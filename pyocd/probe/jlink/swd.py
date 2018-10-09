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

from .bitstring import (bitstring, ones, zeros, zero_or_one)

# Dir: 0=in, 1=out

## @brief SWD protocol bit stream generator.
class SWDProtocol(object):
    def __init__(self):
        self._trn = 1
        self._trnBits = ones(self._trn) # Single-bit turnaround by default
        self._trnDirBits = zeros(self._trn) # Direction bits for turnaround.
        self._ackBits = bitstring('111') % self._trnBits
        self._ackDirBits = bitstring('000') % self._trnDirBits
    
    def generate_request(self, APnDP, RnW, A32):
        # 0     1     2   3  4  5      6    7
        # Start APnDP RnW A2 A3 Parity Stop Park
        pkt = bitstring('10000001')
        pkt[1] = APnDP
        pkt[2] = RnW
        pkt[3] = (A32 >> 1) & 1
        pkt[4] = A32 & 1
        parityValue = zero_or_one(APnDP) % zero_or_one(RnW) % bitstring(A32, width=2)
        pkt[5] = parityValue.bit_count() & 1 # parity = 1 if 1s count is odd
        
        return pkt
    
    def generate_wdata(self, data):
        pkt = bitstring(data, width=32)
        pkt %= zero_or_one(pkt.bit_count() & 1)
        return pkt

    def generate_write(self, APnDP, A32, data):
        # Write request.
        swdio = self.generate_request(APnDP, 0, A32)
        dir = ones(8)
        
        # Add turnaround period and input bits.
        swdio %= self._trnBits
        dir %= self._trnDirBits
        
        # Add 3-bit ack and turnaround.
        swdio %= self._ackBits
        dir %= self._ackDirBits
        
        # Write word.
        swdio %= self.generate_wdata(data)
        dir %= ones(33)
        
        return swdio.reverse(), dir.reverse()
    
    def extract_write_ack(self, data):
        bits = bitstring(data, width=(8 + self._trn + 3 + self._trn + 33))
        ack = bits[(8 + self._trn):(8 + self._trn + 3)]
        return ack.value
        
    def generate_read(self, APnDP, A32):
        # Write request.
        swdio = self.generate_request(APnDP, 1, A32)
        dir = ones(8)
        
        # Add turnaround period and input bits.
        swdio %= self._trnBits
        dir %= self._trnDirBits
        
        # Read ack, word, turnaround.
        swdio %= ones(36) % self._trnBits
        dir %= zeros(36) % self._trnDirBits
        
        return swdio.reverse(), dir.reverse()
    
    def extract_read_result(self, data):
        bits = bitstring(data, width=36)
        ack = bits[0:4]
        value = bits[4:35]
        parity = bits[35:36]
        parityOk = (value.bit_count() & 1) == parity.value
        return ack.value, value.value, parityOk


