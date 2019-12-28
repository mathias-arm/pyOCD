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

import logging
import six

from ..utility import conversion

LOG = logging.getLogger(__name__)

## @brief Map from register name to register index.
#
# For most registers, the value is the DCRSR register index. Those registers not directly supported
# by the DCRSR have special values that are interpreted by the register read/write methods.
#
# The CONTROL, FAULTMASK, BASEPRI, and PRIMASK registers are special in that they share the
# same DCRSR register index and are returned as a single value. In this dict, these registers
# have negative values to signal to the register read/write functions that special handling
# is necessary. The values are the byte number containing the register value, plus 1 and then
# negated. So -1 means a mask of 0xff, -2 is 0xff00, and so on. The actual DCRSR register index
# for these combined registers has the key of 'cfbp'.
#
# XPSR is always read in its entirety via the debug interface, but we also provide
# aliases for the submasks APSR, IPSR and EPSR. These are encoded as 0x10000 plus 3 lower bits
# indicating which parts of the PSR we're interested in - encoded the same way as MRS's SYSm.
# (Note that 'XPSR' continues to denote the raw 32 bits of the register, as per previous versions,
# not the union of the three APSR+IPSR+EPSR masks which don't cover the entire register).
#
# The double-precision floating point registers (D0-D15) are composed of two single-precision
# floating point registers (S0-S31). The value for double-precision registers in this dict is
# the negated value of the first associated single-precision register.
CORE_REGISTER = {
                 'r0': 0,
                 'r1': 1,
                 'r2': 2,
                 'r3': 3,
                 'r4': 4,
                 'r5': 5,
                 'r6': 6,
                 'r7': 7,
                 'r8': 8,
                 'r9': 9,
                 'r10': 10,
                 'r11': 11,
                 'r12': 12,
                 'sp': 13,
                 'r13': 13,
                 'lr': 14,
                 'r14': 14,
                 'pc': 15,
                 'r15': 15,
                 'xpsr': 16,
                 'apsr': 0x10000,
                 'iapsr': 0x10001,
                 'eapsr': 0x10002,
                 'ipsr': 0x10005,
                 'epsr': 0x10006,
                 'iepsr': 0x10007,
                 'msp': 17,
                 'psp': 18,
                 'cfbp': 20,
                 'control':-4,
                 'faultmask':-3,
                 'basepri':-2,
                 'primask':-1,
                 'fpscr': 33,
                 's0': 0x40,
                 's1': 0x41,
                 's2': 0x42,
                 's3': 0x43,
                 's4': 0x44,
                 's5': 0x45,
                 's6': 0x46,
                 's7': 0x47,
                 's8': 0x48,
                 's9': 0x49,
                 's10': 0x4a,
                 's11': 0x4b,
                 's12': 0x4c,
                 's13': 0x4d,
                 's14': 0x4e,
                 's15': 0x4f,
                 's16': 0x50,
                 's17': 0x51,
                 's18': 0x52,
                 's19': 0x53,
                 's20': 0x54,
                 's21': 0x55,
                 's22': 0x56,
                 's23': 0x57,
                 's24': 0x58,
                 's25': 0x59,
                 's26': 0x5a,
                 's27': 0x5b,
                 's28': 0x5c,
                 's29': 0x5d,
                 's30': 0x5e,
                 's31': 0x5f,
                 'd0': -0x40,
                 'd1': -0x42,
                 'd2': -0x44,
                 'd3': -0x46,
                 'd4': -0x48,
                 'd5': -0x4a,
                 'd6': -0x4c,
                 'd7': -0x4e,
                 'd8': -0x50,
                 'd9': -0x52,
                 'd10': -0x54,
                 'd11': -0x56,
                 'd12': -0x58,
                 'd13': -0x5a,
                 'd14': -0x5c,
                 'd15': -0x5e,
                 }

# Program Status Register
APSR_MASK = 0xF80F0000
EPSR_MASK = 0x0700FC00
IPSR_MASK = 0x000001FF

class CoreRegisterInfo(object):
    """! @brief Useful information about a core register.
    
    Provides properties for classification of the register, and utilities to convert to and from
    the raw integer representation of the register value.
    
    Each core register has both a name (string), which is always lowercase, and an integer index.
    For most registers, the index is the value written to the DCRSR register to read or write the
    core register. Other core registers not directly supported by DCRSR have special index values.
    """
    
    @staticmethod
    def get(reg):
        """! @brief Return the CoreRegisterInfo instance for a register."""
        if isinstance(reg, six.string_types):
            reg = reg.lower()

        try:
            return _CORE_REGISTERS_INFO[reg]
        except KeyError as err:
            six.raise_from(KeyError('unknown core register %s' % reg), err)

    @staticmethod
    def register_name_to_index(reg):
        """! @brief Convert a register name to integer register index."""
        if isinstance(reg, six.string_types):
            try:
                reg = CORE_REGISTER[reg.lower()]
            except KeyError as err:
                six.raise_from(KeyError('unknown core register name %s' % reg), err)
        return reg

    def __init__(self, name, bitsize, reg_type, reg_group):
        """! @brief Constructor."""
        self._name = name
        self._index = CORE_REGISTER[name]
        self._bitsize = bitsize
        self._gdb_type = reg_type
        self._group = reg_group

    @property
    def name(self):
        """! @brief Name of the register. Always lowercase."""
        return self._name
    
    @property
    def index(self):
        """! @brief Integer index of the register."""
        return self._index
    
    @property
    def bitsize(self):
        """! @brief Bit width of the register.."""
        return self._bitsize
    
    @property
    def group(self):
        """! @brief Named group the register is contained within."""
        return self._group
    
    @property
    def gdb_type(self):
        """! @brief Value type specific to gdb."""
        return self._gdb_type

    @property
    def is_float_register(self):
        """! @brief Returns true for registers single or double precision float registers (but not FPSCR)."""
        return self.is_single_float_register or self.is_double_float_register

    @property
    def is_single_float_register(self):
        """! @brief Returns true for registers holding single-precision float values"""
        return 0x40 <= self.index <= 0x5f

    @property
    def is_double_float_register(self):
        """! @brief Returns true for registers holding double-precision float values"""
        return -0x40 >= self.index > -0x60

    @property
    def is_fpu_register(self):
        """! @brief Returns true for FPSCR, SP, or DP registers."""
        return self.index == 33 or self.is_float_register

    @property
    def is_cfbp_subregister(self):
        """! @brief Whether the register is one of those combined into CFBP by the DCSR."""
        return -4 <= self.index <= -1

    @property
    def is_psr_subregister(self):
        """! @brief Whether the register is a combination of xPSR fields."""
        return 0x10000 <= self.index <= 0x10007

    @property
    def psr_mask(self):
        """! @brief Generate a PSR mask based on bottom 3 bits of a MRS SYSm value"""
        mask = 0
        if (self.index & 1) != 0:
            mask |= IPSR_MASK
        if (self.index & 2) != 0:
            mask |= EPSR_MASK
        if (self.index & 4) == 0:
            mask |= APSR_MASK
        return mask
    
    def from_raw(self, value):
        """! @brief Convert register value from raw (integer) to canonical type."""
        # Convert int to float.
        if self.is_single_float_register:
            value = conversion.u32_to_float32(value)
        elif self.is_double_float_register:
            value = conversion.u64_to_float64(value)
        return value
    
    def to_raw(self, value):
        """! @brief Convert register value from canonical type to raw (integer)."""
        # Convert float to int.
        if isinstance(value, float):
            if self.is_single_float_register:
                value = conversion.float32_to_u32(value)
            elif self.is_double_float_register:
                value = conversion.float64_to_u64(value)
            else:
                raise TypeError("non-float register value has float type")
        return value

class CoreRegisterGroups:
    """! @brief Namespace for lists of register information."""
    
    GENERAL = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('r0',      32,         'int',          'general'),
        CoreRegisterInfo('r1',      32,         'int',          'general'),
        CoreRegisterInfo('r2',      32,         'int',          'general'),
        CoreRegisterInfo('r3',      32,         'int',          'general'),
        CoreRegisterInfo('r4',      32,         'int',          'general'),
        CoreRegisterInfo('r5',      32,         'int',          'general'),
        CoreRegisterInfo('r6',      32,         'int',          'general'),
        CoreRegisterInfo('r7',      32,         'int',          'general'),
        CoreRegisterInfo('r8',      32,         'int',          'general'),
        CoreRegisterInfo('r9',      32,         'int',          'general'),
        CoreRegisterInfo('r10',     32,         'int',          'general'),
        CoreRegisterInfo('r11',     32,         'int',          'general'),
        CoreRegisterInfo('r12',     32,         'int',          'general'),
        CoreRegisterInfo('sp',      32,         'data_ptr',     'general'),
        CoreRegisterInfo('lr',      32,         'int',          'general'),
        CoreRegisterInfo('pc',      32,         'code_ptr',     'general'),
        CoreRegisterInfo('msp',     32,         'data_ptr',     'system'),
        CoreRegisterInfo('psp',     32,         'data_ptr',     'system'),
        CoreRegisterInfo('primask', 32,         'int',          'system'),
        ]

    XPSR_CONTROL_PLAIN = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('xpsr',    32,         'int',          'general'),
        CoreRegisterInfo('control', 32,         'int',          'system'),
        ]

    XPSR_CONTROL_FIELDS = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('xpsr',    32,         'xpsr',         'general'),
        CoreRegisterInfo('control', 32,         'control',      'system'),
        ]

    SYSTEM_V7M_ONLY = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('basepri',     32,     'int',          'system'),
        CoreRegisterInfo('faultmask',   32,     'int',          'system'),
        ]
    
    CFBP = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('cfbp',    32,         'int',          'system'),
        ]
    
    ALL_PSR = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('apsr',    32,         'int',          'system'),
        CoreRegisterInfo('iapsr',   32,         'int',          'system'),
        CoreRegisterInfo('eapsr',   32,         'int',          'system'),
        CoreRegisterInfo('ipsr',    32,         'int',          'system'),
        CoreRegisterInfo('epsr',    32,         'int',          'system'),
        CoreRegisterInfo('iepsr',   32,         'int',          'system'),
        ]

    FLOAT_FPSCR = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('fpscr',   32,         'int',          'float'),
        ]

    FLOAT_SP = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('s0' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s1' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s2' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s3' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s4' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s5' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s6' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s7' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s8' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s9' ,     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s10',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s11',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s12',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s13',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s14',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s15',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s16' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s17' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s18' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s19' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s20' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s21' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s22' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s23' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s24' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s25' ,    32,         'ieee_single',  'float'),
        CoreRegisterInfo('s26',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s27',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s28',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s29',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s30',     32,         'ieee_single',  'float'),
        CoreRegisterInfo('s31',     32,         'ieee_single',  'float'),
        ]

    FLOAT_DP = [
        #                Name       bitsize     type            group
        CoreRegisterInfo('d0' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d1' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d2' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d3' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d4' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d5' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d6' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d7' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d8' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d9' ,     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d10',     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d11',     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d12',     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d13',     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d14',     64,         'ieee_double',  'float'),
        CoreRegisterInfo('d15',     64,         'ieee_double',  'float'),
        ]

## Map of info for all defined registers.
_CORE_REGISTERS_INFO = {}

# Build info map.
def _build_reg_info():
    all_regs = (CoreRegisterGroups.GENERAL
                + CoreRegisterGroups.XPSR_CONTROL_PLAIN
                + CoreRegisterGroups.SYSTEM_V7M_ONLY
                + CoreRegisterGroups.CFBP
                + CoreRegisterGroups.ALL_PSR
                + CoreRegisterGroups.FLOAT_FPSCR
                + CoreRegisterGroups.FLOAT_SP
                + CoreRegisterGroups.FLOAT_DP)
    for reg in all_regs:
        _CORE_REGISTERS_INFO[reg.name] = reg
        _CORE_REGISTERS_INFO[reg.index] = reg
        
_build_reg_info()
