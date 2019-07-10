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

import struct
import copy
from collections import (namedtuple, OrderedDict)
import logging
from enum import (Enum, IntEnum)

from ..core import exceptions

LOG = logging.getLogger(__name__)

class InvalidTypeDefinition(exceptions.Error):
    """! @brief Could not parse a type definitions."""
    pass

class DataType(object):
    class Qualifiers:
        CONST = 0x01
        VOLATILE = 0x02
        RESTRICT = 0x04
    
    def __init__(self, name, byte_size=0, bit_size=0, bit_offset=0):
        self._name = name
        self._byte_size = byte_size
        self._bit_size = bit_size
        self._bit_offset = bit_offset
        self._parent = None
        self._qualifiers = 0
    
    @property
    def name(self):
        return self._name
    
    @property
    def byte_size(self):
        return self._byte_size
    
    @property
    def bit_size(self):
        return self._bit_size
    
    @property
    def bit_offset(self):
        return self._bit_offset
    
    @property
    def parent(self):
        return self._parent
    
    @property
    def qualifiers(self):
        return self._qualifiers
    
    @property
    def is_const(self):
        return (self._qualifiers & self.Qualifiers.CONST) != 0
    
    @property
    def is_volatile(self):
        return (self._qualifiers & self.Qualifiers.VOLATILE) != 0
    
    @property
    def is_restrict(self):
        return (self._qualifiers & self.Qualifiers.RESTRICT) != 0
    
    def make_typedef(self, new_name, add_qualifiers=None):
        child = copy.copy(self)
        child._name = new_name
        child._parent = self
        if add_qualifiers is not None:
            child._qualifiers |= add_qualifiers
        return child
    
    def decode(self, data):
        raise NotImplementedException()
    
    def encode(self, value):
        raise NotImplementedException()
    
    def _get_repr(self, extra=""):
        q = ""
        if self.is_const:
            q += "c"
        if self.is_volatile:
            q += "v"
        if self.is_restrict:
            q += "r"
        if q == "":
            q = "-"
        if extra:
            extra = " " + extra
        return "<{}@{:#10x} name={} Bsz={} q={}{}>".format(
            self.__class__.__name__, id(self), self.name, self.byte_size, q, extra)
    
    def __repr__(self):
        return self._get_repr()

class ScalarType(DataType):
    """! @brief Base scalar data type.
    
    A scalar type can be one of these:
    - boolean
    - float or double
    - signed byte (char), halfword, or word
    - unsigned byte (char), halfword, or word
    
    This is represented by the combination of the _form_, _is_signed_, and _byte_size_ properties.
    """
    
    class Form(Enum):
        """! @brief Class of scalar."""
        BOOL = 1
        INT = 2
        FLOAT = 3
    
    def __init__(self, name, fmt, byte_size):
        super(ScalarType, self).__init__(name, byte_size=byte_size)
        self._format = "<" + fmt # Force little-endian (for now, at least).
        if fmt == '?':
            self._form = self.Form.BOOL
        elif fmt.lower() in ('b', 'h', 'l', 'q'):
            self._form = self.Form.INT
        elif fmt in ('f', 'd'):
            self._form = self.Form.FLOAT
        else:
            raise InvalidTypeDefinition("unsupported scalar format '{}'".format(fmt))
        self._is_signed = fmt in ('b', 'h', 'l', 'q')
    
    @property
    def form(self):
        return self._form
    
    @property
    def is_signed(self):
        return self._is_signed
    
    def decode(self, data):
        value, = struct.unpack_from(self._format, data)
        return value
    
    def encode(self, value):
        return struct.pack(self._format, value)
    
    def __repr__(self):
        return self._get_repr("{}{}{}".format(
            ('s' if self.is_signed else 'u'),
            self.form.name,
            self.byte_size,
            ))

class PointerType(DataType):
    """! @brief Pointer to another type.
    
    We assume a pointer is always 32-bit (and little-endian). If we ever support v8-A/R
    or later, we'll have to correct this assumption.
    """
    
    def __init__(self, name, object_type):
        super(PointerType, self).__init__(name, byte_size=4)
        self._object_type = object_type
    
    @property
    def object_type(self):
        return self._object_type
    
    def decode(self, data):
        value, = struct.unpack_from("<L", data)
        return value
    
    def encode(self, value):
        return struct.pack("<L", value)
    
    def __repr__(self):
        return self._get_repr("obj={}".format(repr(self._object_type)))

class ArrayType(DataType):
    def __init__(self, name, element_type, length):
        super(ArrayType, self).__init__(name, byte_size=element_type.byte_size * length)
        self._element_type = element_type
        self._length = length
    
    @property
    def length(self):
        return self._length
    
    @property
    def element_type(self):
        return self._element_type
    
    def decode(self, data):
        value = []
        for i in range(self._length):
            value.append(self._element_type.decode(data))
            data = data[self._element_type.byte_size:]
        return value
    
    def encode(self, value):
        assert len(value) == self._length, "array value is incorrect size"
        data = bytestring()
        for v in value:
           data += self._element_type.encode(v)
        return data
    
    def __repr__(self):
        return self._get_repr("n={} elem={}".format(self.length, repr(self._element_type)))

StructMember = namedtuple("StructMember", ["name", "offset", "type"])

class StructType(DataType):
    def __init__(self, name, byte_size):
        super(StructType, self).__init__(name, byte_size=byte_size)
        self._members = OrderedDict()
    
    @property
    def members(self):
        return self._members
    
    def add_member(self, name, offset, member_type):
        """! @brief Add a new member to the struct.
        
        Members must be added in offset order.
        """
        self._members[name] = StructMember(name, offset, member_type)
    
    def __repr__(self):
        members_info = ""
        for _, info in self.members.items():
            members_info += "{}@{:#x}: {}\n".format(info.name, info.offset, repr(info.type))
        return self._get_repr("members=[" + members_info + "]")

EnumMember = namedtuple("EnumMember", ["name", "value"])
    
class EnumerationType(DataType):
    def __init__(self, name, byte_size, enum_type):
        super(EnumerationType, self).__init__(name, byte_size=byte_size)
        self._enum_type = enum_type
        self._enumerators = OrderedDict()
    
    @property
    def enum_type(self):
        return self._enum_type
    
    @property
    def enumerators(self):
        return self._enumerators
    
    def add_enumerator(self, name, value):
        """! @brief Add a new enumerator to the enum.
        
        Enumerators retain their declaration order.
        """
        self._enumerators[name] = EnumMember(name, value)
    
    def __repr__(self):
        members_info = ""
        for _, info in self.enumerators.items():
            members_info += "{}={}, ".format(info.name, info.value)
        return self._get_repr("type=" + repr(self.enum_type) + " members=[" + members_info + "]")




