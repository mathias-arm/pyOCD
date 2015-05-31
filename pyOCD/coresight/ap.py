"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2015 ARM Limited

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

from .rom_table import ROMTable
from ..transport.cmsis_dap import AP_REG
from ..utility import conversion
import logging

AP_SEL_SHIFT = 24

AP_ROM_TABLE_ADDR_REG = 0xf8
AP_ROM_TABLE_FORMAT_MASK = 0x2
AP_ROM_TABLE_ENTRY_PRESENT_MASK = 0x1

AHB_IDR_TO_WRAP_SIZE = {
    0x24770011 : 0x1000,    # Used on m4 & m3 - Documented in arm_cortexm4_processor_trm_100166_0001_00_en.pdf
                            #                   and arm_cortexm3_processor_trm_100165_0201_00_en.pdf
    0x44770001 : 0x400,     # Used on m1 - Documented in DDI0413D_cortexm1_r1p0_trm.pdf
    0x04770031 : 0x400,     # Used on m0+? at least on KL25Z, KL46, LPC812
    0x04770021 : 0x400,     # Used on m0? used on nrf51, lpc11u24
    0x64770001 : 0x400,     # Used on m7
    0x74770001 : 0x400,     # Used on m0+ on KL28Z
    }

class AccessPort(object):
    def __init__(self, dp, ap_num):
        self.dp = dp
        self.ap_num = ap_num
        self.transport = dp.transport
        self.idr = 0
        self.rom_addr = 0
        self.has_rom_table = False
        self.rom_table = None

    def init(self, bus_accessible=True):
        self.idr = self.readReg(AP_REG['IDR'])

        # Init ROM table
        self.rom_addr = self.readReg(AP_ROM_TABLE_ADDR_REG)
        self.has_rom_table = (self.rom_addr != 0xffffffff) and ((self.rom_addr & AP_ROM_TABLE_ENTRY_PRESENT_MASK) != 0)
        self.rom_addr &= 0xfffffffc # clear format and present bits
        if self.has_rom_table and bus_accessible:
            self.initROMTable()

    def initROMTable(self):
        self.rom_table = ROMTable(self)
        self.rom_table.init()

    def readReg(self, addr):
        return self.transport.readAP((self.ap_num << AP_SEL_SHIFT) | addr)

    def writeReg(self, addr, data):
        self.transport.readAP((self.ap_num << AP_SEL_SHIFT) | addr, data)

class MEM_AP(AccessPort):
    def init(self, bus_accessible=True):
        super(MEM_AP, self).init(bus_accessible)

        if self.idr in AHB_IDR_TO_WRAP_SIZE:
            self.auto_increment_page_size = AHB_IDR_TO_WRAP_SIZE[self.idr]
        else:
            # If unknown use the smallest size supported by all targets.
            # A size smaller than the supported size will decrease performance
            # due to the extra address writes, but will not create any
            # read/write errors.
            self.auto_increment_page_size = 0x400
            logging.warning("Unknown AHB IDR: 0x%x" % self.idr)

    ## @brief Write a single memory location.
    #
    # By default the transfer size is a word
    def writeMemory(self, addr, value, transfer_size = 32):
        self.transport.writeMem(addr, value, transfer_size)

    def write32(self, addr, value):
        """
        Shorthand to write a 32-bit word.
        """
        self.writeMemory(addr, value, 32)

    def write16(self, addr, value):
        """
        Shorthand to write a 16-bit halfword.
        """
        self.writeMemory(addr, value, 16)

    def write8(self, addr, value):
        """
        Shorthand to write a byte.
        """
        self.writeMemory(addr, value, 8)

    def readMemory(self, addr, transfer_size = 32):
        """
        read a memory location. By default, a word will
        be read
        """
        return self.transport.readMem(addr, transfer_size)

    def read32(self, addr):
        """
        Shorthand to read a 32-bit word.
        """
        return self.readMemory(addr, 32)

    def read16(self, addr):
        """
        Shorthand to read a 16-bit halfword.
        """
        return self.readMemory(addr, 16)

    def read8(self, addr):
        """
        Shorthand to read a byte.
        """
        return self.readMemory(addr, 8)

    def readBlockMemoryUnaligned8(self, addr, size):
        """
        read a block of unaligned bytes in memory. Returns
        an array of byte values
        """
        res = []

        # try to read 8bits data
        if (size > 0) and (addr & 0x01):
            mem = self.readMemory(addr, 8)
#             logging.debug("get 1 byte at %s: 0x%X", hex(addr), mem)
            res.append(mem)
            size -= 1
            addr += 1

        # try to read 16bits data
        if (size > 1) and (addr & 0x02):
            mem = self.readMemory(addr, 16)
#             logging.debug("get 2 bytes at %s: 0x%X", hex(addr), mem)
            res.append(mem & 0xff)
            res.append((mem >> 8) & 0xff)
            size -= 2
            addr += 2

        # try to read aligned block of 32bits
        if (size >= 4):
            #logging.debug("read blocks aligned at 0x%X, size: 0x%X", addr, (size/4)*4)
            mem = self.readBlockMemoryAligned32(addr, size/4)
            res += conversion.word2byte(mem)
            size -= 4*len(mem)
            addr += 4*len(mem)

        if (size > 1):
            mem = self.readMemory(addr, 16)
#             logging.debug("get 2 bytes at %s: 0x%X", hex(addr), mem)
            res.append(mem & 0xff)
            res.append((mem >> 8) & 0xff)
            size -= 2
            addr += 2

        if (size > 0):
            mem = self.readMemory(addr, 8)
#             logging.debug("get 1 byte remaining at %s: 0x%X", hex(addr), mem)
            res.append(mem)
            size -= 1
            addr += 1

        return res

    def writeBlockMemoryUnaligned8(self, addr, data):
        """
        write a block of unaligned bytes in memory.
        """
        size = len(data)
        idx = 0

        #try to write 8 bits data
        if (size > 0) and (addr & 0x01):
#             logging.debug("write 1 byte at 0x%X: 0x%X", addr, data[idx])
            self.writeMemory(addr, data[idx], 8)
            size -= 1
            addr += 1
            idx += 1

        # try to write 16 bits data
        if (size > 1) and (addr & 0x02):
#             logging.debug("write 2 bytes at 0x%X: 0x%X", addr, data[idx] | (data[idx+1] << 8))
            self.writeMemory(addr, data[idx] | (data[idx+1] << 8), 16)
            size -= 2
            addr += 2
            idx += 2

        # write aligned block of 32 bits
        if (size >= 4):
            #logging.debug("write blocks aligned at 0x%X, size: 0x%X", addr, (size/4)*4)
            data32 = conversion.byte2word(data[idx:idx + (size & ~0x03)])
            self.writeBlockMemoryAligned32(addr, data32)
            addr += size & ~0x03
            idx += size & ~0x03
            size -= size & ~0x03

        # try to write 16 bits data
        if (size > 1):
#             logging.debug("write 2 bytes at 0x%X: 0x%X", addr, data[idx] | (data[idx+1] << 8))
            self.writeMemory(addr, data[idx] | (data[idx+1] << 8), 16)
            size -= 2
            addr += 2
            idx += 2

        #try to write 8 bits data
        if (size > 0):
#             logging.debug("write 1 byte at 0x%X: 0x%X", addr, data[idx])
            self.writeMemory(addr, data[idx], 8)
            size -= 1
            addr += 1
            idx += 1

        return

    ## @brief Write a block of aligned words in memory.
    def writeBlockMemoryAligned32(self, addr, data):
        size = len(data)
        while size > 0:
            n = self.auto_increment_page_size - (addr & (self.auto_increment_page_size - 1))
            if size*4 < n:
                n = (size*4) & 0xfffffffc
            self.transport.writeBlock32(addr, data[:n/4])
            data = data[n/4:]
            size -= n/4
            addr += n
        return

    ## @brief Read a block of aligned words in memory.
    #
    # @return An array of word values
    def readBlockMemoryAligned32(self, addr, size):
        resp = []
        while size > 0:
            n = self.auto_increment_page_size - (addr & (self.auto_increment_page_size - 1))
            if size*4 < n:
                n = (size*4) & 0xfffffffc
            resp += self.transport.readBlock32(addr, n/4)
            size -= n/4
            addr += n
        return resp

class AHB_AP(MEM_AP):
    pass



