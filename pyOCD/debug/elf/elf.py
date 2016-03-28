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

from ...target.memory_map import MemoryRange
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import SH_FLAGS
import logging
import six

##
# @brief
class ELFBinaryFile(object):
    def __init__(self, elf, core):
        if type(elf) in (str, unicode):
            self._elf = ELFFile(open(elf, 'rb'))
        else:
            self._elf = ELFFile(elf)
        self._core = core

        self._extract_sections()
        self._compute_regions()

    def _extract_sections(self):
        # Get list of interesting sections.
        self._sections = []
        sections = self._elf.iter_sections()
        for s in sections:
            # Skip sections not of these types.
            if s['sh_type'] not in ('SHT_PROGBITS', 'SHT_NOBITS'):
                continue

            # Skip sections that don't have one of these flags set.
            if s['sh_flags'] & (SH_FLAGS.SHF_WRITE | SH_FLAGS.SHF_ALLOC | SH_FLAGS.SHF_EXECINSTR) == 0:
                continue

            self._sections.append(s)
        self._sections.sort(key=lambda x: x['sh_addr'])

    def _dump_sections(self):
        for s in self._sections:
            flags = s['sh_flags']
            flagsDesc = ""
            if flags & SH_FLAGS.SHF_WRITE:
                flagsDesc += "WRITE|"
            if flags & SH_FLAGS.SHF_ALLOC:
                flagsDesc += "ALLOC|"
            if flags & SH_FLAGS.SHF_EXECINSTR:
                flagsDesc += "EXECINSTR"
            if flagsDesc[-1] == '|':
                flagsDesc = flagsDesc[:-1]
            print "{0:<20} {1:<25} {2:<10} {3:<10}".format(s.name, flagsDesc, hex(s['sh_addr']), hex(s['sh_size']))

    def _compute_regions(self):
        map = self._core.memory_map
        used = []
        unused = []
        for region in map:
            current = region.start
            for sect in self._sections:
                start = sect['sh_addr']
                length = sect['sh_size']

                # Skip if this section isn't within this memory region.
                if not region.containsRange(start, length=length):
                    continue

                # Add this section as used.
                used.append(MemoryRange(start=start, length=length, region=region))

                # Add unused segment.
                if start > current:
                    unused.append(MemoryRange(start=current, length=(start - current), region=region))

                current = start + length

            # Add a final unused segment of the region.
            if region.end > current:
                unused.append(MemoryRange(start=current, end=region.end, region=region))
        self._used = used
        self._unused = unused

    def get_used_regions(self):
        return self._used

    def get_unused_regions(self):
        return self._unused



