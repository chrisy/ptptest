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
"""PTP Client"""

import eventlet
from eventlet.green import socket

import protocol, time, hexdump, uuid

PTP_CLIENTVER       = 1

def _mkey(addr, port):
    return "%s-%d" % (addr, port)

class Client(object):
    running = True
    args = None
    uuid = uuid.uuid1().bytes
    addr = None
    port = None

    servers = {}
    clients = {}
    server_seq = 0

    def __init__(self, args):
        super(Client, self).__init__()
        self.args = args

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', 0))
        (self.addr, self.port) = s.getsockname()
        self.sock = s

        sk = _mkey(args.server, int(args.port))
        self.servers = {
                sk: {
                    'sin': (args.server, int(args.port)),
                    'ts': time.time(),
                },
        }
        self.clients = {}

    def _server_parse(self, buf, sin, server):
        server['ts'] = time.time()
        l = protocol.PTP(buf)

    def _server_beacons(self):
        # Tell the server about ourself
        # We need a list of TLVs and them form a PTP fron them
        l = protocol.PTP(data=[])
        l.data = []

        t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTVER, data=protocol.UInt(size=1, data=PTP_CLIENTVER))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_SEQUENCE, data=protocol.UInt(size=4, data=self.server_seq))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_UUID, data=protocol.String(data=self.uuid))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_PTPADDR, data=protocol.Address(data=(self.addr, self.port)))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_CC, data=protocol.String(data="Hello, world!"))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_MYTS, data=protocol.UInt(size=8, data=int(time.time()*2**32)))
        l.data.append(t)

        packet = l.pack()
        if len(packet) > protocol.PTP_MTU: # bad
            print "Ignoring attempt to send %d bytes to servers. MTU is %d" % (len(packet), protocol.PTP_MTU)
            return

        if self.args.debug:
            print "Sending %d bytes to servers:" % len(packet)
            hexdump.hexdump(packet)

        for k in self.servers:
            server = self.servers[k]
            self.sock.sendto(packet, server['sin'])

        self.server_seq += 1L

    def _client_parse(self, buf, sin, client):
        client['ts'] = time.time()
        l = protocol.PTP(buf)

    def _client_respond(self, their_ts):
        pass

    def _client_beacons(self):
        pass

    def _read_loop(self):
        while self.running:
            (buf, sin) = self.sock.recvfrom(protocol.PTP_MTU)
            if debug: print "%d bytes received from %s:%d" % (len(buf), sin[0], sin[1])
            k = self._mkey(sim[0], sin[1])

            # See if it was the server
            if k in self.servers:
                self._server_parse(buf, sin, self.servers[k])
            else:
                # Client we know about?
                if k in self.clients:
                    if debug: print "Known client"
                    self._client_parse(buf, sin, self.clients[k])
                else:
                    if debug: print "Unknown client"

    def run(self):
        print "Our socket is %s %s" % (self.addr, self.port)

        eventlet.spawn(self._read_loop)
        ts = 0
        while self.running:
            if time.time() - ts > 5:
                ts = time.time()
                # Send our server beacons
                self._server_beacons()

            # Send a message to the clients
            self._client_beacons()

            # Wait a moment
            eventlet.sleep(1)

