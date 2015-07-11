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

from .ap import (AP_SEL_SHIFT, AP_IDR)
import logging

DP_IDCODE = 0x00
DP_ABORT = 0x00
DP_CTRL_STAT = 0x04
DP_SELECT = 0x08

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
        self.dpidr = self.readReg(DP_IDCODE)
        self.dp_version = (self.dpidr & DPIDR_VERSION_MASK) >> DPIDR_VERSION_SHIFT
        self.is_mindp = (self.dpidr & DPIDR_MIN_MASK) != 0

    def flush(self):
        self.transport.flush()

    def readReg(self, addr):
        return self.transport.readDP(addr)

    def writeReg(self, addr, data):
        self.transport.writeDP(addr, data)

    def clearStickyErr(self):
        self.transport.clearStickyErr()

    def powerUpDebug(self):
        # select bank 0 (to access DRW and TAR)
        self.writeReg(DP_SELECT, 0)
        self.writeReg(DP_CTRL_STAT, CSYSPWRUPREQ | CDBGPWRUPREQ)

        while True:
            r = self.readReg(DP_CTRL_STAT)
            if (r & (CDBGPWRUPACK | CSYSPWRUPACK)) == (CDBGPWRUPACK | CSYSPWRUPACK):
                break

        self.writeReg(DP_CTRL_STAT, CSYSPWRUPREQ | CDBGPWRUPREQ | TRNNORMAL | MASKLANE)
        self.writeReg(DP_SELECT, 0)

    def reset(self):
        self.transport.reset()

    def assertReset(self, asserted):
        self.transport.assertReset(asserted)

    def setClock(self, frequency):
        self.transport.setClock(frequency)

    def findAPs(self):
        ap_num = 0
        while True:
            try:
                idr = self.transport.readAP((ap_num << AP_SEL_SHIFT) | AP_IDR)
                if idr == 0:
                    break
                print "AP#%d IDR = 0x%08x" % (ap_num, idr)
            except Exception, e:
                print "Exception reading AP#%d IDR" % ap_num, e
                break
            ap_num += 1



