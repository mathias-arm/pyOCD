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

import logging

class TPIU(object):
    ACPR = 0xe0040010
    ACPR_PRESCALER_MASK = 0x0000ffff

    SPPR = 0xe00400f0
    SPPR_TXMODE_MASK = 0x00000003
    SPPR_TXMODE_NRZ = 0x00000002

    FFCR = 0xe0040304
    FFCR_ENFCONT_MASK = (1 << 1)

    DEVID = 0xe0040fc8
    DEVID_NRZ_MASK = (1 << 11)

    def __init__(self, ap):
        super(TPIU, self).__init__()
        self.ap = ap
        self._has_swo_uart = False

    def init(self):
        devid = self.ap.read32(TPIU.DEVID)
        self._has_swo_uart = (devid & TPIU.DEVID_NRZ_MASK) != 0
        
        # Go ahead and configure for SWO.
        self.ap.write32(TPIU.SPPR, TPIU.SPPR_TXMODE_NRZ) # Select SWO UART mode.
        self.ap.write32(TPIU.FFCR, 0) # Disable formatter.
    
    ## Sets the SWO clock frequency based on the system clock.
    #
    # @return Boolean indicating if the requested frequency could be set within 3%.
    def set_swo_clock(self, swo_clock, system_clock):
        div = (system_clock // swo_clock) - 1
        actual = system_clock // (div + 1)
        deltaPercent = abs(swo_clock - actual) / swo_clock
        if deltaPercent > 0.03:
            return False
        self.ap.write32(TPIU.ACPR, div & TPIU.ACPR_PRESCALER_MASK)
        return True


