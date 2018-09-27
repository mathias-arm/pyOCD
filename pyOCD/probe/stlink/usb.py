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
import six
import threading
from collections import namedtuple

LOG_USB_DATA = True

log = logging.getLogger('stlink.usb')

StlinkInfo = namedtuple('StlinkInfo', 'version_name out_ep in_ep swv_ep')

class StlinkUsbInterface(object):
    # Command packet size.
    CMD_SIZE = 16
    
    # ST's USB vendor ID
    USB_VID = 0x0483

    # Map of USB PID to device endpoint info.
    USB_PID_EP_MAP = {
        # PID              Version  OUT     IN      SWV
        0x3748: StlinkInfo('V2',    0x02,   0x81,   0x83),
        0x374b: StlinkInfo('V2-1',  0x01,   0x81,   0x82),
        0x374a: StlinkInfo('V2-1',  0x01,   0x81,   0x82),  # Audio
        0x3742: StlinkInfo('V2-1',  0x01,   0x81,   0x82),  # No MSD
        0x374e: StlinkInfo('V3',    0x01,   0x81,   0x82),
        0x374f: StlinkInfo('V3',    0x01,   0x81,   0x82),  # Bridge
        0x3753: StlinkInfo('V3',    0x01,   0x81,   0x82),  # 2VCP
        }
    
    DEBUG_INTERFACE_NUMBER = 0

    @classmethod
    def _usb_match(cls, dev):
        try:
            return (dev.idVendor == cls.USB_VID) and (dev.idProduct in cls.USB_PID_EP_MAP)
        except ValueError as error:
            # Permission denied error gets reported as ValueError (langid)
            log.debug(("ValueError \"{}\" while trying to access USB device fields "
                           "for idVendor=0x{:04x} idProduct=0x{:04x}. "
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
            intf = cls(dev)
            intfList.append(intf)
        
        return intfList

    def __init__(self, dev):
        self._dev = dev
        assert dev.idVendor == self.USB_VID
        self._info = self.USB_PID_EP_MAP[dev.idProduct]
        self._ep_out = None
        self._ep_in = None
        self._ep_swv = None
        self._xfer_counter = 0
        self._max_packet_size = 64
        self._closed = True
        self._thread = None
        self._receive_data = []
        self._read_sem = threading.Semaphore(0)
    
    def open(self):
        assert self._closed
        
        config = self._dev.get_active_configuration()
        
        # Debug interface is always interface 0
        interface = config[(self.DEBUG_INTERFACE_NUMBER, self.DEBUG_INTERFACE_NUMBER)]
        
        for endpoint in interface:
            if endpoint.bEndpointAddress == self._info.out_ep:
                self._ep_out = endpoint
            elif endpoint.bEndpointAddress == self._info.in_ep:
                self._ep_in = endpoint
            elif endpoint.bEndpointAddress == self._info.swv_ep:
                self._ep_swv = endpoint
        
        if not self._ep_out:
            raise StlinkException("Unable to find OUT endpoint")
        if not self._ep_in:
            raise StlinkException("Unable to find IN endpoint")

        self._max_packet_size = self._ep_out.wMaxPacketSize
        
        usb.util.claim_interface(self._dev, 0)
        
        self._closed = False
        self._start_rx()
    
    def close(self):
        assert not self._closed
        self._closed = True
        self._read_sem.release()
        self._thread.join()
        assert self._receive_data[-1] is None
        self._receive_data = []
        usb.util.release_interface(self._dev, self.DEBUG_INTERFACE_NUMBER)
        usb.util.dispose_resources(self._dev)
        self._ep_out = None
        self._ep_in = None
        self._thread = None

    @property
    def serial_number(self):
        return self._dev.serial_number

    @property
    def version_name(self):
        return self._info.version_name

    @property
    def max_packet_size(self):
        return self._max_packet_size

    @property
    def xfer_counter(self):
        return self._xfer_counter

    def _flush_rx(self):
        # Flush the RX buffers by reading until timeout exception
        try:
            while True:
                self._ep_in.read(self._max_packet_size, 1)
        except usb.core.USBError:
            # USB timeout expected
            pass

    def _start_rx(self):
        self._flush_rx()
        
        # Start RX thread
        self._thread = threading.Thread(target=self._rx_task)
        self._thread.daemon = True
        self._thread.start()

    def _rx_task(self):
        try:
            while not self._closed:
                self._read_sem.acquire()
                if not self._closed:
                    rxData = bytearray(self._ep_in.read(self._max_packet_size, 10 * 1000))
                    self._receive_data.append(rxData)
        finally:
            # Set last element of rcv_data to None on exit
            self._receive_data.append(None)

    def _write(self, data, timeout=1000):
        self._xfer_counter += 1
        count = self._dev.write(self._info.out_ep, data, timeout)
        if count != len(data):
            raise StlinkException("Error, only %d Bytes was transmitted to ST-Link instead of expected %d" % (count, len(data)))

    def _prime_read(self, size):
        for _ in range((size + self._max_packet_size + 1) // self._max_packet_size):
            self._read_sem.release()
    
    def _read(self, size, timeout=1000):
        data = bytearray()
        while len(data) < size:
            while len(self._receive_data) == 0:
                pass
            if self._receive_data[0] is None:
                raise StlinkException("STLink %s read thread exited" % self.serial_number)
            packet = self._receive_data.pop(0)
            data += packet
        assert len(data) >= size, "data len (%d) > size (%d)" % (len(data), size)
        return data[:size]

#         read_size = size
#         # Round up reads to the maximum packet size.
# #         if read_size < self._max_packet_size:
# #             read_size = self._max_packet_size
# #         elif read_size % 4:
# #             read_size += 4 - (read_size & 0x3)
#         data = bytearray(self._dev.read(self._info.in_ep, read_size, timeout))
#         return data #[:size]

    def xfer(self, cmd, writeData=None, readSize=None, retries=0, timeout=1000):
        while True:
            try:
                if len(cmd) > self.CMD_SIZE:
                    raise StlinkException("command is too large (%d bytes, max %d bytes)" % (len(cmd), self.CMD_SIZE))

                # Prime the data in phase so it happens immediately when the device readies the data.
                if readSize is not None:
                    self._prime_read(readSize)

                # Command phase. Pad command to required 16 bytes.
                paddedCmd = bytearray(self.CMD_SIZE)
                paddedCmd[0:len(cmd)] = cmd
                if LOG_USB_DATA:
                    log.debug("  USB CMD> %s" % ' '.join(['%02x' % i for i in paddedCmd]))
                self._write(paddedCmd, timeout)
                
                # Optional data out phase.
                if writeData is not None:
                    if LOG_USB_DATA:
                        log.debug("  USB OUT> %s" % ' '.join(['%02x' % i for i in writeData]))
                    self._write(writeData, timeout)
                
                # Optional data in phase.
                if readSize is not None:
                    data = self._read(readSize)
                    if LOG_USB_DATA:
                        log.debug("  USB IN < %s" % ' '.join(['%02x' % i for i in data]))
                    return data
            except usb.core.USBError as exc:
                # Handle retries.
                if retries > 0:
                    retries -= 1
                    continue
                six.raise_from(StlinkException("USB Error: %s" % exc), exc)
            return None
    
    def __repr__(self):
        return "<{} @ {:#x} vid={:#06x} pid={:#06x} sn={} version={}>".format(
            self.__class__.__name__, id(self),
            self._dev.idVendor, self._dev.idProduct, self.serial_number,
            self.version)
