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

## @brief Abstract interface for DP and AP register access.
class DAPInterface(object):

    ## @brief Write a single word to a DP or AP register.
    def write_reg(self, reg_id, value, dap_index=0):
        raise NotImplementedError()

    ## @brief Read a single word to a DP or AP register.
    def read_reg(self, reg_id, dap_index=0, now=True):
        raise NotImplementedError()

    ## @brief Write one or more words to the same DP or AP register.
    def reg_write_repeat(self, num_repeats, reg_id, data_array, dap_index=0):
        raise NotImplementedError()

    ## @brief Read one or more words from the same DP or AP register.
    def reg_read_repeat(self, num_repeats, reg_id, dap_index=0, now=True):
        raise NotImplementedError()
  

