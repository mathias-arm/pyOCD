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

FREERTOS_MAX_PRIORITIES	= 63

LIST_SIZE = 20
LIST_INDEX_OFFSET = 16
LIST_NODE_NEXT_OFFSET = 8
LIST_NODE_OBJECT_OFFSET = 12

THREAD_STACK_POINTER_OFFSET = 0
THREAD_PRIORITY_OFFSET = 44
THREAD_NAME_OFFSET = 52

class TargetList(object):
    def __init__(self, context, ptr):
        self._context = context
        self._list = ptr

    def __iter__(self):
        prev = -1
        found = 0
        count = self._context.read32(self._list)
        if count == 0:
            return

        node = self._context.read32(self._list + LIST_INDEX_OFFSET)

        while (node != 0) and (node != prev) and (found < count):
            try:
                # Read the object from the node.
                obj = self._context.read32(node + LIST_NODE_OBJECT_OFFSET)
                yield obj
                found += 1

                # Read next list node pointer.
                prev = node
                node = self._context.read32(node + LIST_NODE_NEXT_OFFSET)
            except DAPAccess.TransferError:
                logging.debug("TransferError while reading list elements (node=0x%08x)", node)
                break

## @brief
class FreeRTOSThreadContext(DebugContext):
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
        super(FreeRTOSThreadContext, self).__init__(parentContext.core)
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
class FreeRTOSThread(TargetThread):
    RUNNING = 1
    READY = 2
    BLOCKED = 3
    SUSPENDED = 4
    DELETED = 5

    STATE_NAMES = {
            RUNNING : "Running",
            READY : "Ready",
            BLOCKED : "Blocked",
            SUSPENDED : "Suspended",
            DELETED : "Deleted",
        }

    def __init__(self, targetContext, provider, base):
        super(FreeRTOSThread, self).__init__()
        self._target_context = targetContext
        self._provider = provider
        self._base = base
        self._state = FreeRTOSThread.READY
        self._thread_context = FreeRTOSThreadContext(self._target_context, self)

        self._priority = self._target_context.read32(self._base + THREAD_PRIORITY_OFFSET)

        self._name = read_c_string(self._target_context, self._base + THREAD_NAME_OFFSET)
        if len(self._name) == 0:
            self._name = "Unnamed"

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    @property
    def priority(self):
        return self._priority

    @property
    def unique_id(self):
        return self._base

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "%s; Priority %d" % (self.STATE_NAMES[self.state], self.priority)

    @property
    def is_current(self):
        return self._provider.get_current_thread_id() == self.unique_id

    @property
    def context(self):
        return self._thread_context

    def __str__(self):
        return "<FreeRTOSThread@0x%08x id=%x name=%s>" % (id(self), self.unique_id, self.name)

    def __repr__(self):
        return str(self)

## @brief Base class for RTOS support plugins.
class FreeRTOSThreadProvider(ThreadProvider):

    FREERTOS_SYMBOLS = [
        "uxCurrentNumberOfTasks",
        "pxCurrentTCB",
        "pxReadyTasksLists",
        "xDelayedTaskList1",
        "xDelayedTaskList2",
        "xPendingReadyList",
        "xSuspendedTaskList",
        "xTasksWaitingTermination",
        "uxTopReadyPriority",
        ]

    def __init__(self, target):
        super(FreeRTOSThreadProvider, self).__init__(target)
        self._target_context = self._target.getTargetContext()
        self._symbols = None
        self._total_priorities = 0
        self._threads = []
        self._threads_dict = {}

    def init(self, symbolProvider):
        self._symbols = self._lookup_symbols(self.FREERTOS_SYMBOLS, symbolProvider)
        if self._symbols is None:
            return False

        # Check for the expected list size.
        delta = self._symbols['xDelayedTaskList2'] - self._symbols['xDelayedTaskList1']
        if delta != LIST_SIZE:
            logging.warning("FreeRTOS: list size is unexpected")
            return False

        delta = self._symbols['xDelayedTaskList1'] - self._symbols['pxReadyTasksLists']
        if delta % LIST_SIZE:
            logging.warning("FreeRTOS: pxReadyTasksLists size is unexpected, maybe an unsupported version of FreeRTOS")
            return False
        self._total_priorities = delta // LIST_SIZE
        if self._total_priorities > FREERTOS_MAX_PRIORITIES:
            logging.warning("FreeRTOS: number of priorities is too large (%d)", self._total_priorities)
            return False
        logging.debug("FreeRTOS: number of priorities is %d", self._total_priorities)

        return True

    def _build_thread_list(self):
        self._threads = []
        self._threads_dict = {}

        # Read the number of threads.
        threadCount = self._target_context.read32(self._symbols['uxCurrentNumberOfTasks'])

        # Read the current thread.
        currentThread = self._target_context.read32(self._symbols['pxCurrentTCB'])

        if threadCount == 0 or currentThread == 0:
            # TODO handle me
            return

        # Read the top ready priority.
        topPriority = self._target_context.read32(self._symbols['uxTopReadyPriority'])
        if topPriority > self._total_priorities:
            logging.warning("FreeRTOS: top ready priority (%d) is greater than the total number of priorities (%d)", topPriority, self._total_priorities)
            return

        # Build up list of all the thread lists we need to scan.
        listsToRead = []
        for i in range(topPriority + 1):
            listsToRead.append((self._symbols['pxReadyTasksLists'] + i * LIST_SIZE, FreeRTOSThread.READY))

        listsToRead.append((self._symbols['xDelayedTaskList1'], FreeRTOSThread.BLOCKED))
        listsToRead.append((self._symbols['xDelayedTaskList2'], FreeRTOSThread.BLOCKED))
        listsToRead.append((self._symbols['xPendingReadyList'], FreeRTOSThread.READY))
        listsToRead.append((self._symbols['xSuspendedTaskList'], FreeRTOSThread.SUSPENDED))
        listsToRead.append((self._symbols['xTasksWaitingTermination'], FreeRTOSThread.DELETED))

        for listPtr, state in listsToRead:
            allThreads = TargetList(self._target_context, listPtr)
            for threadBase in allThreads:
                try:
                    t = FreeRTOSThread(self._target_context, self, threadBase)
                    if threadBase == currentThread:
                        t.state = FreeRTOSThread.RUNNING
                    else:
                        t.state = state
                    logging.info("Thread 0x%08x (%s)", threadBase, t.name)
                    self._threads.append(t)
                    self._threads_dict[t.unique_id] = t
                except DAPAccess.TransferError:
                    logging.debug("TransferError while examining thread 0x%08x", threadBase)

        if len(self._threads) != threadCount:
            logging.warning("FreeRTOS: thread count mismatch")

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
        return self._symbols is not None and self.get_is_running()

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
        return self._target_context.read32(self._symbols['pxCurrentTCB'])

    def get_ipsr(self):
        return self._target_context.readCoreRegister('xpsr') & 0xff

    def get_is_running(self):
        if self._symbols is None:
            return False
        return self._target_context.read32(self._symbols['pxCurrentTCB']) != 0


