"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2017 ARM Limited

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

from ..core.target import Target
import logging

# Need a local copy to prevent circular import.
# Debug Exception and Monitor Control Register
DEMCR = 0xE000EDFC
DEMCR_TRCENA = (1 << 24)

class ITMOptions(object):
    def __init__(self):
        pass

class ITM(object):
    STIMn = 0xe0000000
    TERn = 0xe0000e00

    TCR = 0xe0000e80
    TCR_ITMENA_MASK = (1 << 0)
    TCR_TSENA_MASK = (1 << 1)
    TCR_SYNCENA_MASK = (1 << 2)
    TCR_TXENA_MASK = (1 << 3)
    TCR_SWOENA_MASK = (1 << 4)
    TCR_TSPRESCALE_MASK = (0x3 << 8)
    TCR_TSPRESCALE_SHIFT = 8
    TCR_TSPRESCALE_DIV_1 = 0x0
    TCR_TSPRESCALE_DIV_4 = 0x1
    TCR_TSPRESCALE_DIV_16 = 0x2
    TCR_TSPRESCALE_DIV_64 = 0x3
    TCR_GTSFREQ_MASK = (0x3 << 10)
    TCR_GTSFREQ_SHIFT = 10
    TCR_TRACEBUSID_MASK = (0x7f << 16)
    TCR_TRACEBUSID_SHIFT = 16
    TCR_BUSY_MASK = (1 << 23)
    
    LAR = 0xe0000fb0
    LAR_KEY = 0xC5ACCE55
    LSR = 0xe0000fb4
    LSR_SLK_MASK = (1 << 1)
    LSR_SLI_MASK = (1 << 0)

    def __init__(self, ap):
        super(ITM, self).__init__()
        self.ap = ap
        self._is_enabled = False

    def init(self):
        # Make sure trace is enabled.
        demcr = self.ap.readMemory(DEMCR)
        if (demcr & DEMCR_TRCENA) == 0:
            demcr |= DEMCR_TRCENA
            self.ap.writeMemory(DEMCR, demcr)

        # Unlock if required.
        val = self.ap.read32(ITM.LSR)
        if (val & (ITM.LSR_SLK_MASK | ITM.LSR_SLI_MASK)) == (ITM.LSR_SLK_MASK | ITM.LSR_SLI_MASK):
            self.ap.write32(ITM.LAR, ITM.LAR_KEY)
            val = self.ap.read32(ITM.LSR)
            if val & ITM.LSR_SLK_MASK:
                raise RuntimeError("Failed to unlock ITM")
        
        # Disable the ITM until enabled.
        self.disable()

    def enable(self):
        self.ap.write32(ITM.TCR, ((1 << ITM.TCR_TRACEBUSID_SHIFT) | ITM.TCR_ITMENA_MASK | 
                                    ITM.TCR_TSENA_MASK | ITM.TCR_TXENA_MASK |
                                    (ITM.TCR_TSPRESCALE_DIV_4 << ITM.TCR_TSPRESCALE_SHIFT)))
        self._is_enabled = True
    
    def disable(self):
        self.ap.write32(ITM.TCR, 0)
        self._is_enabled = False
        
