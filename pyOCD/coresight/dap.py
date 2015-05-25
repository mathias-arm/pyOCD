"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2015 ARM Limited

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

from ..transport.cmsis_dap import (DP_REG, AP_REG)
import logging

DPIDR_MIN_MASK = 0x10000
DPIDR_VERSION_MASK = 0xf000
DPIDR_VERSION_SHIFT = 12

CSYSPWRUPACK = 0x80000000
CDBGPWRUPACK = 0x20000000
CSYSPWRUPREQ = 0x40000000
CDBGPWRUPREQ = 0x10000000

TRNNORMAL = 0x00000000
MASKLANE = 0x00000f00

class DebugPort(object):
    def __init__(self, transport):
        self.transport = transport

    def init(self):
        # Read ID register and get DP version
        self.dpidr = self.readReg(DP_REG['IDCODE'])
        self.dp_version = (self.dpidr & DPIDR_VERSION_MASK) >> DPIDR_VERSION_SHIFT
        self.is_mindp = (self.dpidr & DPIDR_MIN_MASK) != 0

    def readReg(self, addr):
        return self.transport.readDP(addr)

    def writeReg(self, addr, data):
        self.transport.writeDP(addr, data)

    def clearStickyErr(self):
        self.transport.clearStickyErr()

    def powerUpDebug(self):
        # select bank 0 (to access DRW and TAR)
        self.writeReg(DP_REG['SELECT'], 0)
        self.writeReg(DP_REG['CTRL_STAT'], CSYSPWRUPREQ | CDBGPWRUPREQ)

        while True:
            r = self.readReg(DP_REG['CTRL_STAT'])
            if (r & (CDBGPWRUPACK | CSYSPWRUPACK)) == (CDBGPWRUPACK | CSYSPWRUPACK):
                break

        self.writeReg(DP_REG['CTRL_STAT'], CSYSPWRUPREQ | CDBGPWRUPREQ | TRNNORMAL | MASKLANE)
        self.writeReg(DP_REG['SELECT'], 0)

    def reset(self):
        self.transport.reset()

    def assertReset(self, asserted):
        self.transport.assertReset(asserted)

    def setClock(self, frequency):
        self.transport.setClock(frequency)



