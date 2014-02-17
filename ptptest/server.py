# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# 
# Copyright (c) 2014 Chris Luke <chrisy@flirble.org>
"""PTP Server"""

import eventlet, eventlet.debug
from eventlet.green import socket

import protocol, time, hexdump, uuid

PTP_SERVERVER       = 1

eventlet.debug.hub_prevent_multiple_readers(False)

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

    def __init__(self, args):
        super(Server, self).__init__()
        self.args = args

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print "Binding server to %s port %d" % (args.server, args.port)
        s.bind((args.server, args.port))
        (self.addr, self.port) = s.getsockname()
        self.sock = s

        self.clients = {}

    def _client_parse(self, buf, sin, client):
        client['ts'] = time.time()
        l = protocol.PTP(buf)
        if self.args.debug: print repr(l)

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
                print "ACK from client %s; RTT %fs" % (str(sin), time.time() - ts)

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
            print "Ignoring attempt to send ts %d bytes to client %s. MTU is %d" % \
                    (len(packet), str(client['sin']), protocol.PTP_MTU)
            return

        if self.args.debug:
            print "Sending ts %d bytes to client %s" % (len(packet), str(client['sin']))
            hexdump.hexdump(packet)

        self.sock.sendto(packet, client['sin'])
        self.server_seq += 1L

    def _client_beacons(self):
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
            t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTLIST, data=protocol.Address(data=sc['sin']))
            l.data.append(t)
            count += 1

        t = protocol.TLV(type=protocol.PTP_TYPE_CLIENTLEN, data=protocol.UInt(size=1, data=count))
        l.data.append(t)

        packet = l.pack()
        if len(packet) > protocol.PTP_MTU: # bad
            print "Ignoring attempt to send %d bytes to client %s. MTU is %d" % \
                    (len(packet), str(client['sin']), protocol.PTP_MTU)
            return

        if self.args.debug:
            print "Sending %d bytes to client %s" % (len(packet), str(client['sin']))
            hexdump.hexdump(packet)

        self.sock.sendto(packet, client['sin'])
        self.server_seq += 1L

    def _read_loop(self):
        while self.running:
            (buf, sin) = self.sock.recvfrom(protocol.PTP_MTU)
            if self.args.debug: print "%d bytes received from %s:%d" % (len(buf), sin[0], sin[1])
            k = _mkey(sin[0], sin[1])

            new_client = False

            # Client we know about?
            if k in self.clients:
                if self.args.debug: print "Known client"
            else:
                if self.args.debug: print "New client"
                self.clients[k] = {
                        'sin': sin
                }
                new_client = True
            self._client_parse(buf, sin, self.clients[k])

            if new_client: # send an immediate update
                self._client_beacons()

    def run(self):
        eventlet.spawn(self._read_loop)
        ts = 0
        while self.running:
            if time.time() - ts > 13:
                ts = time.time()
                # Send our beacons to the clients
                self._client_beacons()

            # See if any clients need to be expired
            remove = []
            for k in self.clients:
                client = self.clients[k]
                if client['ts'] + 30 < time.time():
                    remove.append(k)
            for k in remove:
                if self.args.debug: print "Expiring client %s" % k
                del(self.clients[k])

            # Wait a moment
            eventlet.sleep(1)

