# pyOCD debugger
# Copyright (c) 2020 Arm Limited
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
from time import sleep

from .component import CoreSightComponent
from ..core import exceptions
from ..utility.timeout import Timeout
from ..utility.hex import dump_hex_data

LOG = logging.getLogger(__name__)

class SDC600(CoreSightComponent):
    """! @brief SDC-600 component.
    """
    
    ## Timeout for each byte transfer.
    TRANSFER_TIMEOUT = 10.0
    
    class Register:
        """! @brief Namespace for register offset constants."""
        # Register offsets.
        VIDR        = 0xD00
        FIDTXR      = 0xD08
        FIDRXR      = 0xD0C
        ICSR        = 0xD10
        DR          = 0xD20
        SR          = 0xD2C
        DBR         = 0xD30
        SR_ALIAS    = 0xD3C

        # FIDTXR and FIDRXR bit definitions.
        FIDxXR_xXI_MASK     = (0x00000001)
        FIDxXR_xXI_SHIFT    = (0)
        FIDxXR_xXINT_MASK   = (0x00000002)
        FIDxXR_xXINT_SHIFT  = (1)
        FIDxXR_xXW_MASK     = (0x000000f0)
        FIDxXR_xXW_SHIFT    = (4)
        FIDxXR_xXSZ8_MASK   = (0x00000100)
        FIDxXR_xXSZ8_SHIFT  = (8)
        FIDxXR_xXSZ16_MASK  = (0x00000200)
        FIDxXR_xXSZ16_SHIFT = (9)
        FIDxXR_xXSZ32_MASK  = (0x00000400)
        FIDxXR_xXSZ32_SHIFT = (10)
        FIDxXR_xXFD_MASK    = (0x000f0000)
        FIDxXR_xXFD_SHIFT   = (16)
        
        # SR bit definitions.
        SR_TXS_MASK         = (0x000000ff)
        SR_TXS_SHIFT        = (0)
        SR_RRDIS_MASK       = (0x00001000)
        SR_RRDIS_SHIFT      = (12)
        SR_TXOE_MASK        = (0x00002000)
        SR_TXOE_SHIFT       = (13)
        SR_TXLE_MASK        = (0x00004000)
        SR_TXLE_SHIFT       = (14)
        SR_TRINPROG_MASK    = (0x00008000)
        SR_TRINPROG_SHIFT   = (18)
        SR_RXF_MASK         = (0x00ff0000)
        SR_RXF_SHIFT        = (16)
        SR_RXLE_MASK        = (0x40000000)
        SR_RXLE_SHIFT       = (30)
        SR_PEN_MASK         = (0x80000000)
        SR_PEN_SHIFT        = (31)
    
    class Flag:
        """! @brief Namespace with flag byte value constants."""
        IDR     = 0xA0
        IDA     = 0xA1
        LPH1RA  = 0xA6
        LPH1RL  = 0xA7
        LPH2RA  = 0xA8
        LPH2RL  = 0xA9
        LPH2RR  = 0xAA
        START   = 0xAC
        END     = 0xAD
        ESC     = 0xAE
        NULL    = 0xAF
    
    ## NULL bytes must be written to the upper bytes, and will be present in the upper bytes
    # when read.
    NULL_FILL = 0xAFAFAF00
    
    def __init__(self, ap, cmpid=None, addr=None):
        super(SDC600, self).__init__(ap, cmpid, addr)
        self._tx_width = 0
        self._rx_width = 0

    def init(self):
        """! @brief Inits the component."""
        fidtx = self.ap.read32(self.Register.FIDTXR)
        LOG.info("fidtx=0x%08x", fidtx)
        fidrx = self.ap.read32(self.Register.FIDRXR)
        LOG.info("fidrx=0x%08x", fidrx)
        
        self._tx_width = (fidtx & self.Register.FIDxXR_xXW_MASK) >> self.Register.FIDxXR_xXW_SHIFT
        
        self._rx_width = (fidrx & self.Register.FIDxXR_xXW_MASK) >> self.Register.FIDxXR_xXW_SHIFT
        
        status = self.ap.read32(self.Register.SR)
        LOG.info("status=0x%08x", status)
        self._is_enabled = (status & self.Register.SR_PEN_MASK) != 0
        
        # Clear any error flags.
        error_flags = status & (self.Register.SR_TXOE_MASK | self.Register.SR_TXLE_MASK)
        if error_flags:
            self.ap.write32(self.Register.SR, error_flags)
    
    @property
    def is_reboot_request_enabled(self):
        return (self.ap.read32(self.Register.SR) & self.Register.SR_RRDIS_MASK) == 0

    def _read(self, count=1):
        data = []
        while count:
            # Wait until a byte is ready in the receive FIFO.
            with Timeout(self.TRANSFER_TIMEOUT) as to_:
                while to_.check():
                    if (self.ap.read32(self.Register.SR) & self.Register.SR_RXF_MASK) != 0:
                        break
                    sleep(0.01)
                else:
                    raise exceptions.TimeoutError("timeout while reading from SDC-600")

            # Read the data register and strip off NULL bytes in high bytes.
            value = self.ap.read32(self.Register.DR) & 0xFF
            data.append(value)
            count -= 1
        return data
        
    def _write(self, data):
        for value in data:
            # Wait until room is available in the transmit FIFO.
            with Timeout(self.TRANSFER_TIMEOUT) as to_:
                while to_.check():
                    if (self.ap.read32(self.Register.SR) & self.Register.SR_TXS_MASK) != 0:
                        break
                    sleep(0.01)
                else:
                    raise exceptions.TimeoutError("timeout while writing to from SDC-600")

            # Write this byte to the transmit FIFO.
            dbr_value = self.NULL_FILL | (value & 0xFF)
            self.ap.write32(self.Register.DR, dbr_value)
    
    def connect(self):
        LOG.info("sending LPH1RA")
        self._write([self.Flag.LPH1RA])
        data = self._read()
        LOG.info("received:")
        dump_hex_data(data)
        if data != [self.Flag.LPH1RA]:
            LOG.error("got %s instead of LPH1RA in response", str(data))
            return
        else:
            LOG.info("got expected LPH1RA")

        status = self.ap.read32(self.Register.SR)
        LOG.info("status=0x%08x", status)
        
        self.session.target.cores[1].reset()

        LOG.info("sending LPH2RA")
        self._write([self.Flag.LPH2RA])
        data = self._read()
        LOG.info("received:")
        dump_hex_data(data)
        if data != [self.Flag.LPH2RA]:
            LOG.error("got %s instead of LPH2RA in response", str(data))
            return
        else:
            LOG.info("got expected LPH2RA")
    
    def __repr__(self):
        return "<SDC-600@{:x}: en={} txw={} rxw={}>".format(id(self),
            self._is_enabled, self._tx_width, self._rx_width)
        


