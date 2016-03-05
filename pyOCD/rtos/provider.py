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

## @brief Base class representing a thread on the target.
class TargetThread(object):
    def __init__(self):
        pass

    @property
    def unique_id(self):
        raise NotImplementedError()

    @property
    def name(self):
        raise NotImplementedError()

    @property
    def description(self):
        raise NotImplementedError()

    @property
    def is_current(self):
        raise NotImplementedError()

    def get_context(self):
        raise NotImplementedError()

## @brief Base class for RTOS support plugins.
class ThreadProvider(object):
    def __init__(self, target):
        self._target = target

    ##
    # @retval True The provider was successfully initialzed.
    # @retval False The provider could not be initialized successfully.
    def init(self, symbolProvider):
        raise NotImplementedError()

    def get_threads(self):
        raise NotImplementedError()

    @property
    def is_enabled(self):
        raise NotImplementedError()

    @property
    def current_thread(self):
        raise NotImplementedError()

