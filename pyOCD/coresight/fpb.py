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

import logging
from .rom_table import CoreSightComponent
from .breakpoints import Breakpoint, BreakpointProvider

# FPB (breakpoint)
FP_CTRL = (0xE0002000)
FP_CTRL_KEY = (1 << 1)
FP_COMP0 = (0xE0002008)

class FPB(CoreSightComponent, BreakpointProvider):
    def __init__(self, ap, top_addr):
        CoreSightComponent.__init__(ap, top_addr)
        BreakpointProvider.__init__(ap)
        self.hw_breakpoints = []
        self.nb_code = 0
        self.nb_lit = 0
        self.num_hw_breakpoint_used = 0
        self.enabled = False

    def init(self):
        """
        Reads the number of hardware breakpoints available on the core
        and disable the FPB (Flash Patch and Breakpoint Unit)
        which will be enabled when a first breakpoint will be set
        """
        # setup FPB (breakpoint)
        fpcr = self.ap.readMemory(FP_CTRL)
        self.nb_code = ((fpcr >> 8) & 0x70) | ((fpcr >> 4) & 0xF)
        self.nb_lit = (fpcr >> 7) & 0xf
        logging.info("%d hardware breakpoints, %d literal comparators", self.nb_code, self.nb_lit)
        for i in range(self.nb_code):
            self.hw_breakpoints.append(Breakpoint(FP_COMP0 + 4*i))

        # disable FPB (will be enabled on first bp set)
        self.disable()
        for bp in self.hw_breakpoints:
            self.ap.writeMemory(bp.comp_register_addr, 0)

    def enable(self):
        self.writeMemory(FP_CTRL, FP_CTRL_KEY | 1)
        self.fpb_enabled = True
        logging.debug('fpb has been enabled')
        return

    def disable(self):
        self.writeMemory(FP_CTRL, FP_CTRL_KEY | 0)
        self.fpb_enabled = False
        logging.debug('fpb has been disabled')
        return

    def available_breakpoints(self):
        return len(self.hw_breakpoints) - self.num_hw_breakpoint_used

    def set_breakpoint(self, addr):
        """
        set a hardware breakpoint at a specific location in flash
        """
        if self.fpb_enabled is False:
            self.enableFPB()

        if addr >= 0x20000000:
            # Hardware breakpoints are only supported in the range
            # 0x00000000 - 0x1fffffff on cortex-m devices
            logging.error('Breakpoint out of range 0x%X', addr)
            return False

        if self.availableBreakpoint() == 0:
            logging.error('No more available breakpoint!!, dropped bp at 0x%X', addr)
            return False

        for bp in self.hw_breakpoints:
            if not bp.enabled:
                bp.enabled = True
                bp_match = (1 << 30)
                if addr & 0x2:
                    bp_match = (2 << 30)
                self.writeMemory(bp.comp_register_addr, addr & 0x1ffffffc | bp_match | 1)
                bp.addr = addr
                self.num_hw_breakpoint_used += 1
                self.breakpoints[addr] = bp
                return True
        return False

    def remove_breakpoint(self, addr):
        """
        remove a hardware breakpoint at a specific location in flash
        """
        for bp in self.hw_breakpoints:
            if bp.enabled and bp.addr == addr:
                bp.enabled = False
                self.writeMemory(bp.comp_register_addr, 0)
                bp.addr = addr
                self.num_hw_breakpoint_used -= 1
                return

