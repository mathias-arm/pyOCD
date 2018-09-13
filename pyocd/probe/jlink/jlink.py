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

from . import JLinkError
import struct
import usb.core
import usb.util

_TRST_TIME = 0.01
_SRST_TIME = 0.01

_MHz = 1000000.0
_KHz = 1000.0
_FREQ = 12.0 * _MHz

# usb vendor:product IDs
_jlink_vps = (
    (0x1366, 0x0101), # J-Link Base
)

## @brief Communication error with the J-Link device
class JLinkError(IOError):
    pass

## @brief J-Link Device Driver
class JLink(object):

    # Document RM08001-R7 J-Link USB Protocol
    # Commands
    EMU_CMD_VERSION                       = 0x01 # Retrieves the firmware version.
    EMU_CMD_RESET_TRST                    = 0x02
    EMU_CMD_RESET_TARGET                  = 0x03
    EMU_CMD_SET_SPEED                     = 0x05
    EMU_CMD_GET_STATE                     = 0x07
    EMU_CMD_SET_KS_POWER                  = 0x08
    EMU_CMD_REGISTER                      = 0x09
    EMU_CMD_GET_SPEEDS                    = 0xc0 # Retrieves the base freq. and the min.divider of the emulator CPU.
    EMU_CMD_GET_HW_INFO                   = 0xc1
    EMU_CMD_GET_COUNTERS                  = 0xc2
    EMU_CMD_SELECT_IF                     = 0xc7
    EMU_CMD_HW_CLOCK                      = 0xc8
    EMU_CMD_HW_TMS0                       = 0xc9
    EMU_CMD_HW_TMS1                       = 0xca
    EMU_CMD_HW_DATA0                      = 0xcb
    EMU_CMD_HW_DATA1                      = 0xcc
    EMU_CMD_HW_JTAG                       = 0xcd
    EMU_CMD_HW_JTAG2                      = 0xce
    EMU_CMD_HW_JTAG3                      = 0xcf
    EMU_CMD_HW_RELEASE_RESET_STOP_EX      = 0xd0
    EMU_CMD_HW_RELEASE_RESET_STOP_TIMED   = 0xd1
    EMU_CMD_GET_MAX_MEM_BLOCK             = 0xd4  # Retrieves the maximum memory block-size.
    EMU_CMD_HW_JTAG_WRITE                 = 0xd5
    EMU_CMD_HW_JTAG_GET_RESULT            = 0xd6
    EMU_CMD_HW_RESET0                     = 0xdc
    EMU_CMD_HW_RESET1                     = 0xdd
    EMU_CMD_HW_TRST0                      = 0xde
    EMU_CMD_HW_TRST1                      = 0xdf
    EMU_CMD_GET_CAPS                      = 0xe8 # Retrieves capabilities of the emulator.
    EMU_CMD_GET_CPU_CAPS                  = 0xe9
    EMU_CMD_EXEC_CPU_CMD                  = 0xea
    EMU_CMD_GET_CAPS_EX                   = 0xed # Retrieves capabilities (including extended ones) of the emulator.
    EMU_CMD_GET_HW_VERSION                = 0xf0 # Retrieves the hardware version of the emulator.
    EMU_CMD_WRITE_DCC                     = 0xf1
    EMU_CMD_READ_CONFIG                   = 0xf2
    EMU_CMD_WRITE_CONFIG                  = 0xf3
    EMU_CMD_WRITE_MEM                     = 0xf4
    EMU_CMD_READ_MEM                      = 0xf5
    EMU_CMD_MEASURE_RTCK_REACT            = 0xf6
    EMU_CMD_WRITE_MEM_ARM79               = 0xf7
    EMU_CMD_READ_MEM_ARM79                = 0xf8

    # Capabilities: EMU_CMD_GET_CAPS bits
    EMU_CAP_RESERVED_1            = 0
    EMU_CAP_GET_HW_VERSION        = 1
    EMU_CAP_WRITE_DCC             = 2
    EMU_CAP_ADAPTIVE_CLOCKING     = 3
    EMU_CAP_READ_CONFIG           = 4
    EMU_CAP_WRITE_CONFIG          = 5
    EMU_CAP_TRACE                 = 6
    EMU_CAP_WRITE_MEM             = 7
    EMU_CAP_READ_MEM              = 8
    EMU_CAP_SPEED_INFO            = 9
    EMU_CAP_EXEC_CODE             = 10
    EMU_CAP_GET_MAX_BLOCK_SIZE    = 11
    EMU_CAP_GET_HW_INFO           = 12
    EMU_CAP_SET_KS_POWER          = 13
    EMU_CAP_RESET_STOP_TIMED      = 14
    EMU_CAP_RESERVED_2            = 15
    EMU_CAP_MEASURE_RTCK_REACT    = 16
    EMU_CAP_SELECT_IF             = 17
    EMU_CAP_RW_MEM_ARM79          = 18
    EMU_CAP_GET_COUNTERS          = 19
    EMU_CAP_READ_DCC              = 20
    EMU_CAP_GET_CPU_CAPS          = 21
    EMU_CAP_EXEC_CPU_CMD          = 22
    EMU_CAP_SWO                   = 23
    EMU_CAP_WRITE_DCC_EX          = 24
    EMU_CAP_UPDATE_FIRMWARE_EX    = 25
    EMU_CAP_FILE_IO               = 26
    EMU_CAP_REGISTER              = 27
    EMU_CAP_INDICATORS            = 28
    EMU_CAP_TEST_NET_SPEED        = 29
    EMU_CAP_RAWTRACE              = 30
    EMU_CAP_RESERVED_3            = 31

    capabilities = {
        EMU_CAP_RESERVED_1         : "Always 1.",
        EMU_CAP_GET_HW_VERSION     : "EMU_CMD_GET_HARDWARE_VERSION",
        EMU_CAP_WRITE_DCC          : "EMU_CMD_WRITE_DCC",
        EMU_CAP_ADAPTIVE_CLOCKING  : "adaptive clocking",
        EMU_CAP_READ_CONFIG        : "EMU_CMD_READ_CONFIG",
        EMU_CAP_WRITE_CONFIG       : "EMU_CMD_WRITE_CONFIG",
        EMU_CAP_TRACE              : "trace commands",
        EMU_CAP_WRITE_MEM          : "EMU_CMD_WRITE_MEM",
        EMU_CAP_READ_MEM           : "EMU_CMD_READ_MEM",
        EMU_CAP_SPEED_INFO         : "EMU_CMD_GET_SPEED",
        EMU_CAP_EXEC_CODE          : "EMU_CMD_CODE_...",
        EMU_CAP_GET_MAX_BLOCK_SIZE : "EMU_CMD_GET_MAX_BLOCK_SIZE",
        EMU_CAP_GET_HW_INFO        : "EMU_CMD_GET_HW_INFO",
        EMU_CAP_SET_KS_POWER       : "EMU_CMD_SET_KS_POWER",
        EMU_CAP_RESET_STOP_TIMED   : "EMU_CMD_HW_RELEASE_RESET_STOP_TIMED",
        EMU_CAP_RESERVED_2         : "Reserved",
        EMU_CAP_MEASURE_RTCK_REACT : "EMU_CMD_MEASURE_RTCK_REACT",
        EMU_CAP_SELECT_IF          : "EMU_CMD_HW_SELECT_IF",
        EMU_CAP_RW_MEM_ARM79       : "EMU_CMD_READ/WRITE_MEM_ARM79",
        EMU_CAP_GET_COUNTERS       : "EMU_CMD_GET_COUNTERS",
        EMU_CAP_READ_DCC           : "EMU_CMD_READ_DCC",
        EMU_CAP_GET_CPU_CAPS       : "EMU_CMD_GET_CPU_CAPS",
        EMU_CAP_EXEC_CPU_CMD       : "EMU_CMD_EXEC_CPU_CMD",
        EMU_CAP_SWO                : "EMU_CMD_SWO",
        EMU_CAP_WRITE_DCC_EX       : "EMU_CMD_WRITE_DCC_EX",
        EMU_CAP_UPDATE_FIRMWARE_EX : "EMU_CMD_UPDATE_FIRMWARE_EX",
        EMU_CAP_FILE_IO            : "EMU_CMD_FILE_IO",
        EMU_CAP_REGISTER           : "EMU_CMD_REGISTER",
        EMU_CAP_INDICATORS         : "EMU_CMD_INDICATORS",
        EMU_CAP_TEST_NET_SPEED     : "EMU_CMD_TEST_NET_SPEED",
        EMU_CAP_RAWTRACE           : "EMU_CMD_RAWTRACE",
        EMU_CAP_RESERVED_3         : "Reserved",
    }

    # CPU Capabilities: EMU_CMD_GET_CPU_CAPS bits
    CPU_CAP_RESERVED  = 0
    CPU_CAP_WRITE_MEM = 1
    CPU_CAP_READ_MEM  = 2

    cpu_capabilities = {
        CPU_CAP_RESERVED    : "Always 1.",
        CPU_CAP_WRITE_MEM   : "CPU_CMD_WRITE_MEM",
        CPU_CAP_READ_MEM    : "CPU_CMD_READ_MEM",
    }

    # hardware types
    HW_TYPE_JLINK                 = 0
    HW_TYPE_JTRACE                = 1
    HW_TYPE_FLASHER               = 2
    HW_TYPE_JLINK_PRO             = 3
    HW_TYPE_JLINK_LITE_ADI        = 5
    HW_TYPE_JLINK_LITE_XMC4000    = 16
    HW_TYPE_JLINK_LITE_XMC4200    = 17
    HW_TYPE_LPCLINK2              = 18

    hw_type = {
        HW_TYPE_JLINK               : "J-Link",
        HW_TYPE_JTRACE              : "J-Trace",
        HW_TYPE_FLASHER             : "Flasher",
        HW_TYPE_JLINK_PRO           : "J-Link Pro",
        HW_TYPE_JLINK_LITE_ADI      : "J-Link Lite-ADI",
        HW_TYPE_JLINK_LITE_XMC4000  : "J-Link Lite-XMC4000",
        HW_TYPE_JLINK_LITE_XMC4200  : "J-Link Lite-XMC4200",
        HW_TYPE_LPCLINK2            : "J-Link on LPC-Link2",
    }

    # interface selection
    TIF_JTAG = 0
    TIF_SWD = 1

    # speed (in KHz)
    MAX_SPEED = 12000

    def __init__(self, dev):
        self.usb_dev = dev

    @property
    def product_name(self):
        return self.usb_dev.product_name
    
    @property
    def unique_id(self):
        return self.usb_dev.serial_number

    def open(self):
        """Open a new interface to the specified J-Link device"""
        self.usb_dev.open()
        self.caps = self.get_capabilities()
        self.hw_jtag_cmd = JLink.EMU_CMD_HW_JTAG3

    def close(self):
        """Close the J-Link interface"""
        self.usb_dev.close()

    def get_version(self):
        """Return the firmware version"""
        self.usb_dev.write_data([JLink.EMU_CMD_VERSION,])
        n, = struct.unpack('<H', self.usb_dev.read_data(2))
        x = self.usb_dev.read_data(n)
        # split on nulls, get rid of empty strings
        return [s.decode() for s in x.split(b'\x00') if len(s)]

    def get_capabilities(self):
        """Return capabilities"""
        self.usb_dev.write_data([JLink.EMU_CMD_GET_CAPS,])
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def get_hw_version(self):
        """Return the hardware version"""
        if not (self.caps & (1 << JLink.EMU_CAP_GET_HW_VERSION)):
            raise JLinkError("EMU_CMD_GET_HW_VERSION not supported")
        self.usb_dev.write_data([JLink.EMU_CMD_GET_HW_VERSION,])
        x, = struct.unpack('<I', self.usb_dev.read_data(4))
        ver = {}
        ver['type'] = (x / 1000000) % 100
        ver['major'] = (x / 10000) % 100
        ver['minor'] = (x / 100) % 100
        ver['revision'] = x % 100
        return ver

    def get_max_mem_block(self):
        """Return the maximum memory block size of the device"""
        if not (self.caps & (1 << JLink.EMU_CAP_GET_MAX_BLOCK_SIZE)):
            raise JLinkError("EMU_CMD_GET_MAX_MEM_BLOCK not supported")
        self.usb_dev.write_data([JLink.EMU_CMD_GET_MAX_MEM_BLOCK,])
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def get_config(self):
        """Return the 256 byte configuration block"""
        if not (self.caps & (1 << JLink.EMU_CAP_READ_CONFIG)):
            raise JLinkError("EMU_CMD_READ_CONFIG not supported")
        self.usb_dev.write_data([JLink.EMU_CMD_READ_CONFIG,])
        return self.usb_dev.read_data(256)

    def get_state(self):
        """Return the state of the JTAG interface pins"""
        self.usb_dev.write_data([JLink.EMU_CMD_GET_STATE,])
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
        """Return a bitmask of available interfaces"""
        if not (self.caps & (1 << JLink.EMU_CAP_SELECT_IF)):
            raise JLinkError("EMU_CMD_SELECT_IF not supported")
        self.usb_dev.write_data([JLink.EMU_CMD_SELECT_IF, 0xff])
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def select_interface(self, itf):
        """Select the JTAG/SWD interface"""
        x = self.get_interfaces()
        if not (x & (1 << itf)):
            raise JLinkError("interface %d not supported" % itf)
        self.usb_dev.write_data([JLink.EMU_CMD_SELECT_IF, 1<<itf])
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def register(self):
        """Taken from openocd jlink.c - not sure what it does
           comment says - "Registration is sometimes necessary for SWD to work"
           Segger doesn't document it.
        """
        if not (self.caps & (1 << JLink.EMU_CAP_REGISTER)):
            raise JLinkError("EMU_CMD_SELECT_IF not supported")
        cmd = [JLink.EMU_CMD_REGISTER,JLink.EMU_CMD_REGISTER,0,0,0,0,0,0,0,0,0,0,0,0]
        self.usb_dev.write_data(cmd)
        x = self.usb_dev.read_data(76)

    def set_frequency(self, f):
        """set JTAG frequency (Hz)"""
        if f < 0:
            speed = 0xffff
        else:
            speed = int(f / 1000.0)
            if speed > JLink.MAX_SPEED:
                speed = JLink.MAX_SPEED
        cmd = [JLink.EMU_CMD_SET_SPEED, speed & 0xff, (speed >> 8) & 0xff,]
        self.usb_dev.write_data(cmd)

    def trst(self, x):
        """Control the TRST line"""
        cmd = (JLink.EMU_CMD_HW_TRST0, JLink.EMU_CMD_HW_TRST1)[x]
        self.usb_dev.write_data([cmd,])

    def srst(self, x):
        """Control the SRST line"""
        cmd = (JLink.EMU_CMD_HW_RESET0, JLink.EMU_CMD_HW_RESET1)[x]
        self.usb_dev.write_data([cmd,])

    def get_cpu_capabilities(self):
        """Return CPU capabilities"""
        if not (self.caps & (1 << JLink.EMU_CAP_GET_CPU_CAPS)):
            raise JLinkError("EMU_CMD_GET_CPU_CAPS not supported")
        cmd = [JLink.EMU_CMD_GET_CPU_CAPS, 9, JLink.TIF_JTAG, 0, 0]
        self.usb_dev.write_data(cmd)
        return struct.unpack('<I', self.usb_dev.read_data(4))[0]

    def hw_jtag_write(self, tms, tdi, tdo = None):
        #print('tms: %s' % tms.bit_str())
        #print('tdi: %s' % tdi.bit_str())
        n = len(tms)
        assert len(tdi) == n
        cmd = [self.hw_jtag_cmd, 0, n & 0xff, (n >> 8) & 0xff]
        cmd.extend(tms.get())
        cmd.extend(tdi.get())
        self.usb_dev.write_data(cmd)
        nbytes = (n + 7) >> 3
        assert nbytes % 64
        if self.hw_jtag_cmd == JLink.EMU_CMD_HW_JTAG3:
            rd = self.usb_dev.read_data(nbytes + 1)
            if rd[-1] != 0:
                raise JLinkError("EMU_CMD_HW_JTAG3 error")
            rd = rd[:-1]
        else:
            rd = self.usb_dev.read_data(nbytes)
        if tdo is not None:
            tdo.set(n, rd)
            #print('tdo: %s' % tdo.bit_str())

    def write_reg(self, reg_id, value, dap_index=0):
        """Write a single word to a DP or AP register"""
        pass

    def read_reg(self, reg_id, dap_index=0, now=True):
        """Read a single word to a DP or AP register"""
        pass
        
        # Need to wrap the deferred callback to convert exceptions.
        def read_reg_cb():
            pass
        
        return result if now else read_reg_cb

    def reg_write_repeat(self, num_repeats, reg_id, data_array, dap_index=0):
        """Write one or more words to the same DP or AP register"""
        pass

    def reg_read_repeat(self, num_repeats, reg_id, dap_index=0, now=True):
        """Read one or more words from the same DP or AP register"""
        pass

        # Need to wrap the deferred callback to convert exceptions.
        def read_reg_cb():
            pass

        return result if now else read_reg_cb

    def __str__(self):
        s = ['%s' % x for x in self.get_version()]
        s.append('capabilities 0x%08x' % self.caps)
        for i in range(32):
            if self.caps & (1 << i):
                s.append('capability (%2d) %s' % (i, JLink.capabilities[i]))
        s.append('cpu capabilities 0x%08x' % self.get_cpu_capabilities())
        ifs = self.get_interfaces()
        s.append("interfaces " + ' '.join(name for (mask,name) in ((1 << JLink.TIF_JTAG, "jtag"), (1 << JLink.TIF_SWD, "swd")) if (ifs & mask)))
        x = ['%s %d' % (k, v) for (k,v) in self.get_hw_version().items()]
        s.append(' '.join(x))
        s.append('max mem block %d bytes' % self.get_max_mem_block())
        x = ['%s %d' % (k, v) for (k,v) in self.get_state().items()]
        s.append(' '.join(x))
        s = ['jlink: %s' % x for x in s]
        return '\n'.join(s)

