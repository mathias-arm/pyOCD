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
from .breakpoints import Watchpoint
from ..target.target import Target

# Need a local copy to prevent circular import.
# Debug Exception and Monitor Control Register
DEMCR = 0xE000EDFC
# DWTENA in armv6 architecture reference manual
DEMCR_TRCENA = (1 << 24)
DEMCR_VC_HARDERR = (1 << 10)
DEMCR_VC_BUSERR = (1 << 8)
DEMCR_VC_CORERESET = (1 << 0)

class DWT(CoreSightComponent):
    # DWT (data watchpoint & trace)
    DWT_CTRL = 0xE0001000
    DWT_COMP_BASE = 0xE0001020
    DWT_MASK_OFFSET = 4
    DWT_FUNCTION_OFFSET = 8
    DWT_COMP_BLOCK_SIZE = 0x10

    WATCH_TYPE_TO_FUNCT = {
                            Target.WATCHPOINT_READ: 5,
                            Target.WATCHPOINT_WRITE: 6,
                            Target.WATCHPOINT_READ_WRITE: 7
                            }

    # Only sizes that are powers of 2 are supported
    # Breakpoint size = MASK**2
    WATCH_SIZE_TO_MASK = dict((2**i, i) for i in range(0,32))

    def __init__(self, ap, top_addr):
        super(DWT, self).__init__(ap, top_addr)
        self.watchpoints = []
        self.watchpoint_used = 0
        self.dwt_configured = False

    def init(self):
        """
        Reads the number of hardware watchpoints available on the core
        and makes sure that they are all disabled and ready for future
        use
        """
        demcr = self.ap.readMemory(CortexM.DEMCR)
        demcr = demcr | CortexM.DEMCR_TRCENA
        self.ap.writeMemory(CortexM.DEMCR, demcr)
        dwt_ctrl = self.ap.readMemory(DWT.DWT_CTRL)
        watchpoint_count = (dwt_ctrl >> 28) & 0xF
        logging.info("%d hardware watchpoints", watchpoint_count)
        for i in range(watchpoint_count):
            self.watchpoints.append(Watchpoint(DWT.DWT_COMP_BASE + DWT.DWT_COMP_BLOCK_SIZE*i))
            self.writeMemory(DWT.DWT_COMP_BASE + DWT.DWT_COMP_BLOCK_SIZE*i + DWT.DWT_FUNCTION_OFFSET, 0)
        self.dwt_configured = True

    def findWatchpoint(self, addr, size, type):
        for watch in self.watchpoints:
            if watch.addr == addr and watch.size == size and watch.func == DWT.WATCH_TYPE_TO_FUNCT[type]:
                return watch
        return None

    def setWatchpoint(self, addr, size, type):
        """
        set a hardware watchpoint
        """
        if self.dwt_configured is False:
            self.setupDWT()

        watch = self.findWatchpoint(addr, size, type)
        if watch != None:
            return True

        if type not in DWT.WATCH_TYPE_TO_FUNCT:
            logging.error("Invalid watchpoint type %i", type)
            return False

        for watch in self.watchpoints:
            if watch.func == 0:
                watch.addr = addr
                watch.func = DWT.WATCH_TYPE_TO_FUNCT[type]
                watch.size = size

                if size not in DWT.WATCH_SIZE_TO_MASK:
                    logging.error('Watchpoint of size %d not supported by device', size)
                    return False

                mask = DWT.WATCH_SIZE_TO_MASK[size]
                self.writeMemory(watch.comp_register_addr + DWT.DWT_MASK_OFFSET, mask)
                if self.readMemory(watch.comp_register_addr + DWT.DWT_MASK_OFFSET) != mask:
                    logging.error('Watchpoint of size %d not supported by device', size)
                    return False

                self.writeMemory(watch.comp_register_addr, addr)
                self.writeMemory(watch.comp_register_addr + DWT.DWT_FUNCTION_OFFSET, watch.func)
                self.watchpoint_used += 1
                return True

        logging.error('No more available watchpoint!!, dropped watch at 0x%X', addr)
        return False

    def removeWatchpoint(self, addr, size, type):
        """
        remove a hardware watchpoint
        """
        watch = self.findWatchpoint(addr, size, type)
        if watch is None:
            return

        watch.func = 0
        self.writeMemory(watch.comp_register_addr + DWT.DWT_FUNCTION_OFFSET, 0)
        self.watchpoint_used -= 1
        return

