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
            # Read the object from the node.
            obj = self._context.read32(node + LIST_NODE_OBJ_OFFSET)
            yield obj

            next = self._context.read32(node + LIST_NODE_NEXT_OFFSET)
            node = next

## @brief
class ArgonThreadContext(DebugContext):
    def __init__(self, parentContext):
        super(ArgonThreadContext, self).__init__(parentContext.core)
        self._parent = parentContext

    def readCoreRegister(self, id):
        return self._core.readCoreRegister(id)

    def writeCoreRegister(self, id, data):
        return self._core.writeCoreRegister(id, data)

    def readCoreRegisterRaw(self, reg):
        return self._core.readCoreRegisterRaw(reg)

    def readCoreRegistersRaw(self, reg_list):
        return self._core.readCoreRegistersRaw(reg_list)

    def writeCoreRegisterRaw(self, reg, data):
        self._core.writeCoreRegisterRaw(reg, data)

    def writeCoreRegistersRaw(self, reg_list, data_list):
        self._core.writeCoreRegistersRaw(reg_list, data_list)

## @brief Base class representing a thread on the target.
class ArgonThread(TargetThread):
    def __init__(self):
        super(ArgonThread, self).__init__()

    @property
    def unique_id(self):
        return 0

    @property
    def name(self):
        return "a"

    @property
    def description(self):
        return "foo"

    @property
    def is_current(self):
        return False

    def get_context(self):
        return None

## @brief Base class for RTOS support plugins.
class ArgonThreadProvider(ThreadProvider):
    def __init__(self, target):
        super(ArgonThreadProvider, self).__init__(target)
        self.g_ar = None
        self._threads = []

    def init(self, symbolProvider):
        self.g_ar = symbolProvider.get_symbol_value("g_ar")
        if self.g_ar is None:
            return False
        logging.info("Argon: g_ar = 0x%08x", self.g_ar)

        return True

    def _build_thread_list(self):
        pass

    def get_threads(self):
        return self._threads

    @property
    def is_enabled(self):
        return True

    @property
    def current_thread(self):
        return None


