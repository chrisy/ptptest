# Point-to-point UDP tester

This is a simple tool to test some basic and common point-to-point
network protocol techniques. Ostensibly this is to test the various
ways that peers in a PTP mesh can discover and communicate with
each other directly via their various and often broken home routers.


# The software

The client and server are written in Python and should run on most
platforms. It uses Urwid to provide a pretty console-based user
interface; this works well on all kinds of POSIX systems and also
works with Cygwin on Windows platforms; it will also run with win32
Python on Windows with curses support.

It was developed using Python 2.7 and appears to work with
Python 2.6. It would be very suprising if it worked with Python 3.x.

## Dependencies

The software has some dependencies.


Python packages:

> pip install argparse dpkt eventlet IPy urwid pystun bson

Pip doesn't always want to install `dpkt`, but `dpkt-fix` seems to install,
and work, fine.

On Windows, if you are not using Cygwin, you may also need:

> pip install cursesw

## Packaged dependencies

If you are using a system that has packages, you could probably use
these commands below to install the required packages.

However, `pystun` and `bson` may be esoteric enough to not be packaged. To 
work around this, they are available as sub-modules in the Git repository. To
fetch them, use `git submodule init && git submodule update`.


### Ubuntu

> sudo apt-get install -y python-dpkt python-eventlet python-ipy python-urwid

### Fedora

> sudo yum install -y python-dpkt python-eventlet python-IPy python-urwid

### FreeBSD

> portmaster devel/py-argparse net/py-dpkt net/py-eventlet net-mgmt/py-ipy devel/py-urwid

### MacOS/X

On MacOS/X you can either use `pip` as above, or if you use MacPorts:

> sudo port install py27-dpkt py27-eventlet py27-ipy py27-urwid 


## Running the client

The runtime syntax is along the lines of:

```
usage: ptpclient [-h] [-s <address>] [-p <port>] [--nostun] [-d] [--hexdump]
                 [--curses] [--loglines <int>]

PTP Mesh Client

optional arguments:
  -h, --help            show this help message and exit
  -s <address>, --server <address>
                        The address of the server [127.0.0.1]
  -p <port>, --port <port>
                        The port to use on the server [23456]
  --nostun              Don't use STUN
  -d, --debug           Enable debugging output
  --hexdump             Enable hexdump debugging output
  --curses              Force use of curses
  --loglines <int>      Number of lines high to for the log window [10]
```

Debug defaults to off, which isn't very interesting at the moment.
Address and port default to the localhost and port 23456. You can
use `--help` to see other options available.

## Running the server

The runtime syntax is along the lines of:

```
usage: ptpserver [-h] [-s <address>] [-p <port>] [--nostun] [-d] [--hexdump]
                 [--curses] [--loglines <int>]

PTP Mesh Server

optional arguments:
  -h, --help            show this help message and exit
  -s <address>, --server <address>
                        The address to bind to for the server [0.0.0.0]
  -p <port>, --port <port>
                        The port to use for the server [23456]
  --nostun              Don't use STUN
  -d, --debug           Enable debugging output
  --hexdump             Enable hexdump debugging output
  --curses              Force use of curses
  --loglines <int>      Number of lines high to for the log window [10]
```

Debug defaults to off, which isn't very interesting at the moment.
Address and port default to the binding to any address and listening
to port 23456. You can use `--help` to see other options available.


# The architecture

This tool has its own protocol. There are two roles involved in this
protocol: A server and a client.

## The server

There is generally a small set of servers involved in this type of PTP,
and in many cases just one. The servers primary job is to coordinate
clients though it is also possible that it can also be a client and
participate in client-focused PtP exchanges.

There are some simple aspects to this coordination:

* Discovery, by a client announcing itself to a server. The client
  would include details about itself. Often it will include any
  information the client has been able to determine, such as local
  IP addresses, external IP addresses, port numbers and in the case
  of subscription services, some account details to link the client
  to a specific service. Often some details can be discovered from the
  metadata of the packet itself, such as the IP address and port number
  the packet originated from.

* Publishing, by a server telling clients about all the clients known.
  Clients would then start sending their data to new clients in the
  list. The list includes the IP address and port details that PTP peers
  should use to contact each client.

* Purging, by removing clients that have not been seen for a while.
  When a client is being purged, further publications of the client
  list inform all the other clients that one of their peers has gone.

* Analytics, by collecting metrics from the clients and storing them.
  This data will generally include packet counts from tach PTP peer
  and any related performance metrics such as measured delay between
  peers.

## The client

There can be and generally will be many clients. The client role is
typically to distribute its state or other data to other clients.

* Registration, by informing some central server or servers of our
  presence. Typically the client includes some identification data,
  such as account details and sometimes IP address data.

* Discovery, by receiving from one or more servers details on the
  other clients that are available to form a PTP mesh with. These
  details will include IP address and port details. We only send data
  to and accept data from clients that were included in the most recent.
  Similarly, if we don't receive a response from a server, we might try
  a different server, or report that communications are unavailable.

* Publishing, by sending data to other clients that we know about. This
  is the primary means for data transfer, either by the unsolicitced
  sending of information or using it to request details from another
  client (or a set of clients).

* Analytics, by including timestamps and other metrics in the data.

## Data integrity

Especially in subscription services, the packets containing this data
would be wrapped in some sort of protection, either to conceal
elements with privacy concerns or to reveal if the data was tampered
with in transit with man-in-the-middle techniques. For most systems
a simple cryptographic signature is sufficient to trust the integrity
of the data and the keys for this can be distributed by the server.
For our system we will do a simple checksum.

# The protocol

This protocol is entirely UDP based and will refuse to send any message
larger than 1400 bytes. This size is chosen because the de-facto MTU
of the general Internet is 1500 bytes. Overhead from tunneled access
providers, such as those which use PPPoE, reduces this.

UDP is considered unreliable and packet fragmentation would
only increase the chances of data loss.

## Header

The packet header is minimalist with just a 1-byte protocol version number
ahed of the stream of TLVs. A 2 byte checksum is appended after the TLVs.

## TLV

The UDP packets are binary-encoded TLV streams. Each TLV is encoded
as an 8-bit value type indicator, an 8-bit value length indicator and
then a variable length number of value bytes, indicated by the length
indicator.

### Base data types

Each data type is comprised of one or more well-defined datatypes:

* Signed integer, network order. 1, 2, 4, 8 byte numbers.
* Unsigned integer, network order. 1, 2, 4, 8 byte numbers.
* Text string. Any byte stream would also use.
* IP address, network order. Encodes address family, address
and port number.
* JSON object. ASCII-encoded JSON objects.
* BSON object.

### Value types

The TLV decoder will always decode values by looking up the value type
in a table that maps each value type to a specific data type; the table
below reflects this mapping.

| Value type | Value type name          | Data type          | Description
| ---------- | ------------------------ | ------------------ | -----------
| 0          | PTP_TYPE_PROTOVER        | Unsigned integer   | Protocol version indicator
| 1          | PTP_TYPE_SERVERVER       | Unsigned integer   | Server version indicator
| 2          | PTP_TYPE_CLIENTVER       | Unsigned integer   | Client version indicator
| 3          | PTP_TYPE_SEQUENCE        | Unsigned integer   | Sequence counter
| 4          | PTP_TYPE_UUID            | String             | UUID (16 bytes)
| 8          | PTP_TYPE_MYTS            | Unsigned integer   | "My" timestamp
| 9          | PTP_TYPE_YOURTS          | Unsigned integer   | "Your" timestamp
| *Client-server* |||
| 32         | PTP_TYPE_PTPADDR         | Address            | PTP address
| 33         | PTP_TYPE_INTADDR         | Address            | Internal address
| 34         | PTP_TYPE_UPNP            | Unsigned integer   | uPNP used
| 35         | PTP_TYPE_META            | JSON               | Various metadata
| 45         | PTP_TYPE_SHUTDOWN        | Unsigned integer   | Client is shutting down
| *Server-client* |||
| 64         | PTP_TYPE_CLIENTLIST_EXT  | Address            | Client list entry (external address)
| 65         | PTP_TYPE_CLIENTLEN       | Unsigned integer   | Client list entry count (int+ext)
| 66         | PTP_TYPE_YOURADDR        | Unsigned integer   | Client address as seen by server
| 67         | PTP_TYPE_CLIENTLIST_INT  | Address            | Client list entry (local address)
| *Client-client* |||
| 96         | PTP_TYPE_CC              | String             | Experimental extension


# Protocol mechanisms

The protocol implements some mechanisms for higher-level functionality
such as RTT measurement and the transfer of arbitrarily large objects.

## RTT measurment mechanism

TODO: Describe the action: sent TSV with MYTS, other end responds
with a message containing YOURTS.

## Bulk transfer mechanism

Two modes: Local client requests object and the remote responds to that
request, or a remote client sends an object without solicitation.

The receiving client is responsible for managing the transfer by requesting
outstanding blocks. Currently this targets a specific sender though a
later iteration may discover which clients have the blocks required and
request these blocks from any such client that can satisfy the request.

Sending of object:

* Sender informs receiver of transfer intent, containing details
  such as request ID, object name, total size, block transfer size,
  checksum and other useful data. Note this transfer must fit inside
  a single packet.

* Receiver then becomes responsible for requesting blocks from the
  sender.

* Blocks can be requested in any order, though it is expected initial
  requests will be sequential.

* All blocks except the last one will be of the same size, the
  advertised block size. The last block may be less than this.

* Receiver can send multiple requests in parallel and is responsible
  for limiting the number of requests that are in flight. The number
  can increase/decrease depending on delay and throughput (aka, sliding
  window).

* Receiver is responsible for managing retries of blocks that did not
  arrive. Receiver is responsible for giving up if individual blocks
  fail to arrive after an excessive number of retries.

* Receiver must inform the sender when reception is complete so that the
  sender can clean up its state.

* If the sender does not hear from the receiver regarding a transfer
  after some period of time it may forget any state is has about the
  transfer and ignore future requests regarding the transfer.


# Future work

In no particular order:

* Add some uPNP hooks. We want to be able to test interactions with
  port forwarding on an IGD.

* Provide a mechanism for the server to relay packets between clients
  if their NAT mode doesn't allow direct delivery. This may require
  distribution of NAT modes for each client to other clients.

* Use the results from STUN to determine the PtP mechanism to use.

* Add the option to seperate server and client-side sockets.

* Though most of the code is address family agnostic, IPv6 has not been
  tested.

* Track packets sent; when the response doesn't arrive (after a timeout)
  then count it as lost.

* Track RTT's of last N packets so we can measure average and jitter.

* Optionally have the client tell the server about the clients it was and
  was not able to communicate with.

* Have the server summarize its analytics, perhaps publishing a web page
  for it.

* Distribute 'binary' versions for Win32 and MacOS/X.

* Transfers of objects larger than a packet will carry, such as files.



# License

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
