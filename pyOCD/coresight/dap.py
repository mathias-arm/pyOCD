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

from ..pyDAPAccess import DAPAccess
import logging

# !! This value are A[2:3] and not A[3:2]
DP_REG = {'IDCODE': DAPAccess.REG.DP_0x0,
          'ABORT': DAPAccess.REG.DP_0x0,
          'CTRL_STAT': DAPAccess.REG.DP_0x4,
          'SELECT': DAPAccess.REG.DP_0x8
          }
AP_REG = {'CSW' : 0x00,
          'TAR' : 0x04,
          'DRW' : 0x0C,
          'IDR' : 0xFC
          }

# DP Control / Status Register bit definitions
CTRLSTAT_STICKYORUN = 0x00000002
CTRLSTAT_STICKYCMP = 0x00000010
CTRLSTAT_STICKYERR = 0x00000020

IDCODE = 0 << 2
AP_ACC = 1 << 0
DP_ACC = 0 << 0
READ = 1 << 1
WRITE = 0 << 1
VALUE_MATCH = 1 << 4
MATCH_MASK = 1 << 5

A32 = 0x0c
APSEL_SHIFT = 24
APSEL = 0xff000000
APBANKSEL = 0x000000f0

# mine...
DP_IDCODE = DAPAccess.REG.DP_0x0
DP_ABORT = DAPAccess.REG.DP_0x0
DP_CTRL_STAT = DAPAccess.REG.DP_0x4
DP_SELECT = DAPAccess.REG.DP_0x8

DPIDR_MIN_MASK = 0x10000
DPIDR_VERSION_MASK = 0xf000
DPIDR_VERSION_SHIFT = 12

AP_IDR = 0xFC

CSYSPWRUPACK = 0x80000000
CDBGPWRUPACK = 0x20000000
CSYSPWRUPREQ = 0x40000000
CDBGPWRUPREQ = 0x10000000

TRNNORMAL = 0x00000000
MASKLANE = 0x00000f00

def _ap_addr_to_reg(addr):
    return DAPAccess.REG(4 + ((addr & A32) >> 2))

class DebugPort(object):
    def __init__(self, link):
        self.link = link
        self.csw = -1
        self.dp_select = -1
        self._fault_recovery_handler = None

    def init(self):
        # Connect to the target.
        self.link.connect()
        self.readIDCode()
        self.clear_sticky_err()

    @property
    def fault_recovery_handler(self):
        return self._fault_recovery_handler

    @fault_recovery_handler.setter
    def fault_recovery_handler(self, handler):
        self._fault_recovery_handler = handler

    def readIDCode(self):
        # Read ID register and get DP version
        self.dpidr = self.readReg(DP_IDCODE)
        self.dp_version = (self.dpidr & DPIDR_VERSION_MASK) >> DPIDR_VERSION_SHIFT
        self.is_mindp = (self.dpidr & DPIDR_MIN_MASK) != 0
        return self.dpidr

    def flush(self):
        try:
            self.link.flush()
        finally:
            self.csw = -1
            self.dp_select = -1

    def readReg(self, addr, now=True):
        return self.readDP(addr, now)

    def writeReg(self, addr, data):
        self.writeDP(addr, data)

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
        try:
            self.link.reset()
        finally:
            self.csw = -1
            self.dp_select = -1

    def assert_reset(self, asserted):
        self.link.assert_reset(asserted)
        self.csw = -1
        self.dp_select = -1

    def set_clock(self, frequency):
        self.link.set_clock(frequency)

    def find_aps(self):
        ap_num = 0
        while True:
            try:
                idr = self.readAP((ap_num << APSEL_SHIFT) | AP_IDR)
                if idr == 0:
                    break
                print "AP#%d IDR = 0x%08x" % (ap_num, idr)
            except Exception, e:
                print "Exception reading AP#%d IDR" % ap_num, e
                break
            ap_num += 1

    def readDP(self, addr, now=True):
        assert addr in DAPAccess.REG

        try:
            result_cb = self.link.read_reg(addr, now=False)
        except DAPAccess.Error as error:
            self._handle_error(error)
            raise

        def readDPCb():
            try:
                return result_cb()
            except DAPAccess.Error as error:
                self._handle_error(error)
                raise

        if now:
            return readDPCb()
        else:
            return readDPCb

    def writeDP(self, addr, data):
        assert addr in DAPAccess.REG
        if addr == DP_REG['SELECT']:
            if data == self.dp_select:
                return
            self.dp_select = data

        try:
            self.link.write_reg(addr, data)
        except DAPAccess.Error as error:
            self._handle_error(error)
            raise
        return True

    def writeAP(self, addr, data):
        assert type(addr) in (int, long)
        ap_sel = addr & APSEL
        bank_sel = addr & APBANKSEL
        self.writeDP(DP_REG['SELECT'], ap_sel | bank_sel)

        # TODO: move csw caching to MEM_AP
        if addr == AP_REG['CSW']:
            if data == self.csw:
                return
            self.csw = data

        ap_reg = _ap_addr_to_reg(WRITE | AP_ACC | (addr & A32))
        try:
            self.link.write_reg(ap_reg, data)

        except DAPAccess.Error as error:
            self._handle_error(error)
            raise

        return True

    def readAP(self, addr, now=True):
        assert type(addr) in (int, long)
        res = None
        ap_reg = _ap_addr_to_reg(READ | AP_ACC | (addr & A32))

        try:
            ap_sel = addr & APSEL
            bank_sel = addr & APBANKSEL
            self.writeDP(DP_REG['SELECT'], ap_sel | bank_sel)
            result_cb = self.link.read_reg(ap_reg, now=False)
        except DAPAccess.Error as error:
            self._handle_error(error)
            raise

        def readAPCb():
            try:
                return result_cb()
            except DAPAccess.Error as error:
                self._handle_error(error)
                raise

        if now:
            return readAPCb()
        else:
            return readAPCb

    def _handle_error(self, error):
        # Invalidate cached registers
        self.csw = -1
        self.dp_select = -1
        # Clear sticky error for Fault errors only
        if isinstance(error, DAPAccess.TransferFaultError):
            self.clear_sticky_err()
        # Let a target-specific handler deal with errors.
        if self._fault_recovery_handler:
            self._fault_recovery_handler(error)

    def clear_sticky_err(self):
        mode = self.link.get_swj_mode()
        if mode == DAPAccess.PORT.SWD:
            self.link.write_reg(DAPAccess.REG.DP_0x0, (1 << 2))
        elif mode == DAPAccess.PORT.JTAG:
            self.link.write_reg(DP_REG['CTRL_STAT'], CTRLSTAT_STICKYERR)
        else:
            assert False



