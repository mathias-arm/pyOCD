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

from .target import Target
from ..coresight import (dap, ap, cortex_m)
from ..transport.transport import Transport

##
# @brief Debug target that uses CoreSight classes.
class CoreSightTarget(Target):

    def __init__(self, transport, memoryMap=None):
        super(CoreSightTarget, self).__init__(transport, memoryMap)
        self.part_number = self.__class__.__name__
        self.cores = []
        self.aps = []
        self.dp = dap.DebugPort(transport)
        self.selected_core = 0

    @property
    def main_core(self):
        return self.cores[self.selected_core]

    def selectCore(self, num):
        if num >= len(self.cores):
            raise ValueError("invalid core number")
        self.selected_core = num

    def init(self):
        # Create the DP and turn on debug.
        self.dp.init()
        self.dp.powerUpDebug()

        # Create an AHB-AP for the CPU.
        self.aps.append(ap.AHB_AP(self.dp, 0))
        self.aps[0].init()

        # Create CortexM core.
        self.cores.append(cortex_m.CortexM(self.transport, self.dp, self.aps[0], self.memory_map))
        self.main_core.init()

    def readIDCode(self):
        return self.dp.dpidr

    def halt(self):
        return self.main_core.halt()

    def step(self):
        return self.main_core.step()

    def resume(self):
        return self.main_core.resume()

    def writeMemory(self, addr, value, transfer_size=32):
        return self.main_core.writeMemory(addr, value, transfer_size)

    def readMemory(self, addr, transfer_size=32, mode=Transport.READ_NOW):
        return self.main_core.readMemory(addr, transfer_size, mode)

    def writeBlockMemoryUnaligned8(self, addr, value):
        return self.main_core.writeBlockMemoryUnaligned8(addr, value)

    def writeBlockMemoryAligned32(self, addr, data):
        return self.main_core.writeBlockMemoryAligned32(addr, data)

    def readBlockMemoryUnaligned8(self, addr, size):
        return self.main_core.readBlockMemoryUnaligned8(addr, size)

    def readBlockMemoryAligned32(self, addr, size):
        return self.main_core.readBlockMemoryAligned32(addr, size)

    def readCoreRegister(self, id):
        return self.main_core.readCoreRegister(id)

    def writeCoreRegister(self, id):
        return self.main_core.writeCoreRegister(id)

    def readCoreRegisterRaw(self, reg):
        return self.main_core.readCoreRegisterRaw(reg)

    def readCoreRegistersRaw(self, reg_list):
        return self.main_core.readCoreRegistersRaw(reg_list)

    def writeCoreRegisterRaw(self, reg, data):
        self.main_core.writeCoreRegisterRaw(reg, data)

    def writeCoreRegistersRaw(self, reg_list, data_list):
        self.main_core.writeCoreRegistersRaw(reg_list, data_list)

    def setBreakpoint(self, addr, type=Target.BREAKPOINT_AUTO):
        return self.main_core.setBreakpoint(addr, type)

    def getBreakpointType(self, addr):
        return self.main_core.getBreakpointType(addr)

    def removeBreakpoint(self, addr):
        return self.main_core.removeBreakpoint(addr)

    def setWatchpoint(self, addr, size, type):
        return self.main_core.setWatchpoint(addr, size, type)

    def removeWatchpoint(self, addr, size, type):
        return self.main_core.removeWatchpoint(addr, size, type)

    def reset(self):
        return self.main_core.reset()

    def resetStopOnReset(self, software_reset=None):
        return self.main_core.resetStopOnReset(software_reset)

    def setTargetState(self, state):
        return self.main_core.setTargetState(state)

    def getState(self):
        return self.main_core.getState()

    def getMemoryMap(self):
        return self.memory_map

    def setVectorCatchFault(self, enable):
        return self.main_core.setVectorCatchFault(enable)

    def getVectorCatchFault(self):
        return self.main_core.getVectorCatchFault()

    def setVectorCatchReset(self, enable):
        return self.main_core.setVectorCatchReset(enable)

    def getVectorCatchReset(self):
        return self.main_core.getVectorCatchReset()

    # GDB functions
    def getTargetXML(self):
        return self.main_core.getTargetXML()

    def getRegisterContext(self):
        return self.main_core.getRegisterContext()

    def setRegisterContext(self, data):
        return self.main_core.setRegisterContext(data)

    def setRegister(self, reg, data):
        return self.main_core.setRegister(reg, data)

    def getTResponse(self, gdbInterrupt=False):
        return self.main_core.getTResponse(gdbInterrupt)

