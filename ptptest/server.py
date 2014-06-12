# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
"""PTP Server"""

import eventlet, eventlet.debug

# Don't patch 'os' because it breaks nonblocking os.read
eventlet.monkey_patch(socket=True, os=False, time=True)
eventlet.debug.hub_prevent_multiple_readers(False)
eventlet.debug.hub_blocking_detection(True)

from eventlet.green import socket
from eventlet.green import time

import __init__ as ptptest
import protocol, hexdump, uuid, ui

PTP_SERVERVER       = 2

def _mkey(addr, port):
    return "%s-%d" % (addr, port)


class Server(object):
    running = True
    args = None
    uuid = uuid.uuid1().bytes
    addr = None
    port = None

    clients = {}
    server_seq = 0
    ui = None

    _clock = eventlet.semaphore.Semaphore()

    def __init__(self, args):
        super(Server, self).__init__()
        self.args = args

        if 'stun' in args and args.stun:
            import stunloop
            self.stun = stunloop.Stun()

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.args.debug: print "Binding server to %s port %d" % (args.server, args.port)
        s.bind((args.server, args.port))
        (self.addr, self.port) = s.getsockname()
        self.sock = s

        self.clients = {}

    def _client_parse(self, buf, sin, client):
        l = protocol.PTP(buf)
        if l is None:
            self.ui.log("Client packet from %s failed to parse!" % repr(sin))
            return False

        client['ts'] = time.time()
        client['stats']['rcvd'] += 1

        if self.args.debug: self.ui.log(repr(l), indent='  ')

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
            elif p.ptp_type == protocol.PTP_TYPE_PTPADDR:
                client['ptpaddr'] = p.data
            elif p.ptp_type == protocol.PTP_TYPE_YOURTS:
                ts = float(p.data) / float(2**32)
                rtt = client['ts'] - ts
                client['stats']['rtt'] = rtt
                client['stats']['ackd'] += 1
                self.ui.log("ACK from client %s; RTT %fs" % (str(sin), rtt))
            elif p.ptp_type == protocol.PTP_TYPE_SHUTDOWN:
                # Client is going away!
                return False

        self.ui.peer_update('client', client['sin'], client['stats'])

        return True

    def _client_respond(self, client, their_ts):
        l = protocol.PTP(data=[])
        l.data = []
        t = protocol.TLV(type=protocol.PTP_TYPE_SERVERVER, data=protocol.UInt(size=1, data=PTP_SERVERVER))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_SEQUENCE, data=protocol.UInt(size=4, data=self.server_seq))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_UUID, data=protocol.String(data=client['uuid']))
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
        self.server_seq += 1L

    def _client_beacons(self):
        with self._clock:
            for k in self.clients:
                self._client_beacon(k, self.clients[k])

    def _client_beacon(self, k, client):
        # We need a list of TLVs and then form a PTP fron them
        l = protocol.PTP(data=[])
        l.data = []

        t = protocol.TLV(type=protocol.PTP_TYPE_SERVERVER, data=protocol.UInt(size=1, data=PTP_SERVERVER))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_SEQUENCE, data=protocol.UInt(size=4, data=self.server_seq))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_UUID, data=protocol.String(data=client['uuid']))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_MYTS, data=protocol.UInt(size=8, data=int(time.time()*2**32)))
        l.data.append(t)
        t = protocol.TLV(type=protocol.PTP_TYPE_YOURADDR, data=protocol.Address(data=client['sin']))
        l.data.append(t)

        # Now add the list of known clients
        count = 0
        for sk in self.clients:
            if sk == k: continue  # skip the client we're sending this to
            sc = self.clients[sk]
            t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTLIST_EXT,
                    data=protocol.Address(data=sc['sin']))
            l.data.append(t)
            count += 1

            # If this client address matches the address we're sending this packet to then we
            # also send its local address - the clients can then try to talk locally
            if sc['sin'][0] == client['sin'][0]:
                t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTLIST_INT,
                        data=protocol.Address(data=sc['ptpaddr']))
                l.data.append(t)

        t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTLEN, data=protocol.UInt(size=1, data=count))
        l.data.append(t)

        packet = l.pack()
        if len(packet) > protocol.PTP_MTU: # bad
            self.ui.log("Ignoring attempt to send %d bytes to client %s. MTU is %d" % \
                    (len(packet), str(client['sin']), protocol.PTP_MTU))
            return

        if self.args.debug:
            self.ui.log("Sending %d bytes to client %s" % (len(packet), str(client['sin'])))
            self.ui.log("%s" % repr(protocol.PTP(packet)), indent='  ')
            if self.args.hexdump:
                self.ui.log(hexdump.hexdump(result='return', data=packet))

        self.sock.sendto(packet, client['sin'])
        client['stats']['sent'] += 1
        self.server_seq += 1L
        self.ui.peer_update('client', client['sin'], client['stats'])

    def _read_loop(self):
        while self.running:
            (buf, sin) = self.sock.recvfrom(protocol.PTP_MTU)
            if self.args.debug: self.ui.log("%d bytes received from %s:%d" % (len(buf), sin[0], sin[1]))
            k = _mkey(sin[0], sin[1])

            send_beacons = False

            # Client we know about?
            with self._clock:
                if k in self.clients:
                    self.ui.log("Received packet from a known client %s" % repr(sin))
                else:
                    self.ui.log("Received packet from a new client %s" % repr(sin))
                    self.clients[k] = {
                            'sin': sin,
                            'stats': {
                                'sent': 0,
                                'rcvd': 0,
                                'ackd': 0,
                                'rtt': 0,
                            },
                    }
                    self.ui.peer_add(group='client', sin=sin)
                    send_beacons = True

                ret = self._client_parse(buf, sin, self.clients[k])
                if ret == False:
                    # Client should be removed
                    self.ui.log("Immediately removing client %s" % repr(sin))
                    self.ui.peer_del(group='client', sin=self.clients[k]['sin'])
                    del(self.clients[k])
                    send_beacons = True

            if send_beacons: # send an immediate update
                self._client_beacons()

    def run(self):
        # Spawn a UI
        self.ui = ui.UI(server=True, parent=self)

        self.ui.title("PTP Server version %s (protocol version %d)" %
                (ptptest.__version__, PTP_SERVERVER), stdout=True)
        self.ui.log("Our socket is %s %s" % (self.addr, self.port), stdout=True)
        self.ui.set_address(self.addr, self.port)

        eventlet.spawn(self._read_loop)

        if self.stun:
            self.stun.set_ui(self.ui)
            eventlet.spawn(self.stun.run)

        client_ts = 0
        while self.running:
            ts = time.time()
            if ts - client_ts > 13:
                client_ts = ts
                # Send our beacons to the clients
                self._client_beacons()

            # See if any clients need to be expired
            with self._clock:
                remove = []
                for k in self.clients:
                    client = self.clients[k]
                    if client['ts'] + 30 < ts:
                        remove.append(k)
                for k in remove:
                    self.ui.log("Expiring client %s" % k)
                    self.ui.peer_del(group='client', sin=self.clients[k]['sin'])
                    del(self.clients[k])

            # Wait a moment
            eventlet.sleep(1)

