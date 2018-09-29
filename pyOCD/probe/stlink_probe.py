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

from .debug_probe import DebugProbe
from ..core.memory_interface import MemoryInterface
from ..core import exceptions
from .stlink import (StlinkException, usb, stlinkv2)
from ..utility import conversion
import six

## @brief Wraps an StLink as a DebugProbe.
class StlinkProbe(DebugProbe, MemoryInterface):
        
    APSEL = 0xff000000
    APSEL_SHIFT = 24
    
    @classmethod
    def get_all_connected_probes(cls):
        try:
            return [cls(dev) for dev in usb.StlinkUsbInterface.get_all_connected_devices()]
        except StlinkException as exc:
            six.raise_from(cls._convert_exception(exc), exc)
    
    @classmethod
    def get_probe_with_id(cls, unique_id):
        try:
            for dev in usb.StlinkUsbInterface.get_all_connected_devices():
                if dev.serial_number == unique_id:
                    return cls(usb.StlinkUsbInterface(unique_id))
            else:
                return None
        except StlinkException as exc:
            six.raise_from(cls._convert_exception(exc), exc)

    def __init__(self, device):
        self._link = stlinkv2.Stlink(device)
        self._is_open = False
        self._nreset_state = False
        
    @property
    def description(self):
        return self.product_name
    
    @property
    def vendor_name(self):
        return "ST"
    
    @property
    def product_name(self):
        return self._link.product_name

    ## @brief Only valid after opening.
    @property
    def supported_wire_protocols(self):
        return [DebugProbe.Protocol.DEFAULT, DebugProbe.Protocol.SWD, DebugProbe.Protocol.JTAG]

    @property
    def unique_id(self):
        return self._link.serial_number

    @property
    def wire_protocol(self):
        return DebugProbe.Protocol.SWD
    
    @property
    def is_open(self):
        return self._is_open

    def create_associated_board(self, session):
        return None
    
    def open(self):
        try:
            self._link.open()
            self._is_open = True
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)
    
    def close(self):
        try:
            self._link.close()
            self._is_open = False
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)

    # ------------------------------------------- #
    #          Target control functions
    # ------------------------------------------- #
    def connect(self, protocol=None):
        """Initialize DAP IO pins for JTAG or SWD"""
        try:
            self._link.enter_debug(stlinkv2.Stlink.Protocol.SWD)
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)

    # TODO remove
    def swj_sequence(self):
        """Send sequence to activate JTAG or SWD on the target"""
        pass

    def disconnect(self):
        """Deinitialize the DAP I/O pins"""
        try:
            self._link.enter_idle()
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def set_clock(self, frequency):
        """Set the frequency for JTAG and SWD in Hz

        This function is safe to call before connect is called.
        """
        try:
            self._link.set_swd_freq(frequency)
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def reset(self):
        """Reset the target"""
        try:
            self._link.target_reset()
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def assert_reset(self, asserted):
        """Assert or de-assert target reset line"""
        try:
            self._link.drive_nreset(asserted)
            self._nreset_state = asserted
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)
    
    def is_reset_asserted(self):
        """Returns True if the target reset line is asserted or False if de-asserted"""
        return self._nreset_state

    def flush(self):
        """Write out all unsent commands"""
        pass

    # ------------------------------------------- #
    #          DAP Access functions
    # ------------------------------------------- #
    
    def read_dp(self, addr, now=True):
        try:
            result = self._link.read_dap_register(stlinkv2.Stlink.DP_PORT, addr)
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)
        
        def read_dp_result_callback():
            return result
        
        return result if now else read_dp_result_callback

    def write_dp(self, addr, data):
        try:
            result = self._link.write_dap_register(stlinkv2.Stlink.DP_PORT, addr, data)
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def read_ap(self, addr, now=True):
        try:
            apsel = (addr & self.APSEL) >> self.APSEL_SHIFT
            result = self._link.read_dap_register(apsel, addr & 0xffff)
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)
        
        def read_ap_result_callback():
            return result
        
        return result if now else read_ap_result_callback

    def write_ap(self, addr, data):
        try:
            apsel = (addr & self.APSEL) >> self.APSEL_SHIFT
            result = self._link.write_dap_register(apsel, addr & 0xffff, data)
        except StlinkException as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def read_ap_multiple(self, addr, count=1, now=True):
        results = [self.read_ap(addr, now=True) for n in range(count)]
        
        def read_ap_multiple_result_callback():
            return result
        
        return results if now else read_ap_multiple_result_callback

    def write_ap_multiple(self, addr, values):
        [self.write_ap(addr, v) for v in values]

    # ------------------------------------------- #
    #          Memory Access functions
    # ------------------------------------------- #
    
    ## @brief Write a single memory location.
    #
    # By default the transfer size is a word.
    def write_memory(self, addr, data, transfer_size=32, apsel=0):
        if transfer_size == 32:
            self._link.write_mem32(addr, conversion.u32leListToByteList([data]), apsel)
        elif transfer_size == 16:
            self._link.write_mem16(addr, conversion.u16leListToByteList([data]), apsel)
        elif transfer_size == 8:
            self._link.write_mem8(addr, [data], apsel)
        else:
            raise ValueError("transfer size is not 32, 16, or 8")
        
    ## @brief Read a memory location.
    #
    # By default, a word will be read.
    def read_memory(self, addr, transfer_size=32, now=True, apsel=0):
        if transfer_size == 32:
            result = conversion.byteListToU32leList(self._link.read_mem32(addr, 4, apsel))[0]
        elif transfer_size == 16:
            result = conversion.byteListToU16leList(self._link.read_mem16(addr, 2, apsel))[0]
        elif transfer_size == 8:
            result = self._link.read_mem8(addr, 1, apsel)[0]
        else:
            raise ValueError("transfer size is not 32, 16, or 8")
        
        def read_callback():
            return result
        return result if now else read_callback

    def write_memory_block32(self, addr, data, apsel=0):
        self._link.write_mem32(addr, conversion.u32leListToByteList(data), apsel)

    def read_memory_block32(self, addr, size, apsel=0):
        return conversion.byteListToU32leList(self._link.read_mem32(addr, size * 4, apsel))
  
    @staticmethod
    def _convert_exception(exc):
        if isinstance(exc, StlinkException):
            return exceptions.ProbeError(str(exc))
        else:
            return exc

