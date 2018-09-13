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

from __future__ import print_function
from . import JLinkError
import usb.core
import usb.util
import logging
import six

log = logging.getLogger('jlink.usb')

## @brief J-Link Device Driver
class JLinkUSBInterface(object):
    # USB vendor and product IDs
    USB_IDS = [
            # Most J-Links
            {
                'vid' : 0x1366,
                'pid' : 0x0101,
            },
        ]

    @classmethod
    def _usb_match(cls, dev):
        try:
            for devType in cls.USB_IDS:
                if dev.idVendor == devType['vid'] and dev.idProduct == devType['pid']:
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
        return [cls(dev) for dev in devices]

    def __init__(self, dev):
        self.usb_dev = dev
        self.usb_read_timeout = 5000
        self.usb_write_timeout = 5000
        self.readbuffer = bytearray()
        self.readoffset = 0
        self.readbuffer_chunksize = 4096
        self.writebuffer_chunksize = 4096
        self.interface = None
        self.index = None
        self.in_ep = None
        self.out_ep = None
    
    @property
    def serial_number(self):
        return self.usb_dev.serial_number

    @property
    def product_name(self):
        return self.usb_dev.product

    def open(self, interface=1):
        """Open a new interface to the specified J-Link device"""
        assert self.usb_dev is not None
        self.usb_dev.set_configuration(1)
        config = self.usb_dev.get_active_configuration()
        # detect invalid interface as early as possible
        if interface > config.bNumInterfaces:
            raise JLinkError('No such J-Link port: %d' % interface)
        self._set_interface(config, interface)
        self.max_packet_size = self._get_max_packet_size()

    def close(self):
        """Close the J-Link interface"""
        pass

    def write_data(self, data):
        """Write data in chunks to the chip"""
        offset = 0
        size = len(data)
        try:
            while offset < size:
                write_size = self.writebuffer_chunksize
                if offset + write_size > size:
                    write_size = size - offset
                length = self._write(data[offset:offset+write_size])
                if length <= 0:
                    raise JLinkError("Usb bulk write error")
                offset += length
            return offset
        except usb.core.USBError as e:
            six.raise_from(JLinkError('USB error while reading from JLink: %s' % str(e)), e)

    def read_data(self, size, attempt=1):
        """Read data in chunks from the chip."""
        # Packet size sanity check
        if not self.max_packet_size:
            raise JLinkError("max_packet_size is bogus")
        packet_size = self.max_packet_size
        length = 1 # initial condition to enter the usb_read loop
        data = bytearray()
        
        # everything we want is still in the cache?
        if size <= len(self.readbuffer) - self.readoffset:
            data = self.readbuffer[self.readoffset : self.readoffset + size]
            self.readoffset += size
            return data
        
        # something still in the cache, but not enough to satisfy 'size'?
        if len(self.readbuffer) - self.readoffset != 0:
            data = self.readbuffer[self.readoffset:]
            # end of readbuffer reached
            self.readoffset = len(self.readbuffer)
        
        # read from USB, filling in the local cache as it is empty
        try:
            while (len(data) < size) and (length > 0):
                while True:
                    tempbuf = self._read()
                    print("readbuf=",repr(tempbuf))
                    attempt -= 1
                    length = len(tempbuf)
                    if length > 0:
                        # skip the status bytes
                        chunks = (length + packet_size - 1) // packet_size
                        count = packet_size
                        self.readbuffer = bytearray()
                        self.readoffset = 0
                        srcoff = 0
                        for i in range(chunks):
                            self.readbuffer += tempbuf[srcoff : srcoff + count]
                            srcoff += packet_size
                        length = len(self.readbuffer)
                        break
                    else:
                        # no data received, may be late, try again
                        if attempt > 0:
                            continue
                        # no actual data
                        self.readbuffer = bytearray()
                        self.readoffset = 0
                        # no more data to read?
                        return data
                if length > 0:
                    # data still fits in buf?
                    if (len(data) + length) <= size:
                        data += self.readbuffer[self.readoffset : self.readoffset + length]
                        self.readoffset += length
                        # did we read exactly the right amount of bytes?
                        if len(data) == size:
                            return data
                    else:
                        # partial copy, not enough bytes in the local cache to
                        # fulfill the request
                        part_size = min(size-len(data), len(self.readbuffer)-self.readoffset)
                        assert part_size >= 0, "Internal Error"
                        data += self.readbuffer[self.readoffset:self.readoffset+part_size]
                        self.readoffset += part_size
                        return data
        except usb.core.USBError as e:
            six.raise_from(JLinkError('USB error while writing to JLink: %s' % str(e)), e)
        
        # (hopefully!) never reached
        raise JLinkError("Internal error")

    def _set_interface(self, config, ifnum):
        """Select the interface to use on the J-Link device"""
        if ifnum == 0:
            ifnum = 1
        if ifnum-1 not in range(config.bNumInterfaces):
            raise ValueError("No such interface for this device")
        self.index = ifnum
        self.interface = config[(ifnum-1, 0)]
        endpoints = sorted([ep.bEndpointAddress for ep in self.interface])
        self.in_ep, self.out_ep = endpoints[:2]

    def _write(self, data):
        """Write using the API introduced with pyusb 1.0.0b2"""
        return self.usb_dev.write(self.in_ep, data, self.usb_write_timeout)

    def _read(self):
        """Read using the API introduced with pyusb 1.0.0b2"""
        return self.usb_dev.read(self.out_ep, self.readbuffer_chunksize, self.usb_read_timeout)

    def _get_max_packet_size(self):
        """Retrieve the maximum length of a data packet"""
        assert self.usb_dev, "Device is not yet known"
        assert self.interface, "Interface is not yet known"
        endpoint = self.interface[0]
        packet_size = endpoint.wMaxPacketSize
        return packet_size

