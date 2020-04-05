# pyOCD debugger
# Copyright (c) 2006-2019 Arm Limited
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
from time import (time, sleep)
from xml.etree.ElementTree import (Element, SubElement, tostring)

from ..core.target import Target
from ..core import exceptions
from ..utility import (cmdline, conversion, timeout)
from ..utility.notification import Notification
from .component import CoreSightCoreComponent
from .fpb import FPB
from .dwt import DWT
from .core_ids import CORE_TYPE_NAME
from .core_registers import (
    CORE_REGISTER,
    CoreRegisterInfo,
    CoreRegisterGroups,
    )
from ..debug.breakpoints.manager import BreakpointManager
from ..debug.breakpoints.software import SoftwareBreakpointProvider

LOG = logging.getLogger(__name__)

class CortexM(Target, CoreSightCoreComponent):
    """! @brief CoreSight component for a v6-M or v7-M Cortex-M core.
    
    This class has basic functions to access a Cortex-M core:
       - init
       - read/write memory
       - read/write core registers
       - set/remove hardware breakpoints
    """

    # Program Status Register
    APSR_MASK = 0xF80F0000
    EPSR_MASK = 0x0700FC00
    IPSR_MASK = 0x000001FF
    
    # Thumb bit in XPSR.
    XPSR_THUMB = 0x01000000

    # Control Register
    CONTROL_FPCA = (1 << 2)
    CONTROL_SPSEL = (1 << 1)
    CONTROL_nPRIV = (1 << 0)

    # Debug Fault Status Register
    DFSR = 0xE000ED30
    DFSR_PMU = (1 << 5)
    DFSR_EXTERNAL = (1 << 4)
    DFSR_VCATCH = (1 << 3)
    DFSR_DWTTRAP = (1 << 2)
    DFSR_BKPT = (1 << 1)
    DFSR_HALTED = (1 << 0)

    # Debug Exception and Monitor Control Register
    DEMCR = 0xE000EDFC
    # DWTENA in armv6 architecture reference manual
    DEMCR_TRCENA = (1 << 24)
    DEMCR_VC_HARDERR = (1 << 10)
    DEMCR_VC_INTERR = (1 << 9)
    DEMCR_VC_BUSERR = (1 << 8)
    DEMCR_VC_STATERR = (1 << 7)
    DEMCR_VC_CHKERR = (1 << 6)
    DEMCR_VC_NOCPERR = (1 << 5)
    DEMCR_VC_MMERR = (1 << 4)
    DEMCR_VC_CORERESET = (1 << 0)

    # CPUID Register
    CPUID = 0xE000ED00

    # CPUID masks
    CPUID_IMPLEMENTER_MASK = 0xff000000
    CPUID_IMPLEMENTER_POS = 24
    CPUID_VARIANT_MASK = 0x00f00000
    CPUID_VARIANT_POS = 20
    CPUID_ARCHITECTURE_MASK = 0x000f0000
    CPUID_ARCHITECTURE_POS = 16
    CPUID_PARTNO_MASK = 0x0000fff0
    CPUID_PARTNO_POS = 4
    CPUID_REVISION_MASK = 0x0000000f
    CPUID_REVISION_POS = 0

    CPUID_IMPLEMENTER_ARM = 0x41
    ARMv6M = 0xC # also ARMv8-M without Main Extension
    ARMv7M = 0xF # also ARMv8-M with Main Extension

    # Debug Core Register Selector Register
    DCRSR = 0xE000EDF4
    DCRSR_REGWnR = (1 << 16)
    DCRSR_REGSEL = 0x1F

    # Debug Halting Control and Status Register
    DHCSR = 0xE000EDF0
    C_DEBUGEN = (1 << 0)
    C_HALT = (1 << 1)
    C_STEP = (1 << 2)
    C_MASKINTS = (1 << 3)
    C_SNAPSTALL = (1 << 5)
    S_REGRDY = (1 << 16)
    S_HALT = (1 << 17)
    S_SLEEP = (1 << 18)
    S_LOCKUP = (1 << 19)
    S_RETIRE_ST = (1 << 24)
    S_RESET_ST = (1 << 25)

    # Debug Core Register Data Register
    DCRDR = 0xE000EDF8

    # Coprocessor Access Control Register
    CPACR = 0xE000ED88
    CPACR_CP10_CP11_MASK = (3 << 20) | (3 << 22)
    
    # Interrupt Control and State Register
    ICSR = 0xE000ED04
    ICSR_PENDSVCLR = (1 << 27)
    ICSR_PENDSTCLR = (1 << 25)
    
    VTOR = 0xE000ED08
    SCR = 0xE000ED10
    SHPR1 = 0xE000ED18
    SHPR2 = 0xE000ED1C
    SHPR3 = 0xE000ED20
    SHCSR = 0xE000ED24
    FPCCR = 0xE000EF34
    FPCAR = 0xE000EF38
    FPDSCR = 0xE000EF3C
    ICTR = 0xE000E004

    NVIC_AIRCR = (0xE000ED0C)
    NVIC_AIRCR_VECTKEY = (0x5FA << 16)
    NVIC_AIRCR_VECTRESET = (1 << 0)
    NVIC_AIRCR_VECTCLRACTIVE = (1 << 1)
    NVIC_AIRCR_SYSRESETREQ = (1 << 2)
    NVIC_AIRCR_PRIGROUP_MASK = 0x700
    NVIC_AIRCR_PRIGROUP_SHIFT = 8
    
    NVIC_ICER0 = 0xE000E180 # NVIC Clear-Enable Register 0
    NVIC_ICPR0 = 0xE000E280 # NVIC Clear-Pending Register 0
    NVIC_IPR0 = 0xE000E400 # NVIC Interrupt Priority Register 0
    
    SYSTICK_CSR = 0xE000E010

    DBGKEY = (0xA05F << 16)

    # Media and FP Feature Register 0
    MVFR0 = 0xE000EF40
    MVFR0_DOUBLE_PRECISION_MASK = 0x00000f00
    MVFR0_DOUBLE_PRECISION_SHIFT = 8

    # Media and FP Feature Register 2
    MVFR2 = 0xE000EF48
    MVFR2_VFP_MISC_MASK = 0x000000f0
    MVFR2_VFP_MISC_SHIFT = 4

    @classmethod
    def factory(cls, ap, cmpid, address):
        # Create a new core instance.
        root = ap.dp.target
        core = cls(root.session, ap, root.memory_map, root._new_core_num, cmpid, address) 
        
        # Associate this core with the AP.
        if ap.core is not None:
            raise exceptions.TargetError("AP#%d has multiple cores associated with it" % ap.ap_num)
        ap.core = core
        
        # Add the new core to the root target.
        root.add_core(core)
        
        root._new_core_num += 1
        
        return core

    def __init__(self, session, ap, memoryMap=None, core_num=0, cmpid=None, address=None):
        Target.__init__(self, session, memoryMap)
        CoreSightCoreComponent.__init__(self, ap, cmpid, address)

        self.arch = 0
        self.core_type = 0
        self.has_fpu = False
        self.core_number = core_num
        self._run_token = 0
        self._target_context = None
        self._elf = None
        self.target_xml = None
        self._core_registers = {}
        self._supports_vectreset = False
        self._reset_catch_delegate_result = False
        self._reset_catch_saved_demcr = 0
        self.fpb = None
        self.dwt = None
        
        # Default to software reset using the default software reset method.
        self._default_reset_type = Target.ResetType.SW
        
        # Select default sw reset type based on whether multicore debug is enabled and which core
        # this is.
        self._default_software_reset_type = Target.ResetType.SW_SYSRESETREQ \
                    if (not self.session.options.get('enable_multicore_debug')) or (self.core_number == 0) \
                    else Target.ResetType.SW_VECTRESET

        # Set up breakpoints manager.
        self.sw_bp = SoftwareBreakpointProvider(self)
        self.bp_manager = BreakpointManager(self)
        self.bp_manager.add_provider(self.sw_bp)

    def add_child(self, cmp):
        """! @brief Connect related CoreSight components."""
        super(CortexM, self).add_child(cmp)
        
        if isinstance(cmp, FPB):
            self.fpb = cmp
            self.bp_manager.add_provider(cmp)
        elif isinstance(cmp, DWT):
            self.dwt = cmp

    @property
    def core_registers(self):
        """! @brief Read-only dictionary of available core registers.
        
        The primary keys are the register names (all lowercase), values are @reg
        pyocd.coresight.core_registers.CoreRegisterInfo "CoreRegisterInfo" instances.
        The integer indexes for each register are also available as keys.
        """
        return self._core_registers

    @property
    def elf(self):
        return self._elf

    @elf.setter
    def elf(self, elffile):
        self._elf = elffile
    
    @property
    def default_reset_type(self):
        return self._default_reset_type
    
    @default_reset_type.setter
    def default_reset_type(self, reset_type):
        assert isinstance(reset_type, Target.ResetType)
        self._default_reset_type = reset_type
    
    @property
    def default_software_reset_type(self):
        return self._default_software_reset_type
    
    @default_software_reset_type.setter
    def default_software_reset_type(self, reset_type):
        """! @brief Modify the default software reset method.
        @param self
        @param reset_type Must be one of the software reset types: Target.ResetType.SW_SYSRESETREQ,
            Target.ResetType.SW_VECTRESET, or Target.ResetType.SW_EMULATED.
        """
        assert isinstance(reset_type, Target.ResetType)
        assert reset_type in (Target.ResetType.SW_SYSRESETREQ, Target.ResetType.SW_VECTRESET,
                                Target.ResetType.SW_EMULATED)
        self._default_software_reset_type = reset_type
    
    @property
    def supported_security_states(self):
        """! @brief Tuple of security states supported by the processor.
        
        @return Tuple of @ref pyocd.core.target.Target.SecurityState "Target.SecurityState". For
            v6-M and v7-M cores, the return value only contains SecurityState.NONSECURE.
        """
        return (Target.SecurityState.NONSECURE,)

    def init(self):
        """! @brief Cortex M initialization.
        
        The bus must be accessible when this method is called.
        """
        if not self.call_delegate('will_start_debug_core', core=self):
            self._read_core_type()
            self._check_for_fpu()
            self._build_registers()
            self.sw_bp.init()

        self.call_delegate('did_start_debug_core', core=self)

    def disconnect(self, resume=True):
        if not self.call_delegate('will_stop_debug_core', core=self):
            # Remove breakpoints and watchpoints.
            self.bp_manager.remove_all_breakpoints()
            if self.dwt is not None:
                self.dwt.remove_all_watchpoints()

            # Disable other debug blocks.
            self.write32(CortexM.DEMCR, 0)

            # Disable core debug.
            if resume:
                self.resume()
                self.write32(CortexM.DHCSR, CortexM.DBGKEY | 0x0000)

        self.call_delegate('did_stop_debug_core', core=self)

    def _build_registers(self):
        """! @brief Build set of core registers and gdb target XML"""
        xml_root = Element('target')
        xml_regs_general = SubElement(xml_root, "feature", name="org.gnu.gdb.arm.m-profile")
        
        def append_regs(regs, xml_element):
            for reg in regs:
                self._core_registers[reg.name] = reg
                self._core_registers[reg.index] = reg
                if xml_element is not None:
                    SubElement(xml_element, 'reg', name=reg.name, bitsize=str(reg.bitsize),
                            type=reg.gdb_type, group=reg.group)

        # Add general purpose registers.
        append_regs(CoreRegisterGroups.GENERAL, xml_regs_general)
        
        # Depending on the xpsr_control_fields setting, the XPSR and CONTROL registers are
        # added as either plain int regs or structured registers with fields defined in the XML.
        if self.session.options.get('xpsr_control_fields'):
            # Define XPSR and CONTROL register fields.
            control = SubElement(xml_regs_general, 'flags', id="control", size="4")
            SubElement(control, "field", name="nPRIV", start="0", end="0", type="bool")
            SubElement(control, "field", name="SPSEL", start="1", end="1", type="bool")
            if self.has_fpu:
                SubElement(control, "field", name="FPCS", start="2", end="2", type="bool")

            apsr = SubElement(xml_regs_general, 'flags', id="apsr", size="4")
            SubElement(apsr, "field", name="N", start="31", end="31", type="bool")
            SubElement(apsr, "field", name="Z", start="30", end="30", type="bool")
            SubElement(apsr, "field", name="C", start="29", end="29", type="bool")
            SubElement(apsr, "field", name="V", start="28", end="28", type="bool")
            SubElement(apsr, "field", name="Q", start="27", end="27", type="bool")

            ipsr = SubElement(xml_regs_general, 'struct', id="ipsr", size="4")
            SubElement(ipsr, "field", name="EXC", start="0", end="8", type="int")
        
            xpsr = SubElement(xml_regs_general, 'union', id="xpsr")
            SubElement(xpsr, "field", name="xpsr", type="uint32")
            SubElement(xpsr, "field", name="apsr", type="apsr")
            SubElement(xpsr, "field", name="ipsr", type="ipsr")
            
            append_regs(CoreRegisterGroups.XPSR_CONTROL_FIELDS, xml_regs_general)
        else:
            # Add XPSR and CONTROL as plain int registers.
            append_regs(CoreRegisterGroups.XPSR_CONTROL_PLAIN, xml_regs_general)
        
        # Check if target has ARMv7 registers
        if self.arch == CortexM.ARMv7M:
            append_regs(CoreRegisterGroups.SYSTEM_V7M_ONLY, xml_regs_general)
        # Check if target has FPU registers
        if self.has_fpu:
            # GDB understands the double/single separation so we don't need
            # to separately pass the single regs, just the double
            xml_regs_fpu = SubElement(xml_root, "feature", name="org.gnu.gdb.arm.vfp")
            append_regs(CoreRegisterGroups.FLOAT_FPSCR, xml_regs_fpu)
            append_regs(CoreRegisterGroups.FLOAT_DP, xml_regs_fpu)
            
            # Add the SP registers to our internal list.
            append_regs(CoreRegisterGroups.FLOAT_SP, None)

        self.target_xml = b'<?xml version="1.0"?><!DOCTYPE feature SYSTEM "gdb-target.dtd">' + tostring(xml_root)

    def _read_core_type(self):
        """! @brief Read the CPUID register and determine core type and architecture."""
        # Read CPUID register
        cpuid = self.read32(CortexM.CPUID)

        implementer = (cpuid & CortexM.CPUID_IMPLEMENTER_MASK) >> CortexM.CPUID_IMPLEMENTER_POS
        if implementer != CortexM.CPUID_IMPLEMENTER_ARM:
            LOG.warning("CPU implementer is not ARM!")

        self.arch = (cpuid & CortexM.CPUID_ARCHITECTURE_MASK) >> CortexM.CPUID_ARCHITECTURE_POS
        self.core_type = (cpuid & CortexM.CPUID_PARTNO_MASK) >> CortexM.CPUID_PARTNO_POS
        
        self.cpu_revision = (cpuid & CortexM.CPUID_VARIANT_MASK) >> CortexM.CPUID_VARIANT_POS
        self.cpu_patch = (cpuid & CortexM.CPUID_REVISION_MASK) >> CortexM.CPUID_REVISION_POS
        
        # Only v7-M supports VECTRESET.
        if self.arch == CortexM.ARMv7M:
            self._supports_vectreset = True
        
        if self.core_type in CORE_TYPE_NAME:
            LOG.info("CPU core #%d is %s r%dp%d", self.core_number, CORE_TYPE_NAME[self.core_type], self.cpu_revision, self.cpu_patch)
        else:
            LOG.warning("CPU core #%d type is unrecognized", self.core_number)

    def _check_for_fpu(self):
        """! @brief Determine if a core has an FPU.
        
        The core architecture must have been identified prior to calling this function.
        """
        if self.arch != CortexM.ARMv7M:
            self.has_fpu = False
            return

        originalCpacr = self.read32(CortexM.CPACR)
        cpacr = originalCpacr | CortexM.CPACR_CP10_CP11_MASK
        self.write32(CortexM.CPACR, cpacr)

        cpacr = self.read32(CortexM.CPACR)
        self.has_fpu = (cpacr & CortexM.CPACR_CP10_CP11_MASK) != 0

        # Restore previous value.
        self.write32(CortexM.CPACR, originalCpacr)

        if self.has_fpu:
            # Now check whether double-precision is supported.
            # (Minimal tests to distinguish current permitted ARMv7-M and
            # ARMv8-M FPU types; used for printing only).
            mvfr0 = self.read32(CortexM.MVFR0)
            dp_val = (mvfr0 & CortexM.MVFR0_DOUBLE_PRECISION_MASK) >> CortexM.MVFR0_DOUBLE_PRECISION_SHIFT

            mvfr2 = self.read32(CortexM.MVFR2)
            vfp_misc_val = (mvfr2 & CortexM.MVFR2_VFP_MISC_MASK) >> CortexM.MVFR2_VFP_MISC_SHIFT

            if dp_val >= 2:
                fpu_type = "FPv5"
            elif vfp_misc_val >= 4:
                fpu_type = "FPv5-SP"
            else:
                fpu_type = "FPv4-SP"
            LOG.info("FPU present: " + fpu_type)

    def write_memory(self, addr, value, transfer_size=32):
        """! @brief Write a single memory location.
        
        By default the transfer size is a word."""
        self.ap.write_memory(addr, value, transfer_size)

    def read_memory(self, addr, transfer_size=32, now=True):
        """! @brief Read a memory location.
        
        By default, a word will be read."""
        result = self.ap.read_memory(addr, transfer_size, now)

        # Read callback returned for async reads.
        def read_memory_cb():
            return self.bp_manager.filter_memory(addr, transfer_size, result())

        if now:
            return self.bp_manager.filter_memory(addr, transfer_size, result)
        else:
            return read_memory_cb

    def read_memory_block8(self, addr, size):
        """! @brief Read a block of unaligned bytes in memory.
        @return an array of byte values
        """
        data = self.ap.read_memory_block8(addr, size)
        return self.bp_manager.filter_memory_unaligned_8(addr, size, data)

    def write_memory_block8(self, addr, data):
        """! @brief Write a block of unaligned bytes in memory."""
        self.ap.write_memory_block8(addr, data)

    def write_memory_block32(self, addr, data):
        """! @brief Write an aligned block of 32-bit words."""
        self.ap.write_memory_block32(addr, data)

    def read_memory_block32(self, addr, size):
        """! @brief Read an aligned block of 32-bit words."""
        data = self.ap.read_memory_block32(addr, size)
        return self.bp_manager.filter_memory_aligned_32(addr, size, data)

    def halt(self):
        """! @brief Halt the core
        """
        LOG.debug("halting core %d", self.core_number)

        self.session.notify(Target.Event.PRE_HALT, self, Target.HaltReason.USER)
        self.write_memory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN | CortexM.C_HALT)
        self.flush()
        self.session.notify(Target.Event.POST_HALT, self, Target.HaltReason.USER)

    def step(self, disable_interrupts=True, start=0, end=0):
        """! @brief Perform an instruction level step.
        
        This function preserves the previous interrupt mask state.
        """
        # Was 'if self.get_state() != TARGET_HALTED:'
        # but now value of dhcsr is saved
        dhcsr = self.read_memory(CortexM.DHCSR)
        if not (dhcsr & (CortexM.C_STEP | CortexM.C_HALT)):
            LOG.error('cannot step: target not halted')
            return

        LOG.debug("step core %d", self.core_number)

        self.session.notify(Target.Event.PRE_RUN, self, Target.RunType.STEP)

        self.clear_debug_cause_bits()

        # Save previous interrupt mask state
        interrupts_masked = (CortexM.C_MASKINTS & dhcsr) != 0

        # Mask interrupts - C_HALT must be set when changing to C_MASKINTS
        if not interrupts_masked and disable_interrupts:
            self.write_memory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN | CortexM.C_HALT | CortexM.C_MASKINTS)

        # Single step using current C_MASKINTS setting
        while True:
            if disable_interrupts or interrupts_masked:
                self.write_memory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN | CortexM.C_MASKINTS | CortexM.C_STEP)
            else:
                self.write_memory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN | CortexM.C_STEP)

            # Wait for halt to auto set (This should be done before the first read)
            while not self.read_memory(CortexM.DHCSR) & CortexM.C_HALT:
                pass

            # Range is empty, 'range step' will degenerate to 'step'
            if start == end:
                break

            # Read program counter and compare to [start, end)
            program_counter = self.read_core_register('pc')
            if program_counter < start or end <= program_counter:
                break

            # Check other stop reasons
            if self.read_memory(CortexM.DFSR) & (CortexM.DFSR_DWTTRAP | CortexM.DFSR_BKPT):
                break
	
        # Restore interrupt mask state
        if not interrupts_masked and disable_interrupts:
            # Unmask interrupts - C_HALT must be set when changing to C_MASKINTS
            self.write_memory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN | CortexM.C_HALT)

        self.flush()

        self._run_token += 1

        self.session.notify(Target.Event.POST_RUN, self, Target.RunType.STEP)

    def clear_debug_cause_bits(self):
        self.write_memory(CortexM.DFSR, CortexM.DFSR_VCATCH | CortexM.DFSR_DWTTRAP | CortexM.DFSR_BKPT | CortexM.DFSR_HALTED)
    
    def _perform_emulated_reset(self):
        """! @brief Emulate a software reset by writing registers.
        
        All core registers are written to reset values. This includes setting the initial PC and SP
        to values read from the vector table, which is assumed to be located at the based of the
        boot memory region.
        
        If the memory map does not provide a boot region, then the current value of the VTOR register
        is reused, as it should at least point to a valid vector table.
        
        The current value of DEMCR.VC_CORERESET determines whether the core will be resumed or
        left halted.
        
        Note that this reset method will not set DHCSR.S_RESET_ST or DFSR.VCATCH.
        """
        # Halt the core before making changes.
        self.halt()
        
        bootMemory = self.memory_map.get_boot_memory()
        if bootMemory is None:
            # Reuse current VTOR value if we don't know the boot memory region.
            vectorBase = self.read32(self.VTOR)
        else:
            vectorBase = bootMemory.start
        
        # Read initial SP and PC.
        initialSp = self.read32(vectorBase)
        initialPc = self.read32(vectorBase + 4)
        
        # Init core registers.
        regList = ['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8', 'r9', 'r10', 'r11', 'r12',
                    'psp', 'msp', 'lr', 'pc', 'xpsr', 'cfbp']
        valueList = [0] * 13 + \
                    [
                        0,          # PSP
                        initialSp,  # MSP
                        0xffffffff, # LR
                        initialPc,  # PC
                        0x01000000, # XPSR
                        0,          # CFBP
                    ]
        
        if self.has_fpu:
            regList += [('s%d' % n) for n in range(32)] + ['fpscr']
            valueList += [0] * 33
        
        self.write_core_registers_raw(regList, valueList)
        
        # "Reset" SCS registers.
        data = [
                (self.ICSR_PENDSVCLR | self.ICSR_PENDSTCLR),  # ICSR
                vectorBase,                   # VTOR
                (self.NVIC_AIRCR_VECTKEY | self.NVIC_AIRCR_VECTCLRACTIVE),    # AIRCR
                0,  # SCR
                0,  # CCR
                0,  # SHPR1
                0,  # SHPR2
                0,  # SHPR3
                0,  # SHCSR
                0,  # CFSR
                ]
        self.write_memory_block32(self.ICSR, data)
        self.write32(self.CPACR, 0)
        
        if self.has_fpu:
            data = [
                    0,  # FPCCR
                    0,  # FPCAR
                    0,  # FPDSCR
                    ]
            self.write_memory_block32(self.FPCCR, data)
        
        # "Reset" SysTick.
        self.write_memory_block32(self.SYSTICK_CSR, [0] * 3)
        
        # "Reset" NVIC registers.
        numregs = (self.read32(self.ICTR) & 0xf) + 1
        self.write_memory_block32(self.NVIC_ICER0, [0xffffffff] * numregs)
        self.write_memory_block32(self.NVIC_ICPR0, [0xffffffff] * numregs)
        self.write_memory_block32(self.NVIC_IPR0, [0xffffffff] * (numregs * 8))

    def _get_actual_reset_type(self, reset_type):
        """! @brief Determine the reset type to use given defaults and passed in type."""
        
        # Default to reset_type session option if reset_type parameter is None. If the session
        # option isn't set, then use the core's default reset type.
        if reset_type is None:
            if self.session.options.get('reset_type') is None:
                reset_type = self.default_reset_type
            else:
                try:
                    # Convert session option value to enum.
                    resetOption = self.session.options.get('reset_type')
                    reset_type = cmdline.convert_reset_type(resetOption)
                    
                    # The converted option will be None if the option value is 'default'.
                    if reset_type is None:
                        reset_type = self.default_reset_type
                except ValueError:
                    reset_type = self.default_reset_type
        else:
            assert isinstance(reset_type, Target.ResetType)
        
        # If the reset type is just SW, then use our default software reset type.
        if reset_type is Target.ResetType.SW:
            reset_type = self.default_software_reset_type
        
        # Fall back to emulated sw reset if the vectreset is specified and the core doesn't support it.
        if (reset_type is Target.ResetType.SW_VECTRESET) and (not self._supports_vectreset):
            reset_type = Target.ResetType.SW_EMULATED
        
        return reset_type

    def _perform_reset(self, reset_type):
        """! @brief Perform a reset of the specified type."""
        assert isinstance(reset_type, Target.ResetType)
        if reset_type is Target.ResetType.HW:
            self.session.probe.reset()
        elif reset_type is Target.ResetType.SW_EMULATED:
            self._perform_emulated_reset()
        else:
            if reset_type is Target.ResetType.SW_SYSRESETREQ:
                mask = CortexM.NVIC_AIRCR_SYSRESETREQ
            elif reset_type is Target.ResetType.SW_VECTRESET:
                mask = CortexM.NVIC_AIRCR_VECTRESET
            else:
                raise exceptions.InternalError("unhandled reset type")
        
            try:
                self.write_memory(CortexM.NVIC_AIRCR, CortexM.NVIC_AIRCR_VECTKEY | mask)
                # Without a flush a transfer error can occur
                self.flush()
            except exceptions.TransferError:
                self.flush()

    def reset(self, reset_type=None):
        """! @brief Reset the core.
        
        The reset method is selectable via the reset_type parameter as well as the reset_type
        session option. If the reset_type parameter is not specified or None, then the reset_type
        option will be used. If the option is not set, or if it is set to a value of 'default', the
        the core's default_reset_type property value is used. So, the session option overrides the
        core's default, while the parameter overrides everything.
        
        Note that only v7-M cores support the `VECTRESET` software reset method. If this method
        is chosen but the core doesn't support it, the the reset method will fall back to an
        emulated software reset.
        
        After a call to this function, the core is running.
        """
        self.session.notify(Target.Event.PRE_RESET, self)

        reset_type = self._get_actual_reset_type(reset_type)

        LOG.debug("reset, core %d, type=%s", self.core_number, reset_type.name)

        self._run_token += 1

        # Give the delegate a chance to overide reset. If the delegate returns True, then it
        # handled the reset on its own.
        if not self.call_delegate('will_reset', core=self, reset_type=reset_type):
            self._perform_reset(reset_type)

        self.call_delegate('did_reset', core=self, reset_type=reset_type)
        
        # Now wait for the system to come out of reset. Keep reading the DHCSR until
        # we get a good response with S_RESET_ST cleared, or we time out.
        with timeout.Timeout(2.0) as t_o:
            while t_o.check():
                try:
                    dhcsr = self.read32(CortexM.DHCSR)
                    if (dhcsr & CortexM.S_RESET_ST) == 0:
                        break
                except exceptions.TransferError:
                    self.flush()
                    sleep(0.01)

        self.session.notify(Target.Event.POST_RESET, self)

    def set_reset_catch(self, reset_type=None):
        """! @brief Prepare to halt core on reset."""
        LOG.debug("set reset catch, core %d", self.core_number)

        self._reset_catch_delegate_result = self.call_delegate('set_reset_catch', core=self, reset_type=reset_type)
        
        # Default behaviour if the delegate didn't handle it.
        if not self._reset_catch_delegate_result:
            # Halt the target.
            self.halt()

            # Save CortexM.DEMCR.
            self._reset_catch_saved_demcr = self.read_memory(CortexM.DEMCR)

            # Enable reset vector catch if needed.
            if (self._reset_catch_saved_demcr & CortexM.DEMCR_VC_CORERESET) == 0:
                self.write_memory(CortexM.DEMCR, self._reset_catch_saved_demcr | CortexM.DEMCR_VC_CORERESET)
    
    def clear_reset_catch(self, reset_type=None):
        """! @brief Disable halt on reset."""
        LOG.debug("clear reset catch, core %d", self.core_number)

        self.call_delegate('clear_reset_catch', core=self, reset_type=reset_type)

        if not self._reset_catch_delegate_result:
            # restore vector catch setting
            self.write_memory(CortexM.DEMCR, self._reset_catch_saved_demcr)

    def reset_and_halt(self, reset_type=None):
        """! @brief Perform a reset and stop the core on the reset handler."""
        # Set up reset catch.
        self.set_reset_catch(reset_type)

        # Perform the reset.
        self.reset(reset_type)

        # wait until the unit resets
        with timeout.Timeout(2.0) as t_o:
            while t_o.check():
                if self.get_state() not in (Target.State.RESET, Target.State.RUNNING):
                    break
                sleep(0.01)

        # Make sure the thumb bit is set in XPSR in case the reset handler
        # points to an invalid address.
        xpsr = self.read_core_register('xpsr')
        if xpsr & self.XPSR_THUMB == 0:
            self.write_core_register('xpsr', xpsr | self.XPSR_THUMB)

        # Restore to original state.
        self.clear_reset_catch(reset_type)

    def get_state(self):
        dhcsr = self.read_memory(CortexM.DHCSR)
        if dhcsr & CortexM.S_RESET_ST:
            # Reset is a special case because the bit is sticky and really means
            # "core was reset since last read of DHCSR". We have to re-read the
            # DHCSR, check if S_RESET_ST is still set and make sure no instructions
            # were executed by checking S_RETIRE_ST.
            newDhcsr = self.read_memory(CortexM.DHCSR)
            if (newDhcsr & CortexM.S_RESET_ST) and not (newDhcsr & CortexM.S_RETIRE_ST):
                return Target.State.RESET
        if dhcsr & CortexM.S_LOCKUP:
            return Target.State.LOCKUP
        elif dhcsr & CortexM.S_SLEEP:
            return Target.State.SLEEPING
        elif dhcsr & CortexM.S_HALT:
            return Target.State.HALTED
        else:
            return Target.State.RUNNING
    
    def get_security_state(self):
        """! @brief Returns the current security state of the processor.
        
        @return @ref pyocd.core.target.Target.SecurityState "Target.SecurityState" enumerator. For
            v6-M and v7-M cores, SecurityState.NONSECURE is always returned.
        """
        return Target.SecurityState.NONSECURE

    @property
    def run_token(self):
        return self._run_token

    def is_running(self):
        return self.get_state() == Target.State.RUNNING

    def is_halted(self):
        return self.get_state() == Target.State.HALTED

    def resume(self):
        """! @brief Resume execution of the core.
        """
        if self.get_state() != Target.State.HALTED:
            LOG.debug('cannot resume: target not halted')
            return
        LOG.debug("resuming core %d", self.core_number)
        self.session.notify(Target.Event.PRE_RUN, self, Target.RunType.RESUME)
        self._run_token += 1
        self.clear_debug_cause_bits()
        self.write_memory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN)
        self.flush()
        self.session.notify(Target.Event.POST_RUN, self, Target.RunType.RESUME)

    def find_breakpoint(self, addr):
        return self.bp_manager.find_breakpoint(addr)

    def read_core_register(self, reg):
        """! @brief Read one core register.
        
        @param self
        @param reg Either the register's name in lowercase or an integer register index.
        @return The current value of the register. Most core registers return an integer value,
            while the floating point single and double precision register return a float value.
        
        @exception KeyError Invalid or unsupported register was requested.
        """
        reg_info = self.core_registers[reg]
        regValue = self.read_core_register_raw(reg_info.index)
        return reg_info.from_raw(regValue)

    def read_core_register_raw(self, reg):
        """! @brief Read a core register without type conversion.
        
        @param self
        @param reg Either the register's name in lowercase or an integer register index.
        @return The current integer value of the register. Even float register values are returned
            as integers (thus the "raw").
        
        @exception KeyError Invalid or unsupported register was requested.
        """
        vals = self.read_core_registers_raw([reg])
        return vals[0]

    def read_core_registers_raw(self, reg_list):
        """! @brief Read one or more core registers.
        
        @param self
        @param reg_list List of registers to read. Each element in the list can be either the
            register's name in lowercase or the integer register index.
        @return List of integer values of the registers requested to be read. The result list will
            be the same length as _reg_list_.
        
        @exception KeyError Invalid or unsupported register was requested.
        """
        # convert to index only
        reg_list = [CoreRegisterInfo.register_name_to_index(reg) for reg in reg_list]

        # Sanity check register values
        for reg in reg_list:
            if reg not in self.core_registers:
                # Invalid register, try to give useful error. An invalid name will already
                # have raised a KeyError above.
                if CoreRegisterInfo.get(reg).is_fpu_register and (not self.has_fpu):
                    raise KeyError("attempt to read FPU register without FPU")
                else:
                    raise KeyError("register not available in this CPU")
        
        return self._base_read_core_registers_raw(reg_list)

    def _base_read_core_registers_raw(self, reg_list):
        """! @brief Low-level core register read routine.
        
        Items in the _reg_list_ must be pre-converted to index and only include valid
        registers for the core.
        """
        
        # Handle doubles.
        doubles = [reg for reg in reg_list if CoreRegisterInfo.get(reg).is_double_float_register]
        hasDoubles = len(doubles) > 0
        if hasDoubles:
            originalRegList = reg_list
            
            # Strip doubles from reg_list.
            reg_list = [reg for reg in reg_list if not CoreRegisterInfo.get(reg).is_double_float_register]
            
            # Read float regs required to build doubles.
            singleRegList = []
            for reg in doubles:
                singleRegList += (-reg, -reg + 1)
            singleValues = self._base_read_core_registers_raw(singleRegList)

        # Begin all reads and writes
        dhcsr_cb_list = []
        reg_cb_list = []
        for reg in reg_list:
            if CoreRegisterInfo.get(reg).is_cfbp_subregister:
                reg = CORE_REGISTER['cfbp']
            elif CoreRegisterInfo.get(reg).is_psr_subregister:
                reg = CORE_REGISTER['xpsr']

            # write id in DCRSR
            self.write_memory(CortexM.DCRSR, reg)

            # Technically, we need to poll S_REGRDY in DHCSR here before reading DCRDR. But
            # we're running so slow compared to the target that it's not necessary.
            # Read it and assert that S_REGRDY is set

            dhcsr_cb = self.read_memory(CortexM.DHCSR, now=False)
            reg_cb = self.read_memory(CortexM.DCRDR, now=False)
            dhcsr_cb_list.append(dhcsr_cb)
            reg_cb_list.append(reg_cb)

        # Read all results
        reg_vals = []
        for reg, reg_cb, dhcsr_cb in zip(reg_list, reg_cb_list, dhcsr_cb_list):
            dhcsr_val = dhcsr_cb()
            assert dhcsr_val & CortexM.S_REGRDY
            val = reg_cb()

            # Special handling for registers that are combined into a single DCRSR number.
            if CoreRegisterInfo.get(reg).is_cfbp_subregister:
                val = (val >> ((-reg - 1) * 8)) & 0xff
            elif CoreRegisterInfo.get(reg).is_psr_subregister:
                val &= CoreRegisterInfo.get(reg).psr_mask

            reg_vals.append(val)
        
        # Merge double regs back into result list.
        if hasDoubles:
            results = []
            for reg in originalRegList:
                # Double
                if CoreRegisterInfo.get(reg).is_double_float_register:
                    doubleIndex = doubles.index(reg)
                    singleLow = singleValues[doubleIndex * 2]
                    singleHigh = singleValues[doubleIndex * 2 + 1]
                    double = (singleHigh << 32) | singleLow
                    results.append(double)
                # Other register
                else:
                    results.append(reg_vals[reg_list.index(reg)])
            reg_vals = results

        return reg_vals

    def write_core_register(self, reg, data):
        """! @brief Write a CPU register.
        
        @param self
        @param reg The name of the register to write.
        @param data New value of the register. Float registers accept float values.
        
        @exception KeyError Invalid or unsupported register was requested.
        @exception @ref pyocd.core.exceptions.DebugError "DebugError" Failed to write one or
            more registers.
        """
        reg_info = self.core_registers[reg]
        self.write_core_register_raw(reg_info.index, reg_info.to_raw(data))

    def write_core_register_raw(self, reg, data):
        """! @brief Write a CPU register without type conversion.
        
        @param self
        @param reg The name of the register to write.
        @param data New value of the register. Must be an integer, even for float registers.
        
        @exception KeyError Invalid or unsupported register was requested.
        @exception @ref pyocd.core.exceptions.DebugError "DebugError" Failed to write one or
            more registers.
        """
        self.write_core_registers_raw([reg], [data])

    def write_core_registers_raw(self, reg_list, data_list):
        """! @brief Write one or more core registers.

        @param self
        @param reg_list List of registers to read. Each element in the list can be either the
            register's name in lowercase or the integer register index.
        @param data_list List of values for the registers in the corresponding positions of
            _reg_list_. All values must be integers, even for float registers.
        
        @exception KeyError Invalid or unsupported register was requested.
        @exception @ref pyocd.core.exceptions.DebugError "DebugError" Failed to write one or
            more registers.
        """
        assert len(reg_list) == len(data_list)
        
        # convert to index only
        reg_list = [CoreRegisterInfo.register_name_to_index(reg) for reg in reg_list]

        # Sanity check register values
        for reg in reg_list:
            if reg not in self.core_registers:
                # Invalid register, try to give useful error. An invalid name will already
                # have raised a KeyError above.
                if CoreRegisterInfo.get(reg).is_fpu_register and (not self.has_fpu):
                    raise KeyError("attempt to read FPU register without FPU")
                else:
                    raise KeyError("register not available in this CPU")
        
        self._base_write_core_registers_raw(reg_list, data_list)

    def _base_write_core_registers_raw(self, reg_list, data_list):
        # Read special register if it is present in the list and
        # convert doubles to single float register writes.
        cfbpValue = None
        xpsrValue = None
        reg_data_list = []
        for reg, data in zip(reg_list, data_list):
            if CoreRegisterInfo.get(reg).is_double_float_register:
                # Replace double with two single float register writes. For instance,
                # a write of D2 gets converted to writes to S4 and S5.
                singleLow = data & 0xffffffff
                singleHigh = (data >> 32) & 0xffffffff
                reg_data_list += [(-reg, singleLow), (-reg + 1, singleHigh)]
            elif CoreRegisterInfo.get(reg).is_cfbp_subregister and cfbpValue is None:
                cfbpValue = self._base_read_core_register_raw(CORE_REGISTER['cfbp'])
            elif CoreRegisterInfo.get(reg).is_psr_subregister and xpsrValue is None:
                xpsrValue = self._base_read_core_register_raw(CORE_REGISTER['xpsr'])
            else:
                # Other register, just copy directly.
                reg_data_list.append((reg, data))
        
        # Write out registers
        dhcsr_cb_list = []
        for reg, data in reg_data_list:
            if CoreRegisterInfo.get(reg).is_cfbp_subregister:
                # Mask in the new special register value so we don't modify the other register
                # values that share the same DCRSR number.
                shift = (-reg - 1) * 8
                mask = 0xffffffff ^ (0xff << shift)
                data = (cfbpValue & mask) | ((data & 0xff) << shift)
                cfbpValue = data # update special register for other writes that might be in the list
                reg = CORE_REGISTER['cfbp']
            elif CoreRegisterInfo.get(reg).is_psr_subregister:
                mask = CoreRegisterInfo.get(reg).psr_mask
                data = (xpsrValue & (0xffffffff ^ mask)) | (data & mask)
                xpsrValue = data
                reg = CORE_REGISTER['xpsr']

            # write DCRDR
            self.write_memory(CortexM.DCRDR, data)

            # write id in DCRSR and flag to start write transfer
            self.write_memory(CortexM.DCRSR, reg | CortexM.DCRSR_REGWnR)

            # Technically, we need to poll S_REGRDY in DHCSR here to ensure the
            # register write has completed.
            # Read it and assert that S_REGRDY is set
            dhcsr_cb = self.read_memory(CortexM.DHCSR, now=False)
            dhcsr_cb_list.append(dhcsr_cb)

        # Make sure S_REGRDY was set for all register writes.
        succeeded = True
        for dhcsr_cb in dhcsr_cb_list:
            dhcsr_val = dhcsr_cb()
            if (dhcsr_val & CortexM.S_REGRDY) == 0:
                raise exceptions.DebugError("failed to write register")

    def set_breakpoint(self, addr, type=Target.BreakpointType.AUTO):
        """! @brief Set a hardware or software breakpoint at a specific location in memory.
        
        @retval True Breakpoint was set.
        @retval False Breakpoint could not be set.
        """
        return self.bp_manager.set_breakpoint(addr, type)

    def remove_breakpoint(self, addr):
        """! @brief Remove a breakpoint at a specific location."""
        self.bp_manager.remove_breakpoint(addr)

    def get_breakpoint_type(self, addr):
        return self.bp_manager.get_breakpoint_type(addr)

    @property
    def available_breakpoint_count(self):
        return self.fpb.available_breakpoints

    def find_watchpoint(self, addr, size, type):
        if self.dwt is not None:
            return self.dwt.find_watchpoint(addr, size, type)

    def set_watchpoint(self, addr, size, type):
        """! @brief Set a hardware watchpoint.
        """
        if self.dwt is not None:
            return self.dwt.set_watchpoint(addr, size, type)

    def remove_watchpoint(self, addr, size, type):
        """! @brief Remove a hardware watchpoint.
        """
        if self.dwt is not None:
            return self.dwt.remove_watchpoint(addr, size, type)

    @staticmethod
    def _map_to_vector_catch_mask(mask):
        result = 0
        if mask & Target.VectorCatch.HARD_FAULT:
            result |= CortexM.DEMCR_VC_HARDERR
        if mask & Target.VectorCatch.BUS_FAULT:
            result |= CortexM.DEMCR_VC_BUSERR
        if mask & Target.VectorCatch.MEM_FAULT:
            result |= CortexM.DEMCR_VC_MMERR
        if mask & Target.VectorCatch.INTERRUPT_ERR:
            result |= CortexM.DEMCR_VC_INTERR
        if mask & Target.VectorCatch.STATE_ERR:
            result |= CortexM.DEMCR_VC_STATERR
        if mask & Target.VectorCatch.CHECK_ERR:
            result |= CortexM.DEMCR_VC_CHKERR
        if mask & Target.VectorCatch.COPROCESSOR_ERR:
            result |= CortexM.DEMCR_VC_NOCPERR
        if mask & Target.VectorCatch.CORE_RESET:
            result |= CortexM.DEMCR_VC_CORERESET
        return result

    @staticmethod
    def _map_from_vector_catch_mask(mask):
        result = 0
        if mask & CortexM.DEMCR_VC_HARDERR:
            result |= Target.VectorCatch.HARD_FAULT
        if mask & CortexM.DEMCR_VC_BUSERR:
            result |= Target.VectorCatch.BUS_FAULT
        if mask & CortexM.DEMCR_VC_MMERR:
            result |= Target.TargetVectorCatch.MEM_FAULT
        if mask & CortexM.DEMCR_VC_INTERR:
            result |= Target.VectorCatch.INTERRUPT_ERR
        if mask & CortexM.DEMCR_VC_STATERR:
            result |= Target.VectorCatch.STATE_ERR
        if mask & CortexM.DEMCR_VC_CHKERR:
            result |= Target.VectorCatch.CHECK_ERR
        if mask & CortexM.DEMCR_VC_NOCPERR:
            result |= Target.VectorCatch.COPROCESSOR_ERR
        if mask & CortexM.DEMCR_VC_CORERESET:
            result |= Target.VectorCatch.CORE_RESET
        return result

    def set_vector_catch(self, enableMask):
        demcr = self.read_memory(CortexM.DEMCR)
        demcr |= CortexM._map_to_vector_catch_mask(enableMask)
        demcr &= ~CortexM._map_to_vector_catch_mask(~enableMask)
        LOG.debug("Setting vector catch to 0x%08x", enableMask)
        self.write_memory(CortexM.DEMCR, demcr)

    def get_vector_catch(self):
        demcr = self.read_memory(CortexM.DEMCR)
        return CortexM._map_from_vector_catch_mask(demcr)

    # GDB functions
    def get_target_xml(self):
        return self.target_xml

    def is_debug_trap(self):
        debugEvents = self.read_memory(CortexM.DFSR) & (CortexM.DFSR_DWTTRAP | CortexM.DFSR_BKPT | CortexM.DFSR_HALTED)
        return debugEvents != 0

    def is_vector_catch(self):
        return self.get_halt_reason() == Target.HaltReason.VECTOR_CATCH
    
    def get_halt_reason(self):
        """! @brief Returns the reason the core has halted.
        
        @return @ref pyocd.core.target.Target.HaltReason "Target.HaltReason" enumerator or None.
        """
        dfsr = self.read32(CortexM.DFSR)
        if dfsr & CortexM.DFSR_HALTED:
            reason = Target.HaltReason.DEBUG
        elif dfsr & CortexM.DFSR_BKPT:
            reason = Target.HaltReason.BREAKPOINT
        elif dfsr & CortexM.DFSR_DWTTRAP:
            reason = Target.HaltReason.WATCHPOINT
        elif dfsr & CortexM.DFSR_VCATCH:
            reason = Target.HaltReason.VECTOR_CATCH
        elif dfsr & CortexM.DFSR_EXTERNAL:
            reason = Target.HaltReason.EXTERNAL
        elif dfsr & CortexM.DFSR_PMU:
            reason = Target.HaltReason.PMU
        else:
            reason = None
        return reason

    def get_target_context(self, core=None):
        return self._target_context

    def set_target_context(self, context):
        self._target_context = context

    ## @brief Names for built-in Exception numbers found in IPSR
    CORE_EXCEPTION = [
           "Thread",
           "Reset",
           "NMI",
           "HardFault",
           "MemManage",
           "BusFault",
           "UsageFault",
           "SecureFault",
           "Exception 8",
           "Exception 9",
           "Exception 10",
           "SVCall",
           "DebugMonitor",
           "Exception 13",
           "PendSV",
           "SysTick",
    ]

    def exception_number_to_name(self, exc_num, name_thread=False):
        if exc_num < len(self.CORE_EXCEPTION):
            if exc_num == 0 and not name_thread:
                return None
            else:
                return self.CORE_EXCEPTION[exc_num]
        else:
            irq_num = exc_num - len(self.CORE_EXCEPTION)
            name = None
            if self.session.target.irq_table:
                name = self.session.target.irq_table.get(irq_num)
            if name is not None:
                return "Interrupt[%s]" % name
            else:
                return "Interrupt %d" % irq_num

    def in_thread_mode_on_main_stack(self):
        return (self._target_context.read_core_register('ipsr') == 0 and
                (self._target_context.read_core_register('control') & CortexM.CONTROL_SPSEL) == 0)
