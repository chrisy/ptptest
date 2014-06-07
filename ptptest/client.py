# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
# 
"""PTP Client"""

import eventlet, eventlet.debug

# Don't patch 'os' because it breaks nonblocking os.read
eventlet.monkey_patch(socket=True, os=False, time=True)
eventlet.debug.hub_prevent_multiple_readers(False)
eventlet.debug.hub_blocking_detection(True)

from eventlet.green import socket
from eventlet.green import time

import __init__ as ptptest
import protocol, hexdump, uuid, ui

PTP_CLIENTVER       = 2

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
                    'stats': {
                        'sent': 0,
                        'rcvd': 0,
                        'ackd': 0,
                        'rtt': 0,
                    },
                },
        }
        self.clients = {}

    def _server_parse(self, buf, sin, server):
        l = protocol.PTP(buf)
        if l is None:
            self.ui.log("Server packet from %s failed to parse!" % repr(sin))
            return False

        server['ts'] = time.time()
        server['stats']['rcvd'] += 1

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
                rtt = server['ts'] - ts
                server['stats']['rtt'] = rtt
                server['stats']['ackd'] += 1
                self.ui.log("ACK from server %s; RTT %fs" % (str(sin), rtt))
            elif p.ptp_type == protocol.PTP_TYPE_CLIENTLEN:
                num_clients = p.data
            elif p.ptp_type == protocol.PTP_TYPE_CLIENTLIST_EXT:
                new_clients.append(p.data) # should be a sockaddr
            elif p.ptp_type == protocol.PTP_TYPE_CLIENTLIST_INT:
                # server thinks the previous address may be on the same
                # network as us, so has sent us a clients internal address
                # This is crude, but we just overwrite the previous address for now
                new_clients[-1] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_YOURADDR:
                self.ui.log("Server sees us as %s" % repr(p.data))

        self.ui.peer_update('server', server['sin'], server['stats'])

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
                        self.ui.peer_del(group='client', sin=self.clients[k]['sin'])
                        del(self.clients[k])
                    for sin in new_clients:
                        k = _mkey(sin[0], sin[1])
                        if k not in self.clients: # new
                            if self.args.debug: self.ui.log("Adding new client %s" % str(sin))
                            self.clients[k] = {
                                'sin': sin,
                                'ts': time.time(),
                                'myseq': 0L,
                                'stats': {
                                    'sent': 0,
                                    'rcvd': 0,
                                    'ackd': 0,
                                    'rtt': 0,
                                },
                            }
                            self.ui.peer_add(group='client', sin=sin)
                    if self.args.debug: self.ui.log("Client count: %d" % len(self.clients))
            else:
                self.ui.log("Mismatch in client list from server")

        return True

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
            self.ui.log("%s" % repr(protocol.PTP(packet)), indent='  ')
            if self.args.hexdump:
                self.ui.log(hexdump.hexdump(result='return', data=packet))

        self.sock.sendto(packet, server['sin'])
        self.server_seq += 1L

    def _server_beacons(self, shutdown=False):
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
        if shutdown:
            t = protocol.TLV(type=protocol.PTP_TYPE_SHUTDOWN, data=protocol.UInt(size=1, data=1))
            l.data.append(t)
        else:
            t = protocol.TLV(type=protocol.PTP_TYPE_MYTS,
                    data=protocol.UInt(size=8, data=int(time.time()*2**32)))
            l.data.append(t)

        packet = l.pack()
        if len(packet) > protocol.PTP_MTU: # bad
            self.ui.log("Ignoring attempt to send %d bytes to servers. MTU is %d" % (len(packet), protocol.PTP_MTU))
            return

        if self.args.debug:
            self.ui.log("Sending %d bytes to servers:" % len(packet))
            self.ui.log("%s" % repr(protocol.PTP(packet)), indent='  ')
            if self.args.hexdump:
                self.ui.log(hexdump.hexdump(result='return', data=packet))

        with self._slock:
            for k in self.servers:
                server = self.servers[k]
                server['stats']['sent'] += 1
                self.sock.sendto(packet, server['sin'])
                self.ui.peer_update('server', server['sin'], server['stats'])

        self.server_seq += 1L

    def _client_parse(self, buf, sin, client):
        l = protocol.PTP(buf)
        if l is None:
            self.ui.log("Client packet from %s failed to parse!" % repr(sin))
            return False

        client['ts'] = time.time()
        client['stats']['rcvd'] += 1

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
                rtt = client['ts'] - ts
                client['stats']['rtt'] = rtt
                client['stats']['ackd'] += 1
                self.ui.log("ACK from client %s; RTT %fs" % (str(sin), rtt))

        self.ui.peer_update('client', client['sin'], client['stats'])
        return True

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
            self.ui.log("%s" % repr(protocol.PTP(packet)), indent='  ')
            if self.args.hexdump:
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
                    self.ui.log("%s" % repr(protocol.PTP(packet)), indent='  ')
                    if self.args.hexdump:
                        self.ui.log(hexdump.hexdump(result='return', data=packet))

                self.sock.sendto(packet, client['sin'])
                client['stats']['sent'] += 1
                client['myseq'] += 1
                self.ui.peer_update('client', client['sin'], client['stats'])

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
        # Get ourselves a UI
        self.ui = ui.UI(client=True, parent=self)

        self.ui.title("PTP Client version %s (protocol version %d)" %
            (ptptest.__version__, PTP_CLIENTVER), stdout=True)
        self.ui.log("Our socket is %s %s" % (self.addr, self.port), stdout=True)

        eventlet.spawn(self._read_loop)

        # Add our servers to the peer list
        with self._slock:
            for sk in self.servers:
                server = self.servers[sk]
                self.ui.peer_add(group='server', sin=server['sin'])

        server_ts = 0
        client_ts = 0
        while self.running:
            ts = time.time()
            if ts - server_ts > 7:
                server_ts = ts
                # Send our server beacons
                self._server_beacons()

            if ts - client_ts > 0.5:
                client_ts = ts
                # Send a message to the clients
                self._client_beacons()

            # Wait a moment
            eventlet.sleep(0.05)

        # Shutting down, try to tell servers
        self._server_beacons(shutdown=True)

