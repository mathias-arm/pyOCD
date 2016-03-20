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

from ...core.target import Target
from ...pyDAPAccess import DAPAccess
from .provider import Breakpoint
from .software import SoftwareBreakpointProvider
from ...utility import conversion
import logging
from copy import copy
from collections import namedtuple

ENABLE_VERIFY = False # Verify pages after writes.

OP_ADD = 1 # Add breakpoint to page.
OP_REMOVE = 2 # Remove breakpoint from page.

PageUpdate = namedtuple('PageUpdate', 'info ops')
PageOp = namedtuple('PageOp', 'op bp')

class FlashBreakpoint(Breakpoint):
    def __init__(self, provider):
        super(FlashBreakpoint, self).__init__(provider)
        self.type = Target.BREAKPOINT_FLASH

class FlashBreakpointProvider(SoftwareBreakpointProvider):
    ## Save registers r0-r15, xpsr, msp, psp, cfbp
    REGS_TO_SAVE = range(19) + [20]

    def __init__(self, core):
        super(FlashBreakpointProvider, self).__init__(core)
        self._flash = core.flash
        self._analyzer_supported = self._flash.use_analyzer
        self._log = logging.getLogger('flashbp')
        self._updated_breakpoints = {}
        self._ignore_notifications = False
        self._enable_filter = True

        # Subscribe to some notifications.
        self._core.subscribe(Target.EVENT_PRE_RUN, self.pre_run_handler)
        self._core.subscribe(Target.EVENT_PRE_DISCONNECT, self.pre_disconnect_handler)

    def bp_type(self):
        return Target.BREAKPOINT_FLASH

    @property
    def do_filter_memory(self):
        return self._enable_filter

    def _save_state(self, maxPageSize):
        self._saved_regs = self._core.readCoreRegistersRaw(self.REGS_TO_SAVE)
        self._log.debug("Saved registers: [%s]", " ".join("%08x" % r for r in self._saved_regs))

        start = self._flash.flash_algo['load_address']
        count = self._flash.begin_stack - start
        self._log.debug("Saving algo region [%x+%x]", start, count)
        self._saved_algo = self._core.readBlockMemoryUnaligned8(start, count)

        start = self._flash.begin_data
        self._log.debug("Saving buffer region [%x+%x]", start, maxPageSize)
        self._saved_buffer = self._core.readBlockMemoryUnaligned8(start, maxPageSize)

    def _restore_state(self):
        self._log.debug("Restoring state")
        self._core.writeBlockMemoryUnaligned8(self._flash.flash_algo['load_address'], self._saved_algo)
        self._core.writeBlockMemoryUnaligned8(self._flash.begin_data, self._saved_buffer)
        self._core.writeCoreRegistersRaw(self.REGS_TO_SAVE, self._saved_regs)
        self._saved_algo = None
        self._saved_buffer = None
        self._saved_regs = None

    def _start_page_updates(self, maxPageSize):
        # Save memory we're going to stomp over.
        self._save_state(maxPageSize)

        # Disable interrupts.
        self._core.writeCoreRegister('primask', 0x1)

        # Prevent analyzer from being loaded into target memory.
        self._flash.use_analyzer = False

        # Init flash algo.
        self._log.debug("Initing flash algo")
        self._flash.init(reset=False)

    def _finish_page_updates(self):
        # Restore everything.
        self._flash.cleanup()
        self._flash.use_analyzer = self._analyzer_supported
        self._restore_state()

#     def find_breakpoint(self, addr):
#         return self._breakpoints.get(addr, None)

    def set_breakpoint(self, addr):
        assert self._core.memory_map.getRegionForAddress(addr).isFlash
        assert (addr & 1) == 0

        self._log.debug("Inserting flash bp @ %x", addr)

        if self._updated_breakpoints.has_key(addr):
            raise RuntimeError("trying to add a breakpoint that already exists (address 0x%08x)", addr)

        # Reuse breakpoint objects from the live list so we don't lose the original_instr.
        if self._breakpoints.has_key(addr):
            bp = self._breakpoints[addr]
        else:
            # Create bp object.
            bp = FlashBreakpoint(self)
            bp.enabled = True
            bp.addr = addr
            bp.original_instr = 0 # To be filled in during flush.

        self._updated_breakpoints[addr] = bp

        return bp

    def remove_breakpoint(self, bp):
        assert bp is not None and isinstance(bp, Breakpoint)

        self._log.debug("Removing flash bp @ %x", bp.addr)

        if self._updated_breakpoints.has_key(bp.addr):
            del self._updated_breakpoints[bp.addr]

    ##
    # @brief Compute added and removed breakpoints since last flush.
    # @return List of PageUpdate objects.
    def _get_page_updates(self):
        pages = {}

        # Get added breakpoints.
        for bp in self._updated_breakpoints.itervalues():
            if not bp.addr in self._breakpoints:
                pageInfo = self._flash.getPageInfo(bp.addr)
                if not pageInfo.base_addr in pages:
                    pages[pageInfo.base_addr] = PageUpdate(info=pageInfo, ops=[])
                pages[pageInfo.base_addr].ops.append(PageOp(op=OP_ADD, bp=bp))

        # Get removed breakpoints.
        for bp in self._breakpoints.itervalues():
            if not bp.addr in self._updated_breakpoints:
                pageInfo = self._flash.getPageInfo(bp.addr)
                if not pageInfo.base_addr in pages:
                    pages[pageInfo.base_addr] = PageUpdate(info=pageInfo, ops=[])
                pages[pageInfo.base_addr].ops.append(PageOp(op=OP_REMOVE, bp=bp))

        # Return the list of pages to update.
        return pages.values()

    def _update_one_page(self, page):
        try:
            # Read original page data.
            start = page.info.base_addr
            self._log.debug("Reading original page [%x+%x]", start, page.info.size)
            pageData = self._core.readBlockMemoryUnaligned8(start, page.info.size)

            for op in page.ops:
                offset = op.bp.addr - start
                if op.op == OP_ADD:
                    op.bp.original_instr = conversion.byteListToU16leList(pageData[offset:offset+2])[0]
                    instr = self.BKPT_INSTR
                elif op.op == OP_REMOVE:
                    instr = op.bp.original_instr
                self._log.debug("Changing [%x:%x] from 0x%02x to 0x%02x", start + offset, start + offset + 2,
                    conversion.byteListToU16leList(pageData[offset:offset+2])[0], instr)
                pageData[offset:offset+2] = conversion.u16leListToByteList([instr])

            # Erase the page.
            self._log.debug("Erasing page @ %x", start)
            self._flash.erasePage(start)

            # Program the page.
            self._log.debug("Programming page @ %x", start)
            self._flash.programPage(start, pageData)

            # Verify.
            if ENABLE_VERIFY:
                verifyData = self._core.readBlockMemoryUnaligned8(start, page.info.size)
                if verifyData != pageData:
                    self._log.error("Verify failed")
                    for i in range(len(verifyData)):
                        if verifyData[i] != pageData[i]:
                            self._log.error("Mismatch at byte %d: expected=0x%02x actual=0x%02x",
                                i, pageData[i], verifyData[i])
                else:
                    self._log.debug("Page verified")
        except DAPAccess.TransferError:
            logging.debug("Failed to update flash bps on page at 0x%x" % page.info.base_addr)

    def flush(self):
        try:
            # Ignore any notifications while we modify breakpoints. The target is run while executing
            # the flash algo, so we don't want to get into infinite loops of flushing.
            self._ignore_notifications = True

            # Turn off memory filtering while we modify flash.
            self._enable_filter = False

            pages = self._get_page_updates()
            self._log.debug("flash bp updates: %s", repr(pages))

            if pages:
                # Determine the largest page size, in case flash pages have different sizes as on some devices.
                maxPageSize = max(u.info.size for u in pages)

                # Save system state.
                self._start_page_updates(maxPageSize)

                # Update each page.
                for page in pages:
                    self._update_one_page(page)

                # Restore system state.
                self._finish_page_updates()

            # Update breakpoint lists.
            self._breakpoints = self._updated_breakpoints
            self._updated_breakpoints = copy(self._breakpoints)
        finally:
            self._ignore_notifications = False
            self._enable_filter = True

    def pre_run_handler(self, notification):
        if not self._ignore_notifications:
            self.flush()

    def pre_disconnect_handler(self, notification):
        pass

