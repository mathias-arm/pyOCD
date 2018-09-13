# pyOCD debugger
# Copyright (c) 2018 Arm Limited
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


## @brief Abstract class for an interface's connect/disconnect controller.
class InterfaceController(object):

    def __init__(self, session):
        self._session = session
    
    @property
    def session(self):
        return self._session
    
    def init(self):
        pass
    
    def connect(self):
        raise NotImplementedError()

    def disconnect(self):
        raise NotImplementedError()
  

