# Point-to-point UDP tester.

This is a simple tool to test some basic and common point-to-point
network protocol techniques. Ostensibly this is to test the various
ways that peers in a ptp mesh can discover and communicate with
each other directly via their various and often broken home routers.


# The software.

The client and server are written in Python and should run on most
platforms. It has some dependencies:

Python packages:
    dpkt eventlet IPy

Ubuntu package names:
    sudo apt-get install -y python-dpkt python-eventlet python-ipy

Fedora package names:
    sudo yum install -y python-dpkt python-eventlet python-IPy

## Running the client.

## Running the server.


# The architecture.

This tester has its own protocol. There are two roles involved in this
protocol: A server and a client.

## The server.

There is generally a small set of servers involved in this type of ptp,
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
list includes the IP address and port details that ptp peers should
use to contact each client.
* Purging, by removing clients that have not been seen for a while.
When a client is being purged, further publications of the client
list inform all the other clients that one of their peers has gone.
* Analytics, by collecting metrics from the clients and storing them.
This data will generally include packet counts from tach ptp peer
and any related performance metrics such as measured delay between
peers.

## The client.

There can be many clients. Their role is typically to distribute their
state or some other data to other clients.

* Registration, by informing some central server or servers of our
presence. Typically the client includes some identification data,
such as account details and sometimes IP address data.
* Discovery, by receiving from one or more servers details on the
other clients that are available to form a ptp mesh with. These
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
within the size of the MTU of the gemeral internet, 1500 bytes, to
limit fragmentation. UDP is considered unreliable and packet
fragmentation would only increase the chances of data loss.

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


