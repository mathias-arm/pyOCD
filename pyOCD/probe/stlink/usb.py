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

# The MIT License (MIT)
# 
# Copyright (c) 2015 Pavel Revak <pavel.revak@gmail.com>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import absolute_import
from . import StlinkException
import usb.core
import usb.util
import logging

log = logging.getLogger('stlink.usb')

class StlinkUsbInterface(object):
    STLINK_CMD_SIZE_V2 = 16

    DEV_TYPES = [
        {
            'version': 'V2',
            'idVendor': 0x0483,
            'idProduct': 0x3748,
            'outPipe': 0x02,
            'inPipe': 0x81,
        }, {
            'version': 'V2-1',
            'idVendor': 0x0483,
            'idProduct': 0x374b,
            'outPipe': 0x01,
            'inPipe': 0x81,
        }
    ]

    @classmethod
    def _usb_match(cls, dev):
        try:
            for devType in cls.DEV_TYPES:
                if dev.idVendor == devType['idVendor'] and dev.idProduct == devType['idProduct']:
                    return True
            else:
                return False
        except ValueError as error:
            # Permission denied error gets reported as ValueError (langid)
            log.debug(("ValueError \"{}\" while trying to access dev.product "
                           "for idManufacturer=0x{:04x} idProduct=0x{:04x}. "
                           "This is probably a permission issue.").format(error, dev.idVendor, dev.idProduct))
            return False
        except usb.core.USBError as error:
            log.warning("Exception getting device info: %s", error)
            return False
        except IndexError as error:
            log.warning("Internal pyusb error: %s", error)
            return False

    @classmethod
    def get_all_connected_devices(cls):
        devices = usb.core.find(find_all=True, custom_match=cls._usb_match)
        
        intfList = []
        for dev in devices:
            intf = StlinkUsbInterface(dev)
            intfList.append(intf)
        
        return intfList

    def __init__(self, dev):
        self._dev = dev
        self._serial_number = dev.serial_number
        self._dev_type = None
        self._xfer_counter = 0
        for dev_type in StlinkUsbInterface.DEV_TYPES:
            if dev.idVendor == dev_type['idVendor'] and dev.idProduct == dev_type['idProduct']:
                self._dev_type = dev_type
                return
        raise StlinkException('ST-Link/V2 is not connected')

    @property
    def serial_number(self):
        return self._serial_number

    @property
    def version(self):
        return self._dev_type['version']

    @property
    def xfer_counter(self):
        return self._xfer_counter

    def _write(self, data, tout=200):
#         log.debug("  USB > %s" % ' '.join(['%02x' % i for i in data]))
        self._xfer_counter += 1
        count = self._dev.write(self._dev_type['outPipe'], data, tout)
        if count != len(data):
            raise StlinkException("Error, only %d Bytes was transmitted to ST-Link instead of expected %d" % (count, len(data)))

    def _read(self, size, tout=200):
        read_size = size
        if read_size < 64:
            read_size = 64
        elif read_size % 4:
            read_size += 3
            read_size &= 0xffc
        data = self._dev.read(self._dev_type['inPipe'], read_size, tout).tolist()
#         log.debug("  USB < %s" % ' '.join(['%02x' % i for i in data]))
        return data[:size]

    def xfer(self, cmd, data=None, rx_len=None, retry=0, tout=200):
        while (True):
            try:
                if len(cmd) > self.STLINK_CMD_SIZE_V2:
                    raise StlinkException("Error too many Bytes in command: %d, maximum is %d" % (len(cmd), self.STLINK_CMD_SIZE_V2))
                # pad to 16 bytes
                cmd += [0] * (self.STLINK_CMD_SIZE_V2 - len(cmd))
                self._write(cmd, tout)
                if data:
                    self._write(data, tout)
                if rx_len:
                    return self._read(rx_len)
            except usb.core.USBError as e:
                if retry:
                    retry -= 1
                    continue
                raise StlinkException("USB Error: %s" % e)
            return None
    
    def __repr__(self):
        return "<{} @ {:#x} vid={:#06x} pid={:#06x} sn={} version={}>".format(
            self.__class__.__name__, id(self),
            self._dev.idVendor, self._dev.idProduct, self.serial_number,
            self.version)
