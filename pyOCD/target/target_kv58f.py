"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2013 ARM Limited

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

from target_kinetis import Kinetis
import logging
from ..transport.transport import TransferError


class KV58F(Kinetis):

    memoryMapXML =  """<?xml version="1.0"?>
<!DOCTYPE memory-map PUBLIC "+//IDN gnu.org//DTD GDB Memory Map V1.0//EN" "http://sourceware.org/gdb/gdb-memory-map.dtd">
<memory-map>
    <memory type="flash" start="0x10000000" length="0x100000"> <property name="blocksize">0x2000</property></memory>
    <memory type="ram" start="0x00000000" length="0x10000"> </memory>
    <memory type="ram" start="0x18000000" length="0x1000"> </memory>
    <memory type="ram" start="0x20000000" length="0x20000"> </memory>
    <memory type="ram" start="0x2F000000" length="0x10000"> </memory>
</memory-map>
"""

    def __init__(self, transport):
        super(KV58F, self).__init__(transport)
        self.mdm_idr = 0x001c0030

    def reset(self, software_reset = None):
        try:
            super(KV58F, self).reset(software_reset)
        except TransferError:
            # KL28 causes a SWD transfer fault for the AIRCR write when
            # it resets. Just ignore this error.
            pass

