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

from .interface_controller import InterfaceController
from ..coresight import (dap, cortex_m, rom_table)
from ..utility.sequencer import CallSequence

## @brief Connect/disconnect controller for a DAP-level interface.
class DAPInterfaceController(InterfaceController):

    def __init__(self, session):
        super(DAPInterfaceController, self).__init__(session)
        self._dp = None
    
    @property
    def dp(self):
        return self._dp
    
    def init(self):
        self._dp = dap.DebugPort(self.session.probe, self.session)

    def connect(self):
        seq = CallSequence(
            ('dp_init',             self.dp.init),
            ('power_up',            self.dp.power_up_debug),
            ('find_aps',            self.dp.find_aps),
            ('create_aps',          self.dp.create_aps),
            ('init_ap_roms',        self.dp.init_ap_roms),
            ('create_cores',        self.create_cores),
            ('create_components',   self.create_components),
            ('board_init',          self.session.board.init),
            )
        
        return seq

    def disconnect(self):
        return CallSequence(
            ('power_down',          self.dp.power_down_debug)
            )
    
    def _create_component(self, cmpid):
        cmp = cmpid.factory(self.session, cmpid.mem, cmpid, cmpid.address)
        cmp.init()

    def create_cores(self):
        self._new_core_num = 0
        self._apply_to_all_components(self._create_component, filter=lambda c: c.factory == cortex_m.CortexM.factory)

    def create_components(self):
        self._apply_to_all_components(self._create_component, filter=lambda c: c.factory is not None and c.factory != cortex_m.CortexM.factory)
    
    def _apply_to_all_components(self, action, filter=None):
        # Iterate over every top-level ROM table.
        for ap in [x for x in self.dp.aps.values() if x.has_rom_table]:
            ap.rom_table.for_each(action, filter)
  

