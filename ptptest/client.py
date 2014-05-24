# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""PTP Client"""

import eventlet, eventlet.debug

eventlet.monkey_patch(socket=True, os=True, time=True)
eventlet.debug.hub_prevent_multiple_readers(False)

from eventlet.green import socket
from eventlet.green import time

import __init__ as ptptest
import protocol, hexdump, uuid, ui
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
    ui = None

    _slock = eventlet.semaphore.Semaphore()
    _clock = eventlet.semaphore.Semaphore()

    def __init__(self, args):
        super(Client, self).__init__()
        self.args = args

        # Discover our local address
        # TODO: Re-do this periodically, in case it changes
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.connect((args.server, int(args.port)))
        self.addr = s.getsockname()[0]
        s.close()

        # Open our main socket, get its port
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', 0))
        self.port = s.getsockname()[1]
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
        if self.args.debug: self.ui.log(repr(l))

        new_clients = []
        num_clients = None

        for tlv in l.data:
            p = tlv.data
            if p.ptp_type == protocol.PTP_TYPE_SERVERVER:
                server['serverver'] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_SEQUENCE:
                server['sequence'] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_UUID:
                server['uuid'] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_MYTS:
                self._server_respond(server, p.data)
                server['myts'] = float(p.data) / float(2**32)
            elif p.ptp_type == protocol.PTP_TYPE_YOURTS:
                ts = float(p.data) / float(2**32)
                self.ui.log("ACK from server %s; RTT %fs" % (str(sin), time.time() - ts))
            elif p.ptp_type == protocol.PTP_TYPE_CLIENTLEN:
                num_clients = p.data
            elif p.ptp_type == protocol.PTP_TYPE_CLIENTLIST:
                new_clients.append(p.data) # should be a sockaddr
            elif p.ptp_type == protocol.PTP_TYPE_YOURADDR:
                self.ui.log("Server sees us as %s" % repr(p.data))

        if num_clients is not None:
            if num_clients == len(new_clients):
                with self._clock:
                    # Sync the client list
                    delete = []
                    for k in self.clients:
                        if not self.clients[k]['sin'] in new_clients: # old
                            delete.append(k)
                    for k in delete:
                        if self.args.debug: self.ui.log("Removing old client %s" % str(self.clients[k]['sin']))
                        del(self.clients[k])
                    for sin in new_clients:
                        k = _mkey(sin[0], sin[1])
                        if k not in self.clients: # new
                            if self.args.debug: self.ui.log("Adding new client %s" % str(sin))
                            self.clients[k] = { 'sin': sin, 'ts': time.time(), 'myseq': 0L }
                    if self.args.debug: self.ui.log("Client count: %d" % len(self.clients))
            else:
                self.ui.log("Mismatch in client list from server")

    def _server_respond(self, server, their_ts):
        l = protocol.PTP(data=[])
        l.data = []
        t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTVER, data=protocol.UInt(size=1, data=PTP_CLIENTVER))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_SEQUENCE, data=protocol.UInt(size=4, data=self.server_seq))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_UUID, data=protocol.String(data=server['uuid']))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_YOURTS, data=protocol.UInt(size=8, data=their_ts))
        l.data.append(t)

        packet = l.pack()
        if len(packet) > protocol.PTP_MTU: # bad
            self.ui.log("Ignoring attempt to send ts %d bytes to server %s. MTU is %d" % \
                    (len(packet), str(server['sin']), protocol.PTP_MTU))
            return

        if self.args.debug:
            self.ui.log("Sending ts %d bytes to server %s" % (len(packet), str(server['sin'])))
            self.ui.log(hexdump.hexdump(result='return', data=packet))

        self.sock.sendto(packet, server['sin'])
        self.server_seq += 1L

    def _server_beacons(self):
        # Tell the server about ourself
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
        t = protocol.TLV(type=protocol.PTP_TYPE_MYTS, data=protocol.UInt(size=8, data=int(time.time()*2**32)))
        l.data.append(t)

        packet = l.pack()
        if len(packet) > protocol.PTP_MTU: # bad
            self.ui.log("Ignoring attempt to send %d bytes to servers. MTU is %d" % (len(packet), protocol.PTP_MTU))
            return

        if self.args.debug:
            self.ui.log("Sending %d bytes to servers:" % len(packet))
            self.ui.log(hexdump.hexdump(result='return', data=packet))

        with self._slock:
            for k in self.servers:
                server = self.servers[k]
                self.sock.sendto(packet, server['sin'])

        self.server_seq += 1L

    def _client_parse(self, buf, sin, client):
        client['ts'] = time.time()
        l = protocol.PTP(buf)
        if self.args.debug: self.ui.log(repr(l))

        for tlv in l.data:
            p = tlv.data
            if p.ptp_type == protocol.PTP_TYPE_CLIENTVER:
                client['clientver'] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_SEQUENCE:
                client['sequence'] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_UUID:
                client['uuid'] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_MYTS:
                self._client_respond(client, p.data)
                client['myts'] = float(p.data) / float(2**32)
            elif p.ptp_type == protocol.PTP_TYPE_YOURTS:
                ts = float(p.data) / float(2**32)
                self.ui.log("ACK from client %s; RTT %fs" % (str(sin), time.time() - ts))

    def _client_respond(self, client, their_ts):
        if not 'myseq' in client or not 'sin' in client: return
        l = protocol.PTP(data=[])
        l.data = []
        t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTVER, data=protocol.UInt(size=1, data=PTP_CLIENTVER))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_SEQUENCE, data=protocol.UInt(size=4, data=client['myseq']))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_UUID, data=protocol.String(data=self.uuid))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_YOURTS, data=protocol.UInt(size=8, data=their_ts))
        l.data.append(t)

        packet = l.pack()
        if len(packet) > protocol.PTP_MTU: # bad
            self.ui.log("Ignoring attempt to send ts %d bytes to client %s. MTU is %d" % \
                    (len(packet), str(client['sin']), protocol.PTP_MTU))
            return

        if self.args.debug:
            self.ui.log("Sending ts %d bytes to client %s" % (len(packet), str(client['sin'])))
            self.ui.log(hexdump.hexdump(result='return', data=packet))

        self.sock.sendto(packet, client['sin'])
        client['myseq'] += 1

    def _client_beacons(self):
        with self._clock:
            for k in self.clients:
                client = self.clients[k]
                if not 'myseq' in client or not 'sin' in client: continue
                if 'uuid' in client and client['uuid'] == self.uuid: continue # self!

                l = protocol.PTP(data=[])
                l.data = []

                t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTVER, data=protocol.UInt(size=1, data=PTP_CLIENTVER))
                l.data.append(t)
                t = protocol.TLV(type=protocol.PTP_TYPE_SEQUENCE, data=protocol.UInt(size=4, data=client['myseq']))
                l.data.append(t)
                t = protocol.TLV(type=protocol.PTP_TYPE_UUID, data=protocol.String(data=self.uuid))
                l.data.append(t)
                t = protocol.TLV(type=protocol.PTP_TYPE_MYTS, data=protocol.UInt(size=8, data=int(time.time()*2**32)))
                l.data.append(t)

                packet = l.pack()
                if len(packet) > protocol.PTP_MTU: # bad
                    self.ui.log("Ignoring attempt to send ts %d bytes to client %s. MTU is %d" % \
                            (len(packet), str(client['sin']), protocol.PTP_MTU))
                    return

                if self.args.debug:
                    self.ui.log("Sending ts %d bytes to client %s" % (len(packet), str(client['sin'])))
                    self.ui.log(hexdump.hexdump(result='return', data=packet))

                self.sock.sendto(packet, client['sin'])
                client['myseq'] += 1

    def _read_loop(self):
        while self.running:
            (buf, sin) = self.sock.recvfrom(protocol.PTP_MTU)
            if self.args.debug: self.ui.log("%d bytes received from %s:%d" % (len(buf), sin[0], sin[1]))
            k = _mkey(sin[0], sin[1])

            # See if it was the server
            with self._slock:
                if k in self.servers:
                    self._server_parse(buf, sin, self.servers[k])
                else:
                    # Client we know about?
                    with self._clock:
                        if k in self.clients:
                            if self.args.debug: self.ui.log("Known client")
                            self._client_parse(buf, sin, self.clients[k])
                        else:
                            if self.args.debug: self.ui.log("Unknown client")

    def run(self):
        print "PTP Client version %s (protocol version %d)" % (ptptest.__version__, PTP_CLIENTVER)

        # Get ourselves a UI
        self.ui = ui.UI(client=True, parent=self)

        self.ui.log("Our socket is %s %s" % (self.addr, self.port))

        eventlet.spawn(self._read_loop)

        ts = 0
        while self.running:
            if time.time() - ts > 7:
                ts = time.time()
                # Send our server beacons
                self._server_beacons()

            # Send a message to the clients
            self._client_beacons()

            # Wait a moment
            eventlet.sleep(0)

