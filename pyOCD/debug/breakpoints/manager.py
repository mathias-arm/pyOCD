"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2015-2017 ARM Limited

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

from .provider import Breakpoint
from ...core.target import Target
from ...pyDAPAccess import DAPAccess
import logging
from copy import copy

##
# @brief Breakpoint class used until a breakpoint's type is decided.
class UnrealizedBreakpoint(Breakpoint):
    pass

##
# @brief Manages all breakpoints on the target.
#
# The most important function of the breakpoint manager is to decide which breakpoint provider
# to use when a breakpoint is added. The caller can request a particular breakpoint type, but
# the manager may decide to use another depending on the situation. For instance, it tries to
# keep one hardware breakpoint available to use for stepping.
#
# When the caller requests to add or remove breakpoints, the target is not immediately modified.
# Instead, the add/remove request is recorded for later. Then, before the target is stepped or
# resumed, the manager flushes breakpoint changes to the target. It is at this point when it
# decides which provider to use for each new breakpoint.
class BreakpointManager(object):
    ## Number of hardware breakpoints to try to keep available.
    MIN_HW_BREAKPOINTS = 1

    def __init__(self, core):
        self._breakpoints = {}
        self._updated_breakpoints = {}
        self._core = core
        self._fpb = None
        self._flash_bp = None
        self._providers = {}
        self._ignore_notifications = False

        # Subscribe to some notifications.
        self._core.subscribe(Target.EVENT_PRE_RUN, self.pre_run_handler)
        self._core.subscribe(Target.EVENT_PRE_DISCONNECT, self.pre_disconnect_handler)

    def add_provider(self, provider, type):
        self._providers[type] = provider
        if type == Target.BREAKPOINT_HW:
            self._fpb = provider
        elif type == Target.BREAKPOINT_FLASH:
            self._flash_bp = provider

    ## @brief Return a list of all breakpoint addresses.
    def get_breakpoints(self):
        return self._breakpoints.keys()

    def find_breakpoint(self, addr):
        return self._updated_breakpoints.get(addr, None)

    ## @brief Set a hardware or software breakpoint at a specific location in memory.
    #
    # @retval True Breakpoint was set.
    # @retval False Breakpoint could not be set.
    def set_breakpoint(self, addr, type=Target.BREAKPOINT_AUTO):
        logging.debug("set bkpt type %d at 0x%x", type, addr)

        # Clear Thumb bit in case it is set.
        addr = addr & ~1

        in_hw_bkpt_range = addr < 0x20000000
        fbp_available = ((self._fpb is not None) and
                         (self._fpb.available_breakpoints() > 0))
        fbp_below_min = ((self._fpb is None) or
                         (self._fpb.available_breakpoints() <= self.MIN_HW_BREAKPOINTS))

        # Check for an existing breakpoint at this address.
        bp = self.find_breakpoint(addr)
        if bp is not None:
            return True

        # Reuse breakpoint objects from the live list.
        if self._breakpoints.has_key(addr):
            bp = self._breakpoints[addr]
        else:
            # Create temp bp object. This will be replaced with the real object once
            # breakpoints are flushed and the provider sets the bp.
            bp = UnrealizedBreakpoint(self)
            bp.type = type
            bp.addr = addr

        self._updated_breakpoints[addr] = bp
        return True

    ## @brief Remove a breakpoint at a specific location.
    def remove_breakpoint(self, addr):
        try:
            logging.debug("remove bkpt at 0x%x", addr)

            # Clear Thumb bit in case it is set.
            addr = addr & ~1

            # Remove bp from dict.
            del self._updated_breakpoints[addr]
        except KeyError:
            logging.debug("Tried to remove breakpoint 0x%08x that wasn't set" % addr)

    ##
    # @brief Compute added and removed breakpoints since last flush.
    # @return Bi-tuple of (added breakpoint list, removed breakpoint list).
    def _get_updated_breakpoints(self):
        added = []
        removed = []

        # Get added breakpoints.
        for bp in self._updated_breakpoints.itervalues():
            if not bp.addr in self._breakpoints:
                added.append(bp)

        # Get removed breakpoints.
        for bp in self._breakpoints.itervalues():
            if not bp.addr in self._updated_breakpoints:
                removed.append(bp)

        # Return the list of pages to update.
        return added, removed

    def _select_breakpoint_type(self, bp, allowAllHwBps):
        type = bp.type

        if self._core.memory_map is None:
            # No memory map - fallback to hardware breakpoints.
            type = Target.BREAKPOINT_HW
            is_flash = False
            is_ram = False
        else:
            # Look up the memory type for the requested address.
            region = self._core.memory_map.getRegionForAddress(bp.addr)
            if region is not None:
                is_flash = region.isFlash
                is_ram = region.isRam
            else:
                # No memory region - fallback to hardware breakpoints.
                type = Target.BREAKPOINT_HW
                is_flash = False
                is_ram = False

        in_hw_bkpt_range = bp.addr < 0x20000000
        haveHwBp = self._fpb and ((self._fpb.available_breakpoints() > self.MIN_HW_BREAKPOINTS) \
                    or (allowAllHwBps and self._fpb.available_breakpoints() > 0))

        # Determine best type to use if auto.
        if type == Target.BREAKPOINT_AUTO:
            # Use sw breaks for:
            #  1. Addresses outside the supported FPBv1 range of 0-0x1fffffff
            #  2. RAM regions by default.
            #  3. Number of remaining hw breaks are at or less than the minimum we want to keep.
            # Use flash bp for:
            #  1. is flash region and no hw bp available
            #
            # Otherwise use hw.
            if not in_hw_bkpt_range or (not haveHwBp):
                if is_ram:
                    type = Target.BREAKPOINT_SW
                elif is_flash:
                    type = Target.BREAKPOINT_FLASH
                else:
                    logging.debug("unable to set bp because no hw bp available")
                    return None
            else:
                type = Target.BREAKPOINT_HW

            logging.debug("using type %d for auto bp", type)

        # Can't use hw bp above 0x2000_0000.
        if (type == Target.BREAKPOINT_HW) and not in_hw_bkpt_range:
            if is_ram:
                logging.debug("using sw bp instead because of unsupported addr")
                type = Target.BREAKPOINT_SW
            elif is_flash and self._flash_bp:
                logging.debug("using flash bp instead because of unsupported addr")
                type = Target.BREAKPOINT_FLASH
            else:
                logging.debug("could not fallback to software breakpoint")
                return None

        # Revert to hw or flash bp if region is flash.
        if is_flash:
            if (not haveHwBp) and self._flash_bp:
                logging.debug("using flash bp because no more hw bps are available")
                type = Target.BREAKPOINT_FLASH
            elif in_hw_bkpt_range and haveHwBp:
                logging.debug("using hw bp instead because addr is flash")
                type = Target.BREAKPOINT_HW
            else:
                logging.debug("could not fallback to hardware breakpoint")
                return None

        logging.debug("selected bkpt type %d for addr 0x%x", type, bp.addr)
        return type

    def flush(self, isStep=False):
        try:
            # Ignore any notifications while we modify breakpoints.
            self._ignore_notifications = True

            added, removed = self._get_updated_breakpoints()
            logging.debug("bpmgr: added=%s removed=%s", added, removed)

            # Handle removed breakpoints first by asking the providers to remove them.
            for bp in removed:
                assert bp.provider is not None
                bp.provider.remove_breakpoint(bp)
                del self._breakpoints[bp.addr]

            # Only allow use of all hardware breakpoints if we're not stepping and there is
            # only a single added breakpoint.
            allowAllHwBps = not isStep and len(added) == 1

            # Now handle added breakpoints.
            for bp in added:
                type = self._select_breakpoint_type(bp, allowAllHwBps)
                if type is None:
                    continue

                # Set the bp.
                try:
                    provider = self._providers[type]
                    bp = provider.set_breakpoint(bp.addr)
                except KeyError:
                    raise RuntimeError("Unknown breakpoint type %d" % type)

                # Save the bp.
                if bp is not None:
                    self._breakpoints[bp.addr] = bp

            # Update breakpoint lists.
            logging.debug("bpmgr: bps after flush=%s", self._breakpoints)
            self._updated_breakpoints = copy(self._breakpoints)

            # Flush all providers.
            self._flush_all()
        finally:
            self._ignore_notifications = False

    def get_breakpoint_type(self, addr):
        bp = self.find_breakpoint(addr)
        return bp.type if (bp is not None) else None

    def filter_memory(self, addr, size, data):
        for provider in [p for p in self._providers.itervalues() if p.do_filter_memory]:
            data = provider.filter_memory(addr, size, data)
        return data

    def filter_memory_unaligned_8(self, addr, size, data):
        for provider in [p for p in self._providers.itervalues() if p.do_filter_memory]:
            for i, d in enumerate(data):
                data[i] = provider.filter_memory(addr + i, 8, d)
        return data

    def filter_memory_aligned_32(self, addr, size, data):
        for provider in [p for p in self._providers.itervalues() if p.do_filter_memory]:
            for i, d in enumerate(data):
                data[i] = provider.filter_memory(addr + i, 32, d)
        return data

    def remove_all_breakpoints(self):
        # Remove all breakpoints.
        for bp in self._breakpoints.values():
            bp.provider.remove_breakpoint(bp)
        self._breakpoints = {}
        self._flush_all()

    def _flush_all(self):
        # Flush all providers.
        for provider in self._providers.itervalues():
            provider.flush()

    def pre_run_handler(self, notification):
        if not self._ignore_notifications:
            isStep = notification.data == Target.RUN_TYPE_STEP
            self.flush(isStep)

    def pre_disconnect_handler(self, notification):
        pass


