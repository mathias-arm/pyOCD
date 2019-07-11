# pyOCD debugger
# Copyright (c) 2019 Arm Limited
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

import os
from intervaltree import IntervalTree
from collections import (namedtuple, OrderedDict)
import logging
from enum import IntEnum
from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarfinfo import DWARFInfo
from elftools.dwarf import constants

from ..types import (
    InvalidTypeDefinition,
    SourceLocation,
    DataType,
    VOID_TYPE,
    ScalarType,
    PointerType,
    ArrayType,
    StructType,
    UnionType,
    EnumerationType,
    )
from ...core import exceptions
from ...utility.compatibility import to_str_safe

LOG = logging.getLogger(__name__)

## @brief Map from DWARF scalar types to struct module format strings used by ScalarType.
SCALAR_FORMAT_MAP = {
    constants.DW_ATE_address : {
        4 : 'L',
        },
    constants.DW_ATE_boolean : {
        1 : '?',
        },
    constants.DW_ATE_float : {
        4 : 'f',
        8 : 'd',
        },
    constants.DW_ATE_signed : {
        1 : 'b',
        2 : 'h',
        4 : 'l',
        8 : 'q',
        },
    constants.DW_ATE_signed_char : {
        1 : 'b',
        },
    constants.DW_ATE_unsigned : {
        1 : 'B',
        2 : 'H',
        4 : 'L',
        8 : 'Q',
        },
    constants.DW_ATE_unsigned_char : {
        1 : 'B',
        },
    }

class PendedTypeException(Exception):
    """! @brief Exception used to skip to next DIE."""
    pass

class DwarfTypeDecoder(object):
    """! @brief Builds a data type hierarchy from DWARF debug info."""
    
    def __init__(self, elf, dwarfinfo):
        assert isinstance(elf, ELFFile)
        assert isinstance(dwarfinfo, DWARFInfo)
        self._elffile = elf
        self._dwarfinfo = dwarfinfo
        self._anon_count = 0
        self._current_lineprog = None
        self._pending_types = {}
        self._types = {}
        self._types_by_offset = {}
        
        self._build_types()
    
    @property
    def types(self):
        return self._types

    def _build_types(self):
        for cu in self._dwarfinfo.iter_CUs():
            # The top DIE should be a DW_TAG_compile_unit or DW_TAG_partial_unit.
            top_die = cu.get_top_DIE()
            assert top_die.tag in ('DW_TAG_compile_unit', 'DW_TAG_partial_unit')
            
            self._current_lineprog = self._dwarfinfo.line_program_for_CU(cu)
            
            name = os.path.basename(to_str_safe(top_die.attributes['DW_AT_name'].value))
            LOG.debug("---- CU: %s", name)
            
            for die in top_die.iter_children():
                try:
                    new_type = self._handle_type_die(die)
                    self._add_type(new_type, die.offset)
                except PendedTypeException:
                    # Ignore this exception and keep processing.
                    pass
                except (KeyError, InvalidTypeDefinition) as err:
                    LOG.debug("Error parsing DWARF types: %s ; die=%s", err, die, exc_info=True)

    def _add_type(self, new_type, offset):
        if new_type is None:
            return

        self._types[new_type.name] = new_type
        self._types_by_offset[offset] = new_type
            
        if offset in self._pending_types:
            for pending_die in self._pending_types[offset]:
                new_type = self._handle_type_die(pending_die)
                self._add_type(new_type, pending_die.offset)
            del self._pending_types[offset]
    
    def _pend_die(self, die, offset):
        if offset in self._pending_types:
            self._pending_types[offset].append(die)
        else:
            self._pending_types[offset] = [die]

    def _handle_type_die(self, die):
        if die.tag == 'DW_TAG_base_type':
            name = to_str_safe(die.attributes['DW_AT_name'].value)
            encoding = die.attributes['DW_AT_encoding'].value
            if 'DW_AT_byte_size' in die.attributes:
                byte_size = die.attributes['DW_AT_byte_size'].value
                try:
                    fmt = SCALAR_FORMAT_MAP[encoding][byte_size]
                except KeyError:
                    raise InvalidTypeDefinition("unsupported base type: {}, {} bytes".format(encoding, byte_size))
                return ScalarType(name, fmt, byte_size)
            else:
                LOG.debug("Unhandled base type: %s", die)
        elif die.tag == 'DW_TAG_typedef':
            name = to_str_safe(die.attributes['DW_AT_name'].value)
            # DW_AT_type may not be present according to the spec.
            if 'DW_AT_type' in die.attributes:
                return self._get_referenced_type(die).make_typedef(name, loc=self._get_source_loc(die))
        elif die.tag == 'DW_TAG_volatile_type':
            parent_type = self._get_referenced_type(die)
            return parent_type.make_typedef(parent_type.name + ' volatile', DataType.Qualifiers.VOLATILE, loc=self._get_source_loc(die))
        elif die.tag == 'DW_TAG_const_type':
            parent_type = self._get_referenced_type(die)
            return parent_type.make_typedef(parent_type.name + ' const', DataType.Qualifiers.CONST, loc=self._get_source_loc(die))
        elif die.tag == 'DW_TAG_restrict_type':
            parent_type = self._get_referenced_type(die)
            return parent_type.make_typedef(parent_type.name + ' restrict', DataType.Qualifiers.RESTRICT, loc=self._get_source_loc(die))
        elif die.tag == 'DW_TAG_pointer_type':
            if 'DW_AT_type' not in die.attributes:
                parent_type = VOID_TYPE
            else:
                parent_type = self._get_referenced_type(die)
            if parent_type.name.endswith('*'):
                name_star = '*'
            else:
                name_star = ' *'
            return PointerType(parent_type.name + name_star, parent_type, loc=self._get_source_loc(die))
        elif die.tag == 'DW_TAG_structure_type':
            return self._handle_struct_type(die, False)
        elif die.tag == 'DW_TAG_union_type':
            return self._handle_struct_type(die, True)
        elif die.tag == 'DW_TAG_array_type':
            return self._handle_array_type(die)
        elif die.tag == 'DW_TAG_enumeration_type':
            return self._handle_enum_type(die)
        
#         elif die.tag == 'DW_TAG_subroutine_type':

    def _get_source_loc(self, die):
        if 'DW_AT_decl_file' not in die.attributes:
            return None
        filenum = die.attributes['DW_AT_decl_file'].value
        # A value of 0 indicates no file.
        if filenum == 0:
            return None
        try:
            # The file and dir indices are base-1, with 0 meaning invalid.
            file_entry = self._current_lineprog.header['file_entry'][filenum - 1]
            dirnum = file_entry['dir_index']
            if dirnum != 0:
                dirname = to_str_safe(self._current_lineprog.header['include_directory'][dirnum - 1])
            else:
                dirname = ""
        except IndexError:
            LOG.debug("invalid DW_AT_decl_file (%d)", filenum)
            return None
        if 'DW_AT_decl_line' in die.attributes:
            line = die.attributes['DW_AT_decl_line'].value
        else:
            line = 0
        
        return SourceLocation(to_str_safe(file_entry['name']), dirname, line)

    def _get_referenced_type(self, die, die_to_pend=None):
        if die_to_pend is None:
            die_to_pend = die
        type_ref = die.attributes['DW_AT_type'].value
        if type_ref not in self._types_by_offset:
            self._pend_die(die_to_pend, type_ref)
            raise PendedTypeException()
        return self._types_by_offset[type_ref]

    def _get_optional_name(self, die):
        if 'DW_AT_name' in die.attributes:
            name = to_str_safe(die.attributes['DW_AT_name'].value)
        else:
            name = "__anonymous${}".format(self._anon_count)
            self._anon_count += 1
        return name
    
    def _handle_struct_type(self, die, is_union):
        # If DW_AT_declaration is set, then this is just a forward declaration that we can ignore.
        if 'DW_AT_declaration' in die.attributes:
            return None
        # The struct may be anonymous.
        name = self._get_optional_name(die)
        byte_size = die.attributes['DW_AT_byte_size'].value
        if is_union:
            klass = UnionType
        else:
            klass = StructType
        struct_type = klass(name, byte_size, loc=self._get_source_loc(die))
        for child in die.iter_children():
            if child.tag == 'DW_TAG_member':
                member_type = self._get_referenced_type(child, die)
                name = self._get_optional_name(child)
                if is_union:
                    struct_type.add_member(name, member_type)
                else:
                    offset = child.attributes['DW_AT_data_member_location'].value
                    struct_type.add_member(name, offset, member_type)
        return struct_type

    def _handle_array_type(self, die):
        element_type = self._get_referenced_type(die)
        count = None
        # The children represent dimensions. We only support 1 for now.
        for child in die.iter_children():
            if child.tag == 'DW_TAG_subrange_type':
                if 'DW_AT_upper_bound' in child.attributes:
                    # The upper bound is inclusive.
                    count = child.attributes['DW_AT_upper_bound'].value + 1
                elif 'DW_TAG_count' in child.attributes:
                    count = child.attributes['DW_TAG_count'].value
                break
        return ArrayType(element_type.name + '[]', element_type, count, loc=self._get_source_loc(die))
    
    def _handle_enum_type(self, die):
        name = self._get_optional_name(die)
        byte_size = die.attributes['DW_AT_byte_size'].value
        enum_type = self._get_referenced_type(die)
        enum = EnumerationType(name, byte_size, enum_type, loc=self._get_source_loc(die))
        for child in die.iter_children():
            name = to_str_safe(child.attributes['DW_AT_name'].value)
            value = child.attributes['DW_AT_const_value'].value
            enum.add_enumerator(name, value)
        return enum
            
        

