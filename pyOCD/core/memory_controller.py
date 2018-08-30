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
from ..coresight import (cortex_m, fpb, dwt, rom_table)
from ..utility.sequencer import CallSequence

ROM_BASE = 0xe00ff000
SCS_BASE = 0xe000e000
DWT_BASE = 0xe0001000
FPB_BASE = 0xe0002000

# Debug Exception and Monitor Control Register
DEMCR = 0xE000EDFC
# DWTENA in armv6 architecture reference manual
DEMCR_TRCENA = (1 << 24)

## @brief Interface for memory access.
class MemoryInterfaceController(InterfaceController):
    
    def __init__(self, session):
        super(MemoryInterfaceController, self).__init__(session)
        self.probe = session.probe
        self.rom_table = None

    def connect(self):
        return CallSequence(
            ('probe_connect',       self.session.probe.connect),
            ('create_rom_table',    self.create_rom_table),
            ('create_cores',        self.create_cores),
            ('create_components',   self.create_components),
            ('board_init',          self.session.board.init)
            )

    def disconnect(self):
        return CallSequence(
            ('probe_disconnect',    self.session.probe.disconnect),
            )

    def create_rom_table(self):
        try:
            demcr = self.probe.read32(DEMCR)
            self.probe.write32(DEMCR, demcr | DEMCR_TRCENA)
        except exceptions.TransferError:
            # Ignore exception and read whatever we can of the ROM table.
            pass

        self.rom_table = rom_table.ROMTable(self.session, self.probe, None, ROM_BASE)
        self.rom_table.init()

    def _create_component(self, cmpid):
        cmp = cmpid.factory(self.session, self.probe, cmpid, cmpid.address)
        cmp.init()

    def create_cores(self):
        self._new_core_num = 0
        self._apply_to_all_components(self._create_component, filter=lambda c: c.factory == cortex_m.CortexM.factory)

    def create_components(self):
        self._apply_to_all_components(self._create_component, filter=lambda c: c.factory is not None and c.factory != cortex_m.CortexM.factory)
    
    def _apply_to_all_components(self, action, filter=None):
        # Iterate over the top-level ROM table.
        self.rom_table.for_each(action, filter)

