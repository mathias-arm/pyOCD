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
from ..core import exceptions
from .jlink import JLinkError
from .jlink.jlink import JLink
from .jlink.usb import JLinkUSBInterface
import six
from time import sleep

## @brief Wraps a JLink as a DebugProbe.
class JLinkProbe(DebugProbe):

    # APnDP constants.
    DP = 0
    AP = 1
    
    ACK_OK = 0b001
    ACK_WAIT = 0b010
    ACK_FAULT = 0b100
    
    # Bitmasks for AP register address fields.
    A32 = 0x0000000c
    APBANKSEL = 0x000000f0
    APSEL = 0xff000000
    APSEL_APBANKSEL = APSEL | APBANKSEL
    
    # Address of DP's SELECT register.
    DP_SELECT = 0x8
    
    @classmethod
    def get_all_connected_probes(cls):
        try:
            return [cls(dev) for dev in JLinkUSBInterface.get_all_connected_devices()]
        except JLinkError as exc:
            six.raise_from(cls._convert_exception(exc), exc)
    
    @classmethod
    def get_probe_with_id(cls, unique_id):
        try:
            for dev in JLinkUSBInterface.get_all_connected_devices():
                if dev.serial_number == unique_id:
                    return cls(JLinkUSBInterface(unique_id))
            else:
                return None
        except JLinkError as exc:
            six.raise_from(cls._convert_exception(exc), exc)

    def __init__(self, device):
        self._link = JLink(device)
        self._supported_protocols = None
        self._protocol = None
        self._default_protocol = None
        self._is_open = False
        self._dp_select = -1
        
    @property
    def description(self):
        return self.vendor_name + " " + self.product_name
    
    @property
    def vendor_name(self):
        return "Segger"
    
    @property
    def product_name(self):
        return self._link.product_name

    ## @brief Only valid after opening.
    @property
    def supported_wire_protocols(self):
        return self._supported_protocols

    @property
    def unique_id(self):
        return self._link.unique_id

    @property
    def wire_protocol(self):
        return self._protocol
    
    @property
    def is_open(self):
        return self._is_open
    
    def open(self):
        try:
            self._link.open()
            print(self._link)
            self._is_open = True
        
            # Get available wire protocols.
            ifaces = self._link.get_interfaces()
            self._supported_protocols = [DebugProbe.Protocol.DEFAULT]
            if ifaces & (1 << JLink.TIF_JTAG):
                self._supported_protocols.append(DebugProbe.Protocol.JTAG)
            if ifaces & (1 << JLink.TIF_SWD):
                self._supported_protocols.append(DebugProbe.Protocol.SWD)
            assert len(self._supported_protocols) > 1
            
            # Select default protocol, preferring SWD over JTAG.
            if DebugProbe.Protocol.SWD in self._supported_protocols:
                self._default_protocol = DebugProbe.Protocol.SWD
            else:
                self._default_protocol = DebugProbe.Protocol.JTAG
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)
    
    def close(self):
        try:
            self._link.close()
            self._is_open = False
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)

    # ------------------------------------------- #
    #          Target control functions
    # ------------------------------------------- #
    def connect(self, protocol=None):
        """Initialize DAP IO pins for JTAG or SWD"""
        # Handle default protocol.
        if (protocol is None) or (protocol == DebugProbe.Protocol.DEFAULT):
            protocol = self._default_protocol
        
        # Validate selected protocol.
        if protocol not in self._supported_protocols:
            raise ValueError("unsupported wire protocol %s" % protocol)
        
        # Convert protocol to port enum.
        if protocol == DebugProbe.Protocol.SWD:
            iface = JLink.TIF_SWD
        elif protocol == DebugProbe.Protocol.JTAG:
            iface = JLink.TIF_JTAG
        
        try:
            self._link.select_interface(iface)
            self._protocol = protocol
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)

    # TODO remove
    def swj_sequence(self):
        """Send sequence to activate JTAG or SWD on the target"""
        try:
            self._link.swj_sequence()
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def disconnect(self):
        """Deinitialize the DAP I/O pins"""
        self._protocol = None
        self._invalidate_cached_registers()

    def set_clock(self, frequency):
        """Set the frequency for JTAG and SWD in Hz

        This function is safe to call before connect is called.
        """
        try:
            self._link.set_frequency(frequency)
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def reset(self):
        """Reset the target"""
        try:
            self.assert_reset(True)
            sleep(0.5)
            self.assert_reset(False)

            self._invalidate_cached_registers()
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def assert_reset(self, asserted):
        """Assert or de-assert target reset line"""
        try:
            self._link.reset(0 if asserted else 1)
            self._invalidate_cached_registers()
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)
    
    def is_reset_asserted(self):
        """Returns True if the target reset line is asserted or False if de-asserted"""
        try:
            state = self._link.get_state()
            return state['srst'] == 0
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def flush(self):
        """Write out all unsent commands"""
        try:
            pass
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)

    # ------------------------------------------- #
    #          DAP Access functions
    # ------------------------------------------- #

    def read_dp(self, addr, now=True):
        try:
            ack, value, parityOk = self._link.read_reg(self.DP, addr)
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)
        else:
            if ack == JLink.ACK_FAULT:
                self._invalidate_cached_registers()
                raise exceptions.TransferFaultError()
            elif ack != JLink.ACK_OK or not parityOk:
                self._invalidate_cached_registers()
                raise exceptions.TransferError()
            
            def read_reg_cb():
                return value
        
            return value if now else read_reg_cb

    def write_dp(self, addr, data):
        # Skip writing DP SELECT register if its value is not changing.
        if addr == self.DP_SELECT:
            if data == self._dp_select:
                return
            self._dp_select = data

        try:
            ack = self._link.write_reg(self.DP, addr, value)
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)
        else:
            if ack == JLink.ACK_FAULT:
                self._invalidate_cached_registers()
                raise exceptions.TransferFaultError()
            elif ack != JLink.ACK_OK:
                self._invalidate_cached_registers()
                raise exceptions.TransferError()

    def read_ap(self, addr, now=True):
        assert type(addr) in (six.integer_types)
        try:
            self.write_dp(self.DP_SELECT, addr & self.APSEL_APBANKSEL)
            ack, value, parityOk = self._link.read_reg(self.AP, addr)
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)
        else:
            if ack == JLink.ACK_FAULT:
                self._invalidate_cached_registers()
                raise exceptions.TransferFaultError()
            elif ack != JLink.ACK_OK or not parityOk:
                self._invalidate_cached_registers()
                raise exceptions.TransferError()
            
            def read_reg_cb():
                return value
        
            return value if now else read_reg_cb

    def write_ap(self, addr, data):
        assert type(addr) in (six.integer_types)
        try:
            self.write_dp(self.DP_SELECT, addr & self.APSEL_APBANKSEL)
            ack = self._link.write_reg(self.AP, addr, value)
        except JLinkError as exc:
            six.raise_from(self._convert_exception(exc), exc)
        else:
            if ack == JLink.ACK_FAULT:
                self._invalidate_cached_registers()
                raise exceptions.TransferFaultError()
            elif ack != JLink.ACK_OK:
                self._invalidate_cached_registers()
                raise exceptions.TransferError()

    def read_ap_multiple(self, addr, count=1, now=True):
        results = [self.read_ap(addr, now=True) for n in range(count)]
        
        def read_ap_multiple_result_callback():
            return result
        
        return results if now else read_ap_multiple_result_callback

    def write_ap_multiple(self, addr, values):
        for v in values:
            self.write_ap(addr, v)

    def _invalidate_cached_registers(self):
        # Invalidate cached DP SELECT register.
        self._dp_select = -1

    @staticmethod
    def _convert_exception(exc):
        if isinstance(exc, JLinkError):
            return exceptions.ProbeError(str(exc))
        else:
            return exc

