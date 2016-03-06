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
from ..debug.context import DebugContext
from ..coresight.cortex_m import CORE_REGISTER
from pyOCD.pyDAPAccess import DAPAccess
import logging

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

def read_c_string(context, ptr):
    if ptr == 0:
        return ""

    s = ""
    done = False
    count = 0
    try:
        while not done and count < 256:
            data = context.readBlockMemoryUnaligned8(ptr, 16)
            ptr += 16
            count += 16

            for c in data:
                if c == 0:
                    done = True
                    break
                s += chr(c)
    except DAPAccess.TransferError:
        logging.debug("TransferError while trying to read 16 bytes at 0x%08x", ptr)
    return s

## @brief
class ArgonThreadContext(DebugContext):
    def __init__(self, parentContext, thread):
        super(ArgonThreadContext, self).__init__(parentContext.core)
        self._parent = parentContext
        self._thread = thread

    def readCoreRegistersRaw(self, reg_list):
        return self._core.readCoreRegistersRaw(reg_list)

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
        return False

    def get_context(self):
        return self._thread_context

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
        logging.info("Argon: g_ar = 0x%08x", self.g_ar)

        self._all_threads = self.g_ar + ALL_OBJECTS_OFFSET + ALL_OBJECTS_THREADS_OFFSET

        return True

    def _build_thread_list(self):
        allThreads = TargetList(self._target_context, self._all_threads)
        self._threads = []
        self._threads_dict = {}
        for threadBase in allThreads:
            try:
                t = ArgonThread(self._target_context, self, threadBase)
                logging.info("Thread 0x%08x (%s)", threadBase, t.name)
                self._threads.append(t)
                self._threads_dict[t.unique_id] = t
            except DAPAccess.TransferError:
                logging.debug("TransferError while examining thread 0x%08x", threadBase)

    def get_threads(self):
        if not self.is_enabled:
            return []
        self._build_thread_list()
        return self._threads

    @property
    def is_enabled(self):
        return self.g_ar is not None

    @property
    def current_thread(self):
        if not self.is_enabled:
            return None
        self._build_thread_list()
        id = self.get_current_thread_id()
        try:
            return self._threads_dict[id]
        except KeyError:
            return None

    def is_valid_thread_id(self, threadId):
        if not self.is_enabled:
            return False
        self._build_thread_list()
        return threadId in self._threads_dict

    def get_current_thread_id(self):
        if not self.is_enabled:
            return None
        return self._target_context.read32(self.g_ar)

    def get_ipsr(self):
        return self._target_context.readCoreRegister('xpsr') & 0xff


