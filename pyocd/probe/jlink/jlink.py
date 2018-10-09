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

from . import (JLinkError, swd, bitstring)
from .constants import (Commands, Capabilities)
import struct
import usb.core
import usb.util

## @brief J-Link Device Driver
class JLink(object):

    # interface selection
    TIF_JTAG = 0
    TIF_SWD = 1

    # speed (in KHz)
    MAX_SPEED = 12000
    
    # JTAG to SWD sequence.
    #
    # The JTAG-to-SWD sequence is at least 50 TCK/SWCLK cycles with TMS/SWDIO
    # high, putting either interface logic into reset state, followed by a
    # specific 16-bit sequence and finally a line reset in case the SWJ-DP was
    # already in SWD mode.
    SWJ_SEQ = bytearray([   0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7b, 0x9e,
                            0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x0f,   ])
    SWJ_LEN = 118

    def __init__(self, dev):
        self.usb_dev = dev
        self._swd = swd.SWDProtocol()

    @property
    def product_name(self):
        return self.usb_dev.product_name
    
    @property
    def unique_id(self):
        return self.usb_dev.serial_number
    
    @property
    def firmware_version(self):
        return self.fw_version
    
    @property
    def hardware_version(self):
        return self.hw_version

    def open(self):
        self.usb_dev.open()
        self._read_firmware_version()
        self._read_capabilities()
        self._read_hw_version()
        self.config = self.get_config()
        self.get_state()
        self.hw_jtag_cmd = Commands.EMU_CMD_HW_JTAG3
        if self.caps & (1 << Capabilities.EMU_CAP_REGISTER):
            self.register()
        self.select_interface(JLink.TIF_SWD)
        self.set_frequency(100)

    def close(self):
        self.usb_dev.close()

    def _read_firmware_version(self):
        self.usb_dev.write_data([Commands.EMU_CMD_VERSION,])
        n, = struct.unpack('<H', self.usb_dev.read_data(2))
        x = self.usb_dev.read_data(n)
        # split on nulls, get rid of empty strings
        self.fw_version = [s.decode() for s in x.split(b'\x00') if len(s)]

    def _read_capabilities(self):
        # Read basic capabilities.
        self.usb_dev.write_data([Commands.EMU_CMD_GET_CAPS,])
        self.caps = struct.unpack('<I', self.usb_dev.read_data(4))[0]
        
        # Read extended capabilities.
        if self.caps & (1 << Capabilities.EMU_CAP_GET_EXT_CAPS):
            self.usb_dev.write_data([Commands.EMU_CMD_GET_CAPS_EX,])
            self.ext_caps = struct.unpack('<32B', self.usb_dev.read_data(32))

    def _read_hw_version(self):
        if not (self.caps & (1 << Capabilities.EMU_CAP_GET_HW_VERSION)):
            self.hw_version = {}
            return
        
        self.usb_dev.write_data([Commands.EMU_CMD_GET_HW_VERSION,])
        x, = struct.unpack('<I', self.usb_dev.read_data(4))
        ver = {}
        ver['type'] = (x / 1000000) % 100
        ver['major'] = (x / 10000) % 100
        ver['minor'] = (x / 100) % 100
        ver['revision'] = x % 100
        self.hw_version = ver

    def get_max_mem_block(self):
        if not (self.caps & (1 << Capabilities.EMU_CAP_GET_MAX_BLOCK_SIZE)):
            raise JLinkError("EMU_CMD_GET_MAX_MEM_BLOCK not supported")
        self.usb_dev.write_data([Commands.EMU_CMD_GET_MAX_MEM_BLOCK,])
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def get_config(self):
        if not (self.caps & (1 << Capabilities.EMU_CAP_READ_CONFIG)):
            raise JLinkError("EMU_CMD_READ_CONFIG not supported")
        self.usb_dev.write_data([Commands.EMU_CMD_READ_CONFIG,])
        return self.usb_dev.read_data(256)

    def get_state(self):
        self.usb_dev.write_data([Commands.EMU_CMD_GET_STATE,])
        x = struct.unpack('<HBBBBBB', self.usb_dev.read_data(8))
        state = {}
        state['vref'] = x[0]
        state['tck'] = x[1]
        state['tdi'] = x[2]
        state['tdo'] = x[3]
        state['tms'] = x[4]
        state['srst'] = x[5]
        state['trst'] = x[6]
        return state

    def get_interfaces(self):
        if not (self.caps & (1 << Capabilities.EMU_CAP_SELECT_IF)):
            raise JLinkError("EMU_CMD_SELECT_IF not supported")
        self.usb_dev.write_data([Commands.EMU_CMD_SELECT_IF, 0xff])
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def select_interface(self, interface):
        self.usb_dev.write_data([Commands.EMU_CMD_SELECT_IF, (1 << interface)])
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def register(self):
        if not (self.caps & (1 << Capabilities.EMU_CAP_REGISTER)):
            raise JLinkError("EMU_CMD_SELECT_IF not supported")
#         cmd = [Commands.EMU_CMD_REGISTER,JLink.EMU_REG_CMD_REGISTER,0,0,0,0,0,0,0,0,0,0,0,0]
        cmd = [Commands.EMU_CMD_REGISTER,0,0,0,0,0,0,0,0,0,0,0,0]
        self.usb_dev.write_data(cmd)
        data = self.usb_dev.read_data(Commands.REG_MIN_SIZE)
        handle, num, entrySize, infoSize = struct.unpack('<HHHH', data[0:JLink.REG_HEADER_SIZE])
        tableSize = num * entrySize
        size = JLink.REG_HEADER_SIZE + tableSize + infoSize
        print("handle=%d; num=%d; entrySize=%d; infoSize=%d; tableSize=%d; size=%d" % (handle, num, entrySize, infoSize, tableSize, size))
        if size > Commands.REG_MIN_SIZE:
            print("reg: reading extra %d bytes" % (size - Commands.REG_MIN_SIZE))
            data += self.usb_dev.read_data(size - Commands.REG_MIN_SIZE)
        for i in range(num):
            offset = JLink.REG_HEADER_SIZE + i * entrySize
            connInfo = data[offset:offset + entrySize]
            pid, hid, iid, cid, handle, timestamp = struct.unpack('<IIBBHI', connInfo)
            print("conn %d: pid=%d, hid=%d, iid=%d, cid=%d, handle=%d, timestamp=%d" % (i, pid, hid, iid, cid, handle, timestamp))

    def set_frequency(self, f):
        if f < 0:
            speed = 0xffff
        else:
            speed = f // 1000
            if speed > JLink.MAX_SPEED:
                speed = JLink.MAX_SPEED
        cmd = [Commands.EMU_CMD_SET_SPEED, speed & 0xff, (speed >> 8) & 0xff,]
        self.usb_dev.write_data(cmd)

    def reset(self, x):
        cmd = (Commands.EMU_CMD_HW_RESET0, Commands.EMU_CMD_HW_RESET1)[x]
        self.usb_dev.write_data([cmd,])

    def _swd_write(self, numbits, dir, swdio):
        numbytes = (numbits + 7) // 8
        assert len(dir) == len(swdio) == numbytes
        
        cmd = [self.hw_jtag_cmd, 0, numbits & 0xff, (numbits >> 8) & 0xff]
        cmd.extend(dir)
        cmd.extend(swdio)
        self.usb_dev.write_data(cmd)
        
#         assert nbytes % 64
        rd = self.usb_dev.read_data(numbytes + 1)
        if rd[-1] != 0:
            raise JLinkError("EMU_CMD_HW_JTAG3 error")
        rd = rd[:-1]
        return rd

    def swj_sequence(self):
        self._swd_write(self.SWJ_LEN, bitstring.ones(self.SWJ_LEN).bytes, self.SWJ_SEQ)

    def idle(self, clocks):
        idleBits = bitstring.zeros(clocks)
        result = self._swd_write(clocks, bitstring.ones(clocks).bytes, idleBits.bytes)

    def write_reg(self, APnDP, A32, value):
        """Write a single word to a DP or AP register"""
        swdioBits, dirBits = self._swd.generate_write(APnDP, A32, value)
        
        # Insert 8 idle cycles before.
        self.idle(8)
        
        print("write: swdio=",swdioBits,"dir=",dirBits)
        result = self._swd_write(swdioBits.width, dirBits.bytes, swdioBits.bytes)
        ack = self._swd.extract_write_ack(result)
        print("result=",result,"ack=",ack)
        return ack

    def read_reg(self, APnDP, A32):
        """Read a single word to a DP or AP register"""
        swdioBits, dirBits = self._swd.generate_read(APnDP, A32)
        
        # Insert 8 idle cycles before.
        self.idle(8)
        
        print("read: swdio=",swdioBits,"dir=",dirBits)
        result = self._swd_write(dirBits.width, dirBits.bytes, swdioBits.bytes)
        ack, value, parityOk = self._swd.extract_read_result(result)
        print("result=",result,"ack=",ack,"value=",value,"parityOk=",parityOk)
        
        return (ack, value, parityOk)

    def __str__(self):
        s = ['%s' % x for x in self.fw_version]
        s.append('capabilities 0x%08x' % self.caps)
        for i in range(32):
            if self.caps & (1 << i):
                s.append('capability (%2d) %s' % (i, JLink.capabilities[i]))
        s.append(' '.join("%02x" % x for x in self.ext_caps))
#         ifs = self.get_interfaces()
#         s.append("interfaces " + ' '.join(name for (mask,name) in ((1 << JLink.TIF_JTAG, "jtag"), (1 << JLink.TIF_SWD, "swd")) if (ifs & mask)))
#         x = ['%s %d' % (k, v) for (k,v) in self.hw_version.items()]
#         s.append(' '.join(x))
#         s.append('max mem block %d bytes' % self.get_max_mem_block())
#         x = ['%s %d' % (k, v) for (k,v) in self.get_state().items()]
#         s.append(' '.join(x))
        s = ['jlink: %s' % x for x in s]
        return '\n'.join(s)

