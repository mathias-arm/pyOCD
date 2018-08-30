# pyOCD debugger
# Copyright (c) 2018 Arm Limited
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# The MIT License (MIT)
# 
# Copyright (c) 2015 Pavel Revak <pavel.revak@gmail.com>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from . import StlinkException
import logging
import struct
import six

log = logging.getLogger('stlink.stlinkv2')

class Stlink(object):
    STLINK_GET_VERSION = 0xf1
    STLINK_DEBUG_COMMAND = 0xf2
    STLINK_DFU_COMMAND = 0xf3
    STLINK_SWIM_COMMAND = 0xf4
    STLINK_GET_CURRENT_MODE = 0xf5
    STLINK_GET_TARGET_VOLTAGE = 0xf7

    STLINK_MODE_DFU = 0x00
    STLINK_MODE_MASS = 0x01
    STLINK_MODE_DEBUG = 0x02
    STLINK_MODE_SWIM = 0x03
    STLINK_MODE_BOOTLOADER = 0x04

    STLINK_DFU_EXIT = 0x07

    STLINK_SWIM_ENTER = 0x00
    STLINK_SWIM_EXIT = 0x01

    STLINK_DEBUG_ENTER_JTAG = 0x00
    STLINK_DEBUG_STATUS = 0x01
    STLINK_DEBUG_FORCEDEBUG = 0x02
    STLINK_DEBUG_APIV1_RESETSYS = 0x03
    STLINK_DEBUG_APIV1_READALLREGS = 0x04
    STLINK_DEBUG_APIV1_READREG = 0x05
    STLINK_DEBUG_APIV1_WRITEREG = 0x06
    STLINK_DEBUG_READMEM_32BIT = 0x07
    STLINK_DEBUG_WRITEMEM_32BIT = 0x08
    STLINK_DEBUG_RUNCORE = 0x09
    STLINK_DEBUG_STEPCORE = 0x0a
    STLINK_DEBUG_APIV1_SETFP = 0x0b
    STLINK_DEBUG_READMEM_8BIT = 0x0c
    STLINK_DEBUG_WRITEMEM_8BIT = 0x0d
    STLINK_DEBUG_APIV1_CLEARFP = 0x0e
    STLINK_DEBUG_APIV1_WRITEDEBUGREG = 0x0f
    STLINK_DEBUG_APIV1_SETWATCHPOINT = 0x10
    STLINK_DEBUG_APIV1_ENTER = 0x20
    STLINK_DEBUG_EXIT = 0x21
    STLINK_DEBUG_READCOREID = 0x22
    STLINK_DEBUG_APIV2_ENTER = 0x30
    STLINK_DEBUG_APIV2_READ_IDCODES = 0x31
    STLINK_DEBUG_APIV2_RESETSYS = 0x32
    STLINK_DEBUG_APIV2_READREG = 0x33
    STLINK_DEBUG_APIV2_WRITEREG = 0x34
    STLINK_DEBUG_APIV2_WRITEDEBUGREG = 0x35
    STLINK_DEBUG_APIV2_READDEBUGREG = 0x36
    STLINK_DEBUG_APIV2_READALLREGS = 0x3a
    STLINK_DEBUG_APIV2_GETLASTRWSTATUS = 0x3b
    STLINK_DEBUG_APIV2_DRIVE_NRST = 0x3c
    STLINK_DEBUG_SYNC = 0x3e
    STLINK_DEBUG_APIV2_START_TRACE_RX = 0x40
    STLINK_DEBUG_APIV2_STOP_TRACE_RX = 0x41
    STLINK_DEBUG_APIV2_GET_TRACE_NB = 0x42
    STLINK_DEBUG_APIV2_SWD_SET_FREQ = 0x43
    STLINK_DEBUG_ENTER_SWD = 0xa3

    STLINK_DEBUG_APIV2_DRIVE_NRST_LOW = 0x00
    STLINK_DEBUG_APIV2_DRIVE_NRST_HIGH = 0x01
    STLINK_DEBUG_APIV2_DRIVE_NRST_PULSE = 0x02

    STLINK_DEBUG_APIV2_SWD_SET_FREQ_MAP = {
        4000000: 0,
        1800000: 1,  # default
        1200000: 2,
        950000:  3,
        480000:  7,
        240000: 15,
        125000: 31,
        100000: 40,
        50000:  79,
        25000: 158,
        # 15000: 265,
        # 5000:  798
    }

    STLINK_MAXIMUM_TRANSFER_SIZE = 1024

    def __init__(self, connector, swd_frequency=1800000):
        self._connector = connector
        self.read_version()
        self.leave_state()
        self.read_target_voltage()
        if self._ver_jtag >= 22:
            self.set_swd_freq(swd_frequency)
#         self.enter_debug_swd()
#         self.read_coreid()

    def clean_exit(self):
        # WORKAROUND for OS/X 10.11+
        # ... read from ST-Link, must be performed even times
        # call this function after last send command
        if self._connector.xfer_counter & 1:
            self._connector.xfer([Stlink.STLINK_GET_CURRENT_MODE], rx_len=2)

    def read_version(self):
        # WORKAROUND for OS/X 10.11+
        # ... retry XFER if first is timeout.
        # only during this command it is necessary
        rx = self._connector.xfer([Stlink.STLINK_GET_VERSION, 0x80], rx_len=6, retry=2, tout=200)
        ver, = struct.unpack('>H', bytearray(rx[:2]))
        dev_ver = self._connector.version
        self._ver_stlink = (ver >> 12) & 0xf
        self._ver_jtag = (ver >> 6) & 0x3f
        self._ver_swim = ver & 0x3f if dev_ver == 'V2' else None
        self._ver_mass = ver & 0x3f if dev_ver == 'V2-1' else None
        self._ver_api = 2 if self._ver_jtag > 11 else 1
        self._ver_str = "%s V%dJ%d" % (dev_ver, self._ver_stlink, self._ver_jtag)
        if dev_ver == 'V2':
            self._ver_str += "S%d" % self._ver_swim
        if dev_ver == 'V2-1':
            self._ver_str += "M%d" % self._ver_mass
        if self.ver_api == 1:
            raise log.warning("ST-Link/%s is not supported, please upgrade firmware." % self._ver_str)
        if self.ver_jtag < 21:
            log.warning("ST-Link/%s is not recent firmware, please upgrade first - functionality is not guaranteed." % self._ver_str)

    @property
    def product_name(self):
        return "STLink" + self._connector.version

    @property
    def serial_number(self):
        return self._connector.serial_number

    @property
    def ver_stlink(self):
        return self._ver_stlink

    @property
    def ver_jtag(self):
        return self._ver_jtag

    @property
    def ver_mass(self):
        return self._ver_mass

    @property
    def ver_swim(self):
        return self._ver_swim

    @property
    def ver_api(self):
        return self._ver_api

    @property
    def ver_str(self):
        return self._ver_str

    def read_target_voltage(self):
        rx = self._connector.xfer([Stlink.STLINK_GET_TARGET_VOLTAGE], rx_len=8)
        a0, a1 = struct.unpack('<II', bytearray(rx[:8]))
        self._target_voltage = 2 * a1 * 1.2 / a0 if a0 != 0 else None

    @property
    def target_voltage(self):
        return self._target_voltage

#     def read_coreid(self):
#         rx = self._connector.xfer([Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_READCOREID], rx_len=4)
# #         self._coreid = int.from_bytes(rx[:4], byteorder='little')
#         self._coreid = struct.unpack('<L', rx[:4])
# 
#     @property
#     def coreid(self):
#         return self._coreid

    def leave_state(self):
        rx = self._connector.xfer([Stlink.STLINK_GET_CURRENT_MODE], rx_len=2)
        if rx[0] == Stlink.STLINK_MODE_DFU:
            self._connector.xfer([Stlink.STLINK_DFU_COMMAND, Stlink.STLINK_DFU_EXIT])
        elif rx[0] == Stlink.STLINK_MODE_DEBUG:
            self._connector.xfer([Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_EXIT])
        elif rx[0] == Stlink.STLINK_MODE_SWIM:
            self._connector.xfer([Stlink.STLINK_SWIM_COMMAND, Stlink.STLINK_SWIM_EXIT])

    def set_swd_freq(self, freq=1800000):
        for f, d in Stlink.STLINK_DEBUG_APIV2_SWD_SET_FREQ_MAP.items():
            if freq >= f:
                rx = self._connector.xfer([Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_APIV2_SWD_SET_FREQ, d], rx_len=2)
                if rx[0] != 0x80:
                    raise StlinkException("Error switching SWD frequency")
                return
        raise StlinkException("Selected SWD frequency is too low")

    def enter_debug_swd(self):
        self._connector.xfer([Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_APIV2_ENTER, Stlink.STLINK_DEBUG_ENTER_SWD], rx_len=2)

    def debug_resetsys(self):
        self._connector.xfer([Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_APIV2_RESETSYS], rx_len=2)
    
    def drive_nreset(self, isAsserted):
        value = Stlink.STLINK_DEBUG_APIV2_DRIVE_NRST_LOW if isAsserted else Stlink.STLINK_DEBUG_APIV2_DRIVE_NRST_HIGH
        self._connector.xfer([Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_APIV2_DRIVE_NRST, value], rx_len=2)

    def read_mem32(self, addr, size):
        assert (addr % 4) == 0, 'get_mem32: Address must be in multiples of 4'
        assert (size % 4) == 0, 'get_mem32: Size must be in multiples of 4'

        result = []
        while size:
            thisTransferSize = min(size, Stlink.STLINK_MAXIMUM_TRANSFER_SIZE)
            
            cmd = [Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_READMEM_32BIT]
            cmd.extend(six.iterbytes(struct.pack('<II', addr, thisTransferSize)))
            result += self._connector.xfer(cmd, rx_len=thisTransferSize)
            
            addr += thisTransferSize
            size -= thisTransferSize
        return result

    def write_mem32(self, addr, data):
        assert (addr % 4) == 0, 'set_mem32: Address must be in multiples of 4'
        assert (len(data) % 4) == 0, 'set_mem32: Size must be in multiples of 4'

        while len(data):
            thisTransferSize = min(len(data), Stlink.STLINK_MAXIMUM_TRANSFER_SIZE)
            thisTransferData = data[:thisTransferSize]
            
            cmd = [Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_WRITEMEM_32BIT]
            cmd.extend(six.iterbytes(struct.pack('<II', addr, thisTransferSize)))
            self._connector.xfer(cmd, data=thisTransferData)
            
            addr += thisTransferSize
            data = data[thisTransferSize:]

    def read_mem8(self, addr, size):
        result = []
        while size:
            thisTransferSize = min(size, 64)
            
            cmd = [Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_READMEM_8BIT]
            cmd.extend(six.iterbytes(struct.pack('<II', addr, thisTransferSize)))
            result += self._connector.xfer(cmd, rx_len=thisTransferSize)
            
            addr += thisTransferSize
            size -= thisTransferSize
        return result

    def write_mem8(self, addr, data):
        while len(data):
            thisTransferSize = min(len(data), 64)
            thisTransferData = data[:thisTransferSize]
            
            cmd = [Stlink.STLINK_DEBUG_COMMAND, Stlink.STLINK_DEBUG_WRITEMEM_8BIT]
            cmd.extend(six.iterbytes(struct.pack('<II', addr, thisTransferSize)))
            self._connector.xfer(cmd, data=thisTransferData)
            
            addr += thisTransferSize
            data = data[thisTransferSize:]
