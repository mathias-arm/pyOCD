"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2013 ARM Limited

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

import logging
import array
from .dap_access_api import DAPAccessIntf
import six

COMMAND_ID = {'DAP_INFO': 0x00,
              'DAP_LED': 0x01,
              'DAP_CONNECT': 0x02,
              'DAP_DISCONNECT': 0x03,
              'DAP_TRANSFER_CONFIGURE': 0x04,
              'DAP_TRANSFER': 0x05,
              'DAP_TRANSFER_BLOCK': 0x06,
              'DAP_TRANSFER_ABORT': 0x07,
              'DAP_WRITE_ABORT': 0x08,
              'DAP_DELAY': 0x09,
              'DAP_RESET_TARGET': 0x0a,
              'DAP_SWJ_PINS': 0x10,
              'DAP_SWJ_CLOCK': 0x11,
              'DAP_SWJ_SEQUENCE': 0x12,
              'DAP_SWD_CONFIGURE': 0x13,
              'DAP_JTAG_SEQUENCE': 0x14,
              'DAP_JTAG_CONFIGURE': 0x15,
              'DAP_JTAG_IDCODE': 0x16,
              'DAP_SWO_TRANSPORT': 0x17,
              'DAP_SWO_MODE': 0x18,
              'DAP_SWO_BAUDRATE': 0x19,
              'DAP_SWO_CONTROL': 0x1A,
              'DAP_SWO_STATUS': 0x1B,
              'DAP_SWO_DATA': 0x1C,
              'DAP_TI_INFO': 0x1D,
              'DAP_TI_VALUE': 0x1E,
              'DAP_TI_CAPTURE': 0x1F,
              'DAP_TI_TRANSFERBLOCK': 0x20,
              'DAP_SWD_SEQUENCE': 0x21,
              'DAP_QUEUE_COMMANDS': 0x7E,
              'DAP_EXECUTE_COMMANDS': 0x7F,
              'DAP_VENDOR0': 0x80,
              }

ID_INFO = {'VENDOR_ID': 0x01,
           'PRODUCT_ID': 0x02,
           'SERIAL_NUMBER': 0x03,
           'CMSIS_DAP_FW_VERSION': 0x04,
           'TARGET_DEVICE_VENDOR': 0x05,
           'TARGET_DEVICE_NAME': 0x06,
           'CAPABILITIES': 0xf0,
           'TEST_DOMAIN_TIMER': 0xf1,
           'TRACE_DATA_MANAGEMENT': 0xf2,
           'SWO_BUFFER_SIZE': 0xfd,
           'PACKET_COUNT': 0xfe,
           'PACKET_SIZE': 0xff,
           }

CAPABILITIES = {'SWD': 0x01,
                'JTAG': 0x02,
                'SWO_UART': 0x04,
                'SWO_MANCHESTER': 0x08,
                'ATOMIC_COMMANDS': 0x10,
                'DAP_SWD_SEQUENCE': 0x20,
                'TEST_DOMAIN_TIMER': 0x40,
                'TRACE_DATA_MANAGEMENT': 0x100,
                }

PINS = {'None': 0x00,
        'SWCLK_TCK': (1 << 0),
        'SWDIO_TMS': (1 << 1),
        'TDI': (1 << 2),
        'TDO': (1 << 3),
        'nTRST': (1 << 5),
        'nRESET': (1 << 7),
        }

DAP_DEFAULT_PORT = 0
DAP_SWD_PORT = 1
DAP_JTAG_POR = 2

DAP_LED_CONNECT = 0
DAP_LED_RUNNING = 1

# Options for DAP_SWO_TRANSPORT command.
class DAP_SWO_TRANSPORT:
    NONE = 0
    DAP_SWO_DATA = 1

# SWO mode options.
class DAP_SWO_MODE:
    OFF = 0
    UART = 1
    MANCHESTER = 2

# SWO control acions.
class DAP_SWO_CONTROL:
    STOP = 0
    START = 1

# SWO status masks.
class DAP_SWO_STATUS:
    CAPTURE = 0x01
    ERROR = 0x40
    OVERRUN = 0x80

DAP_OK = 0
DAP_ERROR = 0xff

# Responses to DAP_Transfer and DAP_TransferBlock
DAP_TRANSFER_OK = 1
DAP_TRANSFER_WAIT = 2
DAP_TRANSFER_FAULT = 4
DAP_TRANSFER_NO_ACK = 7

## @brief This class implements the CMSIS-DAP wire protocol.
class CMSIS_DAP_Protocol(object):
    def __init__(self, interface):
        self.interface = interface

    def dapInfo(self, id_):
        if not type(id_) in (six.integer_types):
            id_ = ID_INFO[id_]
        cmd = []
        cmd.append(COMMAND_ID['DAP_INFO'])
        cmd.append(id_)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_INFO']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] == 0:
            return

        # Integer values
        if id_ in (ID_INFO['CAPABILITIES'], ID_INFO['SWO_BUFFER_SIZE'], ID_INFO['PACKET_COUNT'], ID_INFO['PACKET_SIZE'], ID_INFO['TEST_DOMAIN_TIMER']):
            if resp[1] == 1:
                return resp[2]
            if resp[1] == 2:
                return (resp[3] << 8) | resp[2]
            if resp[1] == 4:
                return (resp[5] << 24) | (resp[4] << 16) | (resp[3] << 8) | resp[2]
        elif id_ == ID_INFO['TRACE_DATA_MANAGEMENT']:
            blockCount = (resp[3] << 8) | resp[2]
            blockSize = (resp[5] << 8) | resp[4]
            return blockCount, blockSize

        # String values. They are sent as C strings with a terminating null char, so we strip it out.
        x = array.array('B', [i for i in resp[2:2 + resp[1]]]).tostring()
        if x[-1] == '\x00':
            x = x[0:-1]
        return x

    def setLed(self, type, enabled):
        cmd = []
        cmd.append(COMMAND_ID['DAP_LED'])
        cmd.append(type)
        cmd.append(int(enabled))
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_LED']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != 0:
            # Second response byte must be 0
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def connect(self, mode=DAP_DEFAULT_PORT):
        cmd = []
        cmd.append(COMMAND_ID['DAP_CONNECT'])
        cmd.append(mode)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_CONNECT']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] == 0:
            # DAP connect failed
            raise DAPAccessIntf.CommandError()

        if resp[1] == 1:
            logging.info('DAP SWD MODE initialized')

        if resp[1] == 2:
            logging.info('DAP JTAG MODE initialized')

        return resp[1]

    def disconnect(self):
        cmd = []
        cmd.append(COMMAND_ID['DAP_DISCONNECT'])
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_DISCONNECT']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP Disconnect failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def writeAbort(self, data, dap_index=0):
        cmd = []
        cmd.append(COMMAND_ID['DAP_WRITE_ABORT'])
        cmd.append(dap_index)
        cmd.append((data >> 0) & 0xff)
        cmd.append((data >> 8) & 0xff)
        cmd.append((data >> 16) & 0xff)
        cmd.append((data >> 24) & 0xff)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_WRITE_ABORT']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP Write Abort failed
            raise DAPAccessIntf.CommandError()

        return True

    def resetTarget(self):
        cmd = []
        cmd.append(COMMAND_ID['DAP_RESET_TARGET'])
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_RESET_TARGET']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP Reset target failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def transferConfigure(self, idle_cycles=0x00, wait_retry=0x0050, match_retry=0x0000):
        cmd = []
        cmd.append(COMMAND_ID['DAP_TRANSFER_CONFIGURE'])
        cmd.append(idle_cycles)
        cmd.append(wait_retry & 0xff)
        cmd.append(wait_retry >> 8)
        cmd.append(match_retry & 0xff)
        cmd.append(match_retry >> 8)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_TRANSFER_CONFIGURE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP Transfer Configure failed
            raise DAPAccessIntf.CommandError()

        return resp[1]


    def setSWJClock(self, clock=1000000):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWJ_CLOCK'])
        cmd.append(clock & 0xff)
        cmd.append((clock >> 8) & 0xff)
        cmd.append((clock >> 16) & 0xff)
        cmd.append((clock >> 24) & 0xff)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWJ_CLOCK']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP SWJ Clock failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def setSWJPins(self, output, pin, wait=0):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWJ_PINS'])
        try:
            p = PINS[pin]
        except KeyError:
            logging.error('cannot find %s pin', pin)
            return
        cmd.append(output & 0xff)
        cmd.append(p)
        cmd.append(wait & 0xff)
        cmd.append((wait >> 8) & 0xff)
        cmd.append((wait >> 16) & 0xff)
        cmd.append((wait >> 24) & 0xff)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWJ_PINS']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        return resp[1]

    def swdConfigure(self, conf=0):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWD_CONFIGURE'])
        cmd.append(conf)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWD_CONFIGURE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP SWD Configure failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def swjSequence(self, data):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWJ_SEQUENCE'])
        cmd.append(len(data) * 8)
        for i in range(len(data)):
            cmd.append(data[i])
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWJ_SEQUENCE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP SWJ Sequence failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def jtagSequence(self, info, tdi):
        cmd = []
        cmd.append(COMMAND_ID['DAP_JTAG_SEQUENCE'])
        cmd.append(1)
        cmd.append(info)
        cmd.append(tdi)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_JTAG_SEQUENCE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP JTAG Sequence failed
            raise DAPAccessIntf.CommandError()

        return resp[2]

    def jtagConfigure(self, irlen, dev_num=1):
        cmd = []
        cmd.append(COMMAND_ID['DAP_JTAG_CONFIGURE'])
        cmd.append(dev_num)
        cmd.append(irlen)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_JTAG_CONFIGURE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # DAP JTAG Configure failed
            raise DAPAccessIntf.CommandError()

        return resp[2:]

    def jtagIDCode(self, index=0):
        cmd = []
        cmd.append(COMMAND_ID['DAP_JTAG_IDCODE'])
        cmd.append(index)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_JTAG_IDCODE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # Operation failed
            raise DAPAccessIntf.CommandError()

        return  (resp[2] << 0) | \
                (resp[3] << 8) | \
                (resp[4] << 16) | \
                (resp[5] << 24)

    def swoTransport(self, transport):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWO_TRANSPORT'])
        cmd.append(transport)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWO_TRANSPORT']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # Operation failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def swoMode(self, mode):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWO_MODE'])
        cmd.append(mode)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWO_MODE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # Operation failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def swoBaudrate(self, baudrate):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWO_BAUDRATE'])
        cmd.append(baudrate & 0xff)
        cmd.append((baudrate >> 8) & 0xff)
        cmd.append((baudrate >> 16) & 0xff)
        cmd.append((baudrate >> 24) & 0xff)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWO_BAUDRATE']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        return  (resp[1] << 0) | \
                (resp[2] << 8) | \
                (resp[3] << 16) | \
                (resp[4] << 24)

    def swoControl(self, action):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWO_CONTROL'])
        cmd.append(action)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWO_CONTROL']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        if resp[1] != DAP_OK:
            # Operation failed
            raise DAPAccessIntf.CommandError()

        return resp[1]

    def swoStatus(self):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWO_STATUS'])
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWO_STATUS']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        return (resp[1],
                    (resp[2] << 0) | \
                    (resp[3] << 8) | \
                    (resp[4] << 16) | \
                    (resp[5] << 24)
                )

    def swoData(self, count):
        cmd = []
        cmd.append(COMMAND_ID['DAP_SWO_DATA'])
        cmd.append(count & 0xff)
        cmd.append((count >> 8) & 0xff)
        self.interface.write(cmd)

        resp = self.interface.read()
        if resp[0] != COMMAND_ID['DAP_SWO_DATA']:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        status = resp[1]
        count = (resp[2] << 0) | \
                    (resp[3] << 8)
        if count > 0:
            data = resp[4:]
        else:
            data = []
        return (status, count, data)

    def vendor(self, index, data):
        cmd = []
        cmd.append(COMMAND_ID['DAP_VENDOR0'] + index)
        cmd.extend(data)
        self.interface.write(cmd)

        resp = self.interface.read()

        if resp[0] != COMMAND_ID['DAP_VENDOR0'] + index:
            # Response is to a different command
            raise DAPAccessIntf.DeviceError()

        return resp[1:]
