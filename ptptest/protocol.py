# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
#
# The MIT License (MIT)
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
#     The above copyright notice and this permission notice shall be included in all
#     copies or substantial portions of the Software.
# 
#     THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#     IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#     FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#     AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#     LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#     OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#     SOFTWARE.
# 
"""PTP TLV Protocol"""

import struct, dpkt, exceptions, IPy

# Parameters
PTP_VERSION         = 1
PTP_MTU             = 1400

# Protocol TLV types
# General
PTP_TYPE_PROTOVER   = 0
PTP_TYPE_SERVERVER  = 1
PTP_TYPE_CLIENTVER  = 2
PTP_TYPE_SEQUENCE   = 3
PTP_TYPE_UUID       = 4

PTP_TYPE_MYTS       = 8
PTP_TYPE_YOURTS     = 9

# Client-server
PTP_TYPE_PTPADDR    = 32
PTP_TYPE_INTADDR    = 33
PTP_TYPE_UPNP       = 34

# Server-client
PTP_TYPE_CLIENTLIST = 64

# Client-client
PTP_TYPE_CC         = 96


class Base(dpkt.Packet):
    __hdr__ = (
    )

    ptp_type = None


class UInt(Base):
    size = 4

    def _stof(self):
        if self.size == 1: return 'B'
        if self.size == 2: return 'H'
        if self.size == 4: return 'I'
        if self.size == 8: return 'Q'
        raise exceptions.RuntimeError('Unknown unsigned integer size %d', self.size)

    def unpack(self, buf):
        self.size = len(buf)
        super(UInt, self).unpack(buf)
        self.data = struct.unpack('!%s' % self._stof(), self.data)

    def __len__(self):
        return self.size

    def __str__(self):
        return struct.pack('!%s' % self._stof(), self.data)


class Int(Base):
    size = 4

    def _stof(self):
        if self.size == 1: return 'b'
        if self.size == 2: return 'h'
        if self.size == 4: return 'i'
        if self.size == 8: return 'q'
        raise exceptions.RuntimeError('Unknown integer size %d', self.size)

    def unpack(self, buf):
        self.size = len(buf)
        super(UInt, self).unpack(buf)
        self.data = struct.unpack('!%s' % self._stof(), self.data)

    def __len__(self):
        return self.size

    def __str__(self):
        return struct.pack('!%s' % self._stof(), self.data)


class String(Base):
    pass


def pack_sin(sin):
    """Takes a sin tuple (addr, port) and packs it into a
    binary form. Resulting size depends on whether addr
    is IPv4 or IPv6."""
    (addr, port) = sin
    addr = IPy.IPint(addr)
    if addr.version() == 4:
        return struct.pack("!IH", addr.int(), port)
    else:
        a = addr.int()
        return struct.pack("!QQH", a >> 64, a % 2**64, port)
        #return struct.pack("!QQH", a >> 64, a & (2**64 - 1), port)

def unpack_sin(data):
    if len(data) == 6: # IPv4
        (a, port) = struct.unpack("!IH", data)
        addr = IPy.IPint(a)
    elif len(data) == 18: #IPv6
        (a, b, port) = struct.unpack("!QQH", data)
        addr = IPy.IPint(a << 64 + b)
    return (str(addr), port)


class Address(Base):
    __hdr__ = (
    )

    def unpack(self, buf):
        dpkt.Packet.unpack(self, buf)
        self.data = unpack_sin(self.data)

    def __len__(self):
        if ':' in self.data[0]:
            return self.__hdr_len__ + 18
        return self.__hdr_len__ + 6

    def __str__(self):
        return self.pack_hdr() + pack_sin(self.data)


PTP_MAP = {
        PTP_TYPE_PROTOVER: UInt,
        PTP_TYPE_SERVERVER: UInt,
        PTP_TYPE_CLIENTVER: UInt,
        PTP_TYPE_SEQUENCE: UInt,
        PTP_TYPE_UUID: String,

        PTP_TYPE_MYTS: UInt,
        PTP_TYPE_YOURTS: UInt,

        PTP_TYPE_PTPADDR: Address,
        PTP_TYPE_INTADDR: Address,
        PTP_TYPE_UPNP: UInt,

        PTP_TYPE_CLIENTLIST: Address,

        PTP_TYPE_CC: String,
}


class TLV(dpkt.Packet):
    __hdr__ = (
        ('type', 'B', 0),
        ('len', 'B', 4)
    )

    def __init__(self, *args, **kwargs):
        super(TLV, self).__init__(*args, **kwargs)
        if hasattr(self.data, 'ptp_type'):
            self.data.ptp_type = self.type

    def unpack(self, buf):
        dpkt.Packet.unpack(self, buf)
        self.data = self.data[:self.len - 2]
        cls = Base
        if self.type in PTP_MAP:
            cls = PTP_MAP[self.type]
        else:
            raise exceptions.RuntimeError("Unknown TLV type %d" % self.type)

        self.data = cls(self.data, ptp_type=self.type)

    def __len__(self):
        return self.__hdr_len__ + len(self.data)
    
    def __str__(self):
        self.len = len(self)
        return self.pack_hdr() + str(self.data)


class PTP(dpkt.Packet):
    __hdr__ = (
        ('version', 'B', PTP_VERSION),
        ('sum', 'H', 0)
    )
    data = []

    def unpack(self, buf):
        dpkt.Packet.unpack(self, buf)
        buf = self.data
        l = []
        while buf:
            tlv = TLV(buf)
            l.append(tlv)
            buf = buf[len(tlv):]
        self.data = l

    def __len__(self):
        return self.__hdr_len__ + sum(map(len, self.data))

    def __str__(self):
        data = ''.join(map(str, self.data))
        if not self.sum:
            self.sum = dpkt.in_cksum(self.pack_hdr() + data)
        return self.pack_hdr() + data

