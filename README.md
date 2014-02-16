# Point-to-point UDP tester.

This is a simple tool to test some basic and common point-to-point
network protocol techniques. Ostensibly this is to test the various
ways that peers in a PTP mesh can discover and communicate with
each other directly via their various and often broken home routers.


# License.

The MIT License (MIT)

Copyright (c) 2014 Chris Luke

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


# The software.

The client and server are written in Python and should run on most
platforms. It was developed using Python 2.7 and appears to work with
Python 2.6. It would be very suprising if it worked with Python 3.x.
It has some dependencies:

Python packages:

> argparse dpkt eventlet IPy

Ubuntu package names:

> sudo apt-get install -y python-dpkt python-eventlet python-ipy

Fedora package names:

> sudo yum install -y python-dpkt python-eventlet python-IPy

FreeBSD port names:

> devel/py-argparse net/py-dpkt net/py-eventlet net-mgmt/py-ipy

## Running the client.

The runtime syntax is along the lines of:

> ./client --server=[ip address] --port=[port number] --debug

Debug defaults to off, which isn't very interesting at the moment.
Address and port default to the localhost and port 23456.

## Running the server.

The runtime syntax is along the lines of:

> ./server --server=[ip address] --port=[port number] --debug

Debug defaults to off, which isn't very interesting at the moment.
Address and port default to the binding to any address and listening
to port 23456.


# The architecture.

This tester has its own protocol. There are two roles involved in this
protocol: A server and a client.

## The server.

There is generally a small set of servers involved in this type of PTP,
and in many cases just one. The servers job is to coordinate clients.
There are some simple aspects to this coordination:

* Discovery, by a client announcing itself to a server. The client
  would include details about itself. Often it will include any
  information the client has been able to determine, such as local
  IP addresses, external IP addresses, port numbers and in the case
  of subscription services, some account details to link the client
  to a specific service. Often some details can be discovered from the
  metadata of the packet itself, such as the IP address and port number
  the packet originated from.

* Publishing, by telling clients about all the clients known. Clients
  would then start sending their data to new clients in the list. The
  list includes the IP address and port details that PTP peers should
  use to contact each client.

* Purging, by removing clients that have not been seen for a while.
  When a client is being purged, further publications of the client
  list inform all the other clients that one of their peers has gone.

* Analytics, by collecting metrics from the clients and storing them.
  This data will generally include packet counts from tach PTP peer
  and any related performance metrics such as measured delay between
  peers.

## The client.

There can be many clients. Their role is typically to distribute their
state or some other data to other clients.

* Registration, by informing some central server or servers of our
  presence. Typically the client includes some identification data,
  such as account details and sometimes IP address data.

* Discovery, by receiving from one or more servers details on the
  other clients that are available to form a PTP mesh with. These
  details will include IP address and port details. We only send data
  to and accept data from clients that were included in the most recent.
  Similarly, if we don't receive a response from a server, we might try
  a different server, or report that communications are unavailable.

* Publishing, by sending data to other clients that we know about.

* Analytics, by including timestamps in the data.

## Data integrity.

Especially in subscription services, the packets containing this data
would be wrapped in some sort of protection, either to conceal
elements with privacy concerns or to reveal if the data was tampered
with in transit with man-in-the-middle techniques. For most systems
a simple cryptographic signature is sufficient to trust the integrity
of the data and the keys for this can be distributed by the server.
For our system we will do a simple checksum.

# The protocol.

This protocol is entirely UDP based and tries to keep every message
within the size of the de facto MTU of the general internet, 1500 bytes,
to limit fragmentation. To further ameliorate common MTU issues, for
example as a result of PPPoE encapsulation, we limit our packet sizes to
1400 bytes. UDP is considered unreliable and packet fragmentation would
only increase the chances of data loss.

## Header.

The packet header is minimalist. 1-byte protocol version number,
2 byte checksum and then a stream of TLVs.

## TLV.

The UDP packets are binary-encoded TLV streams. Each TLV is encoded
as an 8-bit type indicator, an 8-bit length indicator and then a
variable length number of value bytes, indicated by the length
indicator.

### Base data types.

Each type is comprised of one or more well-defined datatypes:

* Signed integer, network order. 1, 2, 4, 8 byte numbers.
* Unsigned integer, network order. 1, 2, 4, 8 byte numbers.
* ASCII string.
* IP address, network order. Encodes address family, address
and port number.

### Value types.

| Value type | Data type          | Description
| ---------- | ------------------ | -----------
| 0          | Unsigned integer   | Protocol version indicator
| 1          | Unsigned integer   | Client version indicator
| 2          | Unsigned integer   | Server version indicator
| 3          | Unsigned integer   | Sequence counter
| 4          | String             | UUID (16 bytes)
| 8          | Unsigned integer   | "My" timestamp
| 9          | Unsigned integer   | "Your" timestamp
| 32         | Address            | PTP address
| 33         | Address            | Internal address
| 34         | Unsigned integer   | uPNP used
| 64         | Address            | Client list entry

# Future work.

* Currently the client does not try to detect if any other clients are
  on its local network; it should.

* Add some uPNP hooks. We want to be able to test interactions with
  port forwarding on an IGD.

* Add a mechanism for the client to detect its own external IP address.
  This may be useful when looking for local clients, though not reliably
  in a world of increasing CGN.

* Add the option to seperate server and client-side sockets.

* Though most of the code is address family agnostic, IPv6 has not been
  tested

* The client should summarize the clients it talks to as well as those
  it expects to hear from but doesn't.

* Optionally have the client tell the server about the client it was and
  was not able to communicate with.

* Have the server summarize it analytics, perhaps publishing a web page
  for it.

