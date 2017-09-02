"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2017 ARM Limited

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
import enum

class TraceEvent(object):
    pass

class TraceOverflow(TraceEvent):
    pass

class TraceTimestamp(TraceEvent):
    pass

class TraceITMEvent(TraceEvent):
    pass

class TraceEventCounter(TraceEvent):
    pass

class TraceExceptionTrace(TraceEvent):
    pass

class TracePeriodicPC(TraceEvent):
    pass

class SWOParser(object):
    CPI_MASK = 0x01
    EXC_MASK = 0x02
    SLEEP_MASK = 0x04
    LSU_MASK = 0x08
    FOLD_MASK = 0x10
    CYC_MASK = 0x20
    
    FN_MSGS = ("Entered", "Exited", "Returned")
    
    def __init__(self, file):
        self.reset()
        self._file = file
    
    def reset(self):
        self._bytes_parsed = 0
        self._itm_page = 0
        self._parser = self._parse()
        self._parser.next()

    def parse(self, data):
        for value in data:
            self._parser.send(value)
            self._bytes_parsed += 1
        
    def _parse(self):
        while True:
            byte = yield
            hdr = byte
            
            # Sync packet
            if hdr == 0:
                packets = 0
                while True:
                    # Check for final 1 bit after at least 5 all-zero sync packets
                    if (packets >= 5) and (byte == 0x80):
                        break
                    elif byte == 0:
                        packets += 1
                    else:
                        # Get early non-zero packet, reset sync packet counter.
                        packets = 0
                    byte = yield
                self._itm_page = 0
                self._file.write("{:08x}: Sync ({:d} packets)\n".format(self._bytes_parsed, packets))
            # Protocol packet
            elif (hdr & 0x3) == 0:
                c = (hdr >> 7) & 0x1
                d = (hdr >> 4) & 0b111
                # Overflow packet.
                if hdr == 0x70:
                    self._file.write("Overflow\n")
                # Local timestamp.
                elif (hdr & 0xf) == 0 and d not in (0x0, 0x3):
                    ts = 0
                    tc = 0
                    # Local timestamp packet format 1.
                    if c == 1:
                        tc = (hdr >> 4) & 0x3
                        while c == 1:
                            byte = yield
                            ts = (ts << 7) | (byte & 0x7f)
                            c = (byte >> 7) & 0x1
                    # Local timestamp packet format 2.
                    else:
                        ts = (hdr >> 4) & 0x7
                    self._file.write("{:08x}: Local timestamp: TC={:#4x} TS={:d}\n".format(self._bytes_parsed, tc, ts))
                # Global timestamp.
                elif hdr in (0b10010100, 0b10110100):
                    t = (hdr >> 5) & 0x1
                # Extension.
                elif (hdr & 0x8) == 0x8:
                    sh = (hdr >> 2) & 0x1
                    if c == 0:
                        ex = (hdr >> 4) & 0x7
                    else:
                        ex = 0
                        while c == 1:
                            byte = yield
                            ex = (ex << 7) | (byte & 0x7f)
                            c = (byte >> 7) & 0x1
                    if sh == 0:
                        self._file.write("{:08x}: ITM PAGE: {:#x}\n".format(self._bytes_parsed, ex))
                    else:
                        self._file.write("{:08x}: Extension: SH={:d} EX={:#x}\n".format(self._bytes_parsed, sh, ex))
                # Reserved.
                else:
                    pass
            # Source packet
            else:
                ss = hdr & 0x3
                l = 1 << (ss - 1)
                a = (hdr >> 3) & 0x1f
                if l == 1:
                    payload = yield
                elif l == 2:
                    byte1 = yield
                    byte2 = yield
                    payload = (byte1 | 
                                (byte2 << 8))
                else:
                    byte1 = yield
                    byte2 = yield
                    byte3 = yield
                    byte4 = yield
                    payload = (byte1 | 
                                (byte2 << 8) |
                                (byte3 << 16) |
                                (byte4 << 24))
                # Instrumentation packet.
                if (hdr & 0x4) == 0:
                    port = (self._itm_page * 32) + a
                    self._file.write("{:08x}: ITM: port={:d} data={:#010x}\n".format(self._bytes_parsed, port, payload))
                # Hardware source packet.
                else:
                    # Event counter
                    if a == 0:
                        self._file.write("{:08x}: DWT: Event:{}\n".format(self._bytes_parsed, self._get_event_desc(payload)))
                    # Exception trace
                    elif a == 1:
                        exceptionNumber = payload & 0x1ff
                        fn = (payload >> 12) & 0x3
                        fnMsg = SWOParser.FN_MSGS[fn - 1]
                        self._file.write("{:08x}: DWT: Exc #{:d} {}\n".format(self._bytes_parsed, exceptionNumber, fnMsg))
                    # Periodic PC
                    elif a == 2:                        
                        self._file.write("{:08x}: DWT: PC={:#010x}\n".format(self._bytes_parsed, payload))
                    # Data trace
                    elif 8 <= a <= 23:
                        type = (hdr >> 6) & 0x3
                        cmpn = (hdr >> 4) & 0x3
                        bit3 = (hdr >> 3) & 0x1
                        # PC value
                        if type == 0b01 and bit3 == 0:
                            self._file.write("{:08x}: DWT: CMPn={:d} PC={:#010x}\n".format(self._bytes_parsed, cmpn, payload))
                        # Address
                        elif type == 0b01 and bit3 == 1:
                            self._file.write("{:08x}: DWT: CMPn={:d} Daddr[15:0]={:#06x}\n".format(self._bytes_parsed, cmpn, payload))
                        # Data value
                        elif type == 0b10:
                            dir = "Read" if (bit3 == 0) else "Write"
                            self._file.write("{:08x}: DWT: CMPn={:d} Dvalue={:#010x} {}\n".format(self._bytes_parsed, cmpn, payload, dir))
                    else:
                        self._file.write("{:08x}: DWT: id={:d} data={:#010x} (invalid id!)\n".format(self._bytes_parsed, a, payload))
    
    def _get_event_desc(self, evt):
        msg = ""
        if evt & SWOParser.CYC_MASK:
            msg += " Cyc"
        if evt & SWOParser.FOLD_MASK:
            msg += " Fold"
        if evt & SWOParser.LSU_MASK:
            msg += " LSU"
        if evt & SWOParser.SLEEP_MASK:
            msg += " Sleep"
        if evt & SWOParser.EXC_MASK:
            msg += " Exc"
        if evt & SWOParser.CPI_MASK:
            msg += " CPI"
        return msg
        


