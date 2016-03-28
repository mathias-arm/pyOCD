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

import sys
import os
from elftools.elf.elffile import ELFFile
from intervaltree import IntervalTree
from collections import namedtuple
from itertools import islice, imap
import logging

FunctionInfo = namedtuple('FunctionInfo', 'name subprogram low_pc high_pc')
LineInfo = namedtuple('LineInfo', 'cu filename dirname line')
SymbolInfo = namedtuple('SymbolInfo', 'name address size type')

class ElfSymbolDecoder(object):
    def __init__(self, elf):
        assert isinstance(elf, ELFFile)
        self.elffile = elf

        self.symtab = self.elffile.get_section_by_name('.symtab')
        self.symcount = self.symtab.num_symbols()

        self.symbol_tree = None

        # Build indices.
        self._build_symbol_search_tree()
        self._process_arm_type_symbols()

    def get_elf(self):
        return self.elffile

    def get_symbol_for_address(self, addr):
        try:
            return sorted(self.symbol_tree[addr])[0].data
        except IndexError:
            return None

    def _build_symbol_search_tree(self):
        self.symbol_tree = IntervalTree()
        symbols = self.symtab.iter_symbols()
        for symbol in symbols:
            # Only look for functions and objects.
            sym_type = symbol.entry['st_info']['type']
            if sym_type not in ['STT_FUNC', 'STT_OBJECT']:
                continue

            sym_value = symbol.entry['st_value']
            sym_size = symbol.entry['st_size']

            syminfo = SymbolInfo(name=symbol.name, address=sym_value, size=sym_size, type=sym_type)

            self.symbol_tree.addi(sym_value, sym_value+sym_size, syminfo)

    def _process_arm_type_symbols(self):
        type_symbols = self._get_arm_type_symbol_iter()
#         map(print, imap(lambda x:"%s : 0x%x" % (x.name, x['st_value']), type_symbols))

    def _get_arm_type_symbol_iter(self):
        # Scan until we find $m symbol.
        i = 1
        while i < self.symcount:
            symbol = self.symtab.get_symbol(i)
            if symbol.name == '$m':
                break
            i += 1
        if i >= self.symcount:
            return
        n = symbol['st_value']
        return islice(self.symtab.iter_symbols(), i, n)


class DwarfAddressDecoder(object):
    def __init__(self, elf):
        assert isinstance(elf, ELFFile)
        self.elffile = elf

        if not self.elffile.has_dwarf_info():
            raise Exception("No DWARF debug info available")

        self.dwarfinfo = self.elffile.get_dwarf_info()

        self.subprograms = None
        self.function_tree = None
        self.line_tree = None

        # Build indices.
        self._get_subprograms()
        self._build_function_search_tree()
        self._build_line_search_tree()

    def get_function_for_address(self, addr):
        try:
            return sorted(self.function_tree[addr])[0].data
        except IndexError:
            return None

    def get_line_for_address(self, addr):
        try:
            return sorted(self.line_tree[addr])[0].data
        except IndexError:
            return None

    def _get_subprograms(self):
        self.subprograms = []
        for CU in self.dwarfinfo.iter_CUs():
            self.subprograms.extend([d for d in CU.iter_DIEs() if d.tag == 'DW_TAG_subprogram'])

    def _build_function_search_tree(self):
        self.function_tree = IntervalTree()
        for prog in self.subprograms:
            try:
                name = prog.attributes['DW_AT_name'].value
                low_pc = prog.attributes['DW_AT_low_pc'].value
                high_pc = prog.attributes['DW_AT_high_pc'].value

                fninfo = FunctionInfo(name=name, subprogram=prog, low_pc=low_pc, high_pc=high_pc)

                self.function_tree.addi(low_pc, high_pc, fninfo)
            except KeyError:
                pass

    def _build_line_search_tree(self):
        self.line_tree = IntervalTree()
        for cu in self.dwarfinfo.iter_CUs():
            lineprog = self.dwarfinfo.line_program_for_CU(cu)
            prevstate = None
            for entry in lineprog.get_entries():
                # We're interested in those entries where a new state is assigned
                if entry.state is None:
                    continue

                # Looking for a range of addresses in two consecutive states that
                # contain the required address.
                if prevstate: # and prevstate.address <= address < entry.state.address:
                    fileinfo = lineprog['file_entry'][prevstate.file - 1]
                    filename = fileinfo.name
                    dirname = lineprog['include_directory'][fileinfo.dir_index - 1]
                    info = LineInfo(cu=cu, filename=filename, dirname=dirname, line=prevstate.line)
                    self.line_tree.addi(prevstate.address, entry.state.address, info)
                prevstate = entry.state

    def dump_subprograms(self):
        for prog in self.subprograms:
            name = prog.attributes['DW_AT_name'].value
            try:
                low_pc = prog.attributes['DW_AT_low_pc'].value
            except KeyError:
                low_pc = 0
            try:
                high_pc = prog.attributes['DW_AT_high_pc'].value
            except KeyError:
                high_pc = 0xffffffff
            filename = os.path.basename(prog._parent.attributes['DW_AT_name'].value.replace('\\', '/'))
            logging.debug("%s%s%08x %08x %s", name, (' ' * (50-len(name))), low_pc, high_pc, filename)


