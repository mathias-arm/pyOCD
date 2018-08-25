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
from ..core.dap_interface import DAPInterface
from ..core import exceptions
from ..pyDAPAccess import DAPAccess
from ..board.mbed_board import MbedBoard
from ..board.board_ids import BOARD_ID_TO_INFO
import six

SWD_CAPABILITY_MASK = 1
JTAG_CAPABILITY_MASK = 2

## @brief Wraps a pyDAPAccess link as a DebugProbe.
class CMSISDAPProbe(DebugProbe, DAPInterface):

    # Map from DebugProbe protocol types to/from DAPAccess port types.
    PORT_MAP = {
        DebugProbe.Protocol.DEFAULT: DAPAccess.PORT.DEFAULT,
        DebugProbe.Protocol.SWD: DAPAccess.PORT.SWD,
        DebugProbe.Protocol.JTAG: DAPAccess.PORT.JTAG,
        DAPAccess.PORT.DEFAULT: DebugProbe.Protocol.DEFAULT,
        DAPAccess.PORT.SWD: DebugProbe.Protocol.SWD,
        DAPAccess.PORT.JTAG: DebugProbe.Protocol.JTAG,
        }
    
    @classmethod
    def get_all_connected_probes(cls):
        try:
            return [cls(dev) for dev in DAPAccess.get_connected_devices()]
        except DAPAccess.Error as exc:
            six.raise_from(cls._convert_exception(exc), exc)
    
    @classmethod
    def get_probe_with_id(cls, unique_id):
        try:
            return cls(DAPAccess(unique_id))
        except DAPAccess.Error as exc:
            six.raise_from(cls._convert_exception(exc), exc)

    def __init__(self, device):
        self._link = device
        self._supported_protocols = None
        self._protocol = None
        self._is_open = False
        
    @property
    def description(self):
        try:
            board_id = self.unique_id[0:4]
            board_info = BOARD_ID_TO_INFO[board_id]
        except KeyError:
            return self.vendor_name + " " + self.product_name
        else:
            return "{0} [{1}]".format(board_info.name, board_info.target)
    
    @property
    def vendor_name(self):
        return self._link.vendor_name
    
    @property
    def product_name(self):
        return self._link.product_name

    ## @brief Only valid after opening.
    @property
    def supported_wire_protocols(self):
        return self._supported_protocols

    @property
    def unique_id(self):
        return self._link.get_unique_id()

    @property
    def wire_protocol(self):
        return self._protocol
    
    @property
    def is_open(self):
        return self._is_open

    def create_associated_board(self, session):
        return MbedBoard(session)
    
    def open(self):
        try:
            self._link.open()
            self._is_open = True
            self._link.set_deferred_transfer(True)
        
            # Read CMSIS-DAP capabilities
            self._capabilities = self._link.identify(DAPAccess.ID.CAPABILITIES)
            self._supported_protocols = [DebugProbe.Protocol.DEFAULT]
            if self._capabilities & SWD_CAPABILITY_MASK:
                self._supported_protocols.append(DebugProbe.Protocol.SWD)
            if self._capabilities & JTAG_CAPABILITY_MASK:
                self._supported_protocols.append(DebugProbe.Protocol.JTAG)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)
    
    def close(self):
        try:
            self._link.close()
            self._is_open = False
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    # ------------------------------------------- #
    #          Target control functions
    # ------------------------------------------- #
    def connect(self, protocol=None):
        """Initialize DAP IO pins for JTAG or SWD"""
        # Convert protocol to port enum.
        if protocol is not None:
            port = self.PORT_MAP[protocol]
        else:
            port = DAPAccess.PORT.DEFAULT
        
        try:
            self._link.connect(port)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)
        
        # Read the current mode and save it.
        actualMode = self._link.get_swj_mode()
        self._protocol = self.PORT_MAP[actualMode]

    # TODO remove
    def swj_sequence(self):
        """Send sequence to activate JTAG or SWD on the target"""
        try:
            self._link.swj_sequence()
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def disconnect(self):
        """Deinitialize the DAP I/O pins"""
        try:
            self._link.disconnect()
            self._protocol = None
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def set_clock(self, frequency):
        """Set the frequency for JTAG and SWD in Hz

        This function is safe to call before connect is called.
        """
        try:
            self._link.set_clock(frequency)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def reset(self):
        """Reset the target"""
        try:
            self._link.reset()
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def assert_reset(self, asserted):
        """Assert or de-assert target reset line"""
        try:
            self._link.assert_reset(asserted)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)
    
    def is_reset_asserted(self):
        """Returns True if the target reset line is asserted or False if de-asserted"""
        try:
            return self._link.is_reset_asserted()
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def flush(self):
        """Write out all unsent commands"""
        try:
            self._link.flush()
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    # ------------------------------------------- #
    #          DAP Access functions
    # ------------------------------------------- #
    def write_reg(self, reg_id, value, dap_index=0):
        """Write a single word to a DP or AP register"""
        try:
            return self._link.write_reg(reg_id, value, dap_index)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def read_reg(self, reg_id, dap_index=0, now=True):
        """Read a single word to a DP or AP register"""
        try:
            return self._link.read_reg(reg_id, dap_index, now)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def reg_write_repeat(self, num_repeats, reg_id, data_array, dap_index=0):
        """Write one or more words to the same DP or AP register"""
        try:
            return self._link.reg_write_repeat(num_repeats, reg_id, data_array, dap_index)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)

    def reg_read_repeat(self, num_repeats, reg_id, dap_index=0, now=True):
        """Read one or more words from the same DP or AP register"""
        try:
            return self._link.reg_read_repeat(num_repeats, reg_id, dap_index, now)
        except DAPAccess.Error as exc:
            six.raise_from(self._convert_exception(exc), exc)
  
    @staticmethod
    def _convert_exception(exc):
        if isinstance(exc, DAPAccess.TransferFaultError):
            return exceptions.TransferFaultError()
        elif isinstance(exc, DAPAccess.TransferTimeoutError):
            return exceptions.TransferTimeoutError()
        elif isinstance(exc, DAPAccess.TransferError):
            return exceptions.TransferError()
        elif isinstance(exc, (DAPAccess.DeviceError, DAPAccess.CommandError)):
            return exceptions.ProbeError(str(exc))
        elif isinstance(exc, DAPAccess.Error):
            return exceptions.PyOCDError(str(exc))
        else:
            return exc

