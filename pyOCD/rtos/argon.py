"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2016 ARM Limited

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

from .provider import (TargetThread, ThreadProvider)
from .common import read_c_string
from ..debug.context import DebugContext
from ..coresight.cortex_m import CORE_REGISTER
from pyOCD.pyDAPAccess import DAPAccess
import logging

IS_RUNNING_OFFSET = 0x54

ALL_OBJECTS_OFFSET = 0xb0
ALL_OBJECTS_THREADS_OFFSET = 0

THREAD_STACK_POINTER_OFFSET = 0
THREAD_EXTENDED_FRAME_OFFSET = 4
THREAD_NAME_OFFSET = 8
THREAD_STACK_BOTTOM_OFFSET = 12
THREAD_PRIORITY_OFFSET = 16
THREAD_STATE_OFFSET = 17
THREAD_CREATED_NODE_OFFSET = 36

LIST_NODE_NEXT_OFFSET = 0
LIST_NODE_OBJ_OFFSET= 8

class TargetList(object):
    def __init__(self, context, ptr):
        self._context = context
        self._list = ptr

    def __iter__(self):
        next = 0
        head = self._context.read32(self._list)
        node = head
        is_valid = head != 0

        while is_valid and next != head:
            try:
                # Read the object from the node.
                obj = self._context.read32(node + LIST_NODE_OBJ_OFFSET)
                yield obj

                next = self._context.read32(node + LIST_NODE_NEXT_OFFSET)
                node = next
            except DAPAccess.TransferError:
                logging.debug("TransferError while reading list elements (node=0x%08x)", node)
                break

## @brief
class ArgonThreadContext(DebugContext):
    # SP is handled specially, so it is not in this dict.
    CORE_REGISTER_OFFSETS = {
                 0: 32, # r0
                 1: 36, # r1
                 2: 40, # r2
                 3: 44, # r3
                 4: 0, # r4
                 5: 4, # r5
                 6: 8, # r6
                 7: 12, # r7
                 8: 16, # r8
                 9: 20, # r9
                 10: 24, # r10
                 11: 28, # r11
                 12: 48, # r12
                 14: 52, # lr
                 15: 56, # pc
                 16: 60, # xpsr
            }

    def __init__(self, parentContext, thread):
        super(ArgonThreadContext, self).__init__(parentContext.core)
        self._parent = parentContext
        self._thread = thread

    def readCoreRegistersRaw(self, reg_list):
        reg_list = [self.registerNameToIndex(reg) for reg in reg_list]
        reg_vals = []

        inException = self._get_ipsr() > 0
        isCurrent = self._is_current()

        sp = self._get_stack_pointer()
        saveSp = sp
        if not isCurrent:
            sp -= 0x40
        elif inException:
            sp -= 0x20

        for reg in reg_list:
            if isCurrent:
                if not inException:
                    # Not in an exception, so just read the live register.
                    reg_vals.append(self._core.readCoreRegisterRaw(reg))
                    continue
                else:
                    # Check for regs we can't access.
                    if reg in (4, 5, 6, 7, 8, 9, 10, 11):
                        reg_vals.append(0)
                        continue

            # Must handle stack pointer specially.
            if reg == 13:
                reg_vals.append(saveSp)
                continue

            spOffset = self.CORE_REGISTER_OFFSETS.get(reg, None)
            if spOffset is None:
                reg_vals.append(self._core.readCoreRegisterRaw(reg))
                continue
            if isCurrent and inException:
                spOffset -= 0x20

            try:
                reg_vals.append(self._core.read32(sp + spOffset))
            except DAPAccess.TransferError:
                reg_vals.append(0)

        return reg_vals

    def _get_stack_pointer(self):
        sp = 0
        if self._is_current():
            # Read live process stack.
            sp = self._core.readCoreRegister('sp')

            # In IRQ context, we have to adjust for hw saved state.
            if self._get_ipsr() > 0:
                sp += 0x20
        else:
            # Get stack pointer saved in thread struct.
            sp = self._core.read32(self._thread._base + THREAD_STACK_POINTER_OFFSET)

            # Skip saved thread state.
            sp += 0x40
        return sp

    def _get_ipsr(self):
        return self._core.readCoreRegister('xpsr') & 0xff

    def _has_extended_frame(self):
        return False

    def _is_current(self):
        return self._thread.is_current

    def writeCoreRegistersRaw(self, reg_list, data_list):
        self._core.writeCoreRegistersRaw(reg_list, data_list)

## @brief Base class representing a thread on the target.
class ArgonThread(TargetThread):
    def __init__(self, targetContext, provider, base):
        super(ArgonThread, self).__init__()
        self._target_context = targetContext
        self._provider = provider
        self._base = base
        self._thread_context = ArgonThreadContext(self._target_context, self)

        ptr = self._target_context.read32(self._base + THREAD_NAME_OFFSET)
        self._name = read_c_string(self._target_context, ptr)

    @property
    def unique_id(self):
        return self._base

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return ""

    @property
    def is_current(self):
        return self._provider.get_current_thread_id() == self.unique_id

    @property
    def context(self):
        return self._thread_context

    def __str__(self):
        return "<ArgonThread@0x%08x id=%x name=%s>" % (id(self), self.unique_id, self.name)

    def __repr__(self):
        return str(self)

## @brief Base class for RTOS support plugins.
class ArgonThreadProvider(ThreadProvider):
    def __init__(self, target):
        super(ArgonThreadProvider, self).__init__(target)
        self._target_context = self._target.getTargetContext()
        self.g_ar = None
        self._all_threads = None
        self._threads = []
        self._threads_dict = {}

    def init(self, symbolProvider):
        self.g_ar = symbolProvider.get_symbol_value("g_ar")
        if self.g_ar is None:
            return False
        logging.debug("Argon: g_ar = 0x%08x", self.g_ar)

        self._all_threads = self.g_ar + ALL_OBJECTS_OFFSET + ALL_OBJECTS_THREADS_OFFSET

        return True

    def _build_thread_list(self):
        allThreads = TargetList(self._target_context, self._all_threads)
        self._threads = []
        self._threads_dict = {}
        for threadBase in allThreads:
            try:
                t = ArgonThread(self._target_context, self, threadBase)
                logging.debug("Thread 0x%08x (%s)", threadBase, t.name)
                self._threads.append(t)
                self._threads_dict[t.unique_id] = t
            except DAPAccess.TransferError:
                logging.debug("TransferError while examining thread 0x%08x", threadBase)

    def get_threads(self):
        if not self.is_enabled:
            return []
        self.update_threads()
        return self._threads

    def get_thread(self, threadId):
        if not self.is_enabled:
            return None
        self.update_threads()
        return self._threads_dict.get(threadId, None)

    @property
    def is_enabled(self):
        return self.g_ar is not None and self.get_is_running()

    @property
    def current_thread(self):
        if not self.is_enabled:
            return None
        self.update_threads()
        id = self.get_current_thread_id()
        try:
            return self._threads_dict[id]
        except KeyError:
            return None

    def is_valid_thread_id(self, threadId):
        if not self.is_enabled:
            return False
        self.update_threads()
        return threadId in self._threads_dict

    def get_current_thread_id(self):
        if not self.is_enabled:
            return None
        return self._target_context.read32(self.g_ar)

    def get_ipsr(self):
        return self._target_context.readCoreRegister('xpsr') & 0xff

    def get_is_running(self):
        if self.g_ar is None:
            return False
        flag = self._target_context.read8(self.g_ar + IS_RUNNING_OFFSET)
        logging.debug("g_ar.isRunning@0x%08x = %d", self.g_ar + IS_RUNNING_OFFSET, flag)
        return flag != 0


