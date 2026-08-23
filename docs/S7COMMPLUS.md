# Experimental S7CommPlus symbolic access

S7CommPlus is the newer Siemens protocol used by S7-1200 and S7-1500 PLCs.
Optimized data blocks do not have a stable public byte layout: their variables
must be addressed by an AccessArea and an ordered LID (local identifier) path.

This backend is deliberately separate. Continue to use `S7Client` and
`AsyncS7Client` for classic S7Comm/S7ANY configurations. There is no automatic
selection or fallback. S7CommPlus support is experimental and its API may evolve
before it is declared stable.

## Supported subset

Phase 1/2 implements ISO-on-TCP (TPKT/COTP), InitSSL probing, an
**unauthenticated protocol V1 session**, and raw GetMultiVariables /
SetMultiVariables symbolic access. The CreateObject response is the source of
the negotiated protocol version. Protocol V2/V3 integrity, SessionKey/HMAC,
authentication, and TLS-in-COTP are not implemented; those modes fail at
session negotiation with a typed, version-bearing exception rather than later
as a malformed data operation. Plaintext V3 is not merely V1 with a different
frame byte: known hardware flows require session activation and integrity/HMAC
state, so claiming it without that security state would be unsafe.

Consequently, support is expected only for older or appropriately configured
S7-1200/1500 firmware that accepts an unauthenticated V1 session. It has not
yet been verified on real hardware. TLS verification is not weakened: TLS is
simply unavailable in this phase. S7CommPlus TLS records are tunneled inside
COTP data frames, so wrapping the TCP socket with ``ssl.wrap_socket()`` would
be architecturally incorrect.

```python
from pyS7.s7commplus import S7CommPlusClient, db_access_area

with S7CommPlusClient("192.168.0.1") as client:
    raw = client.read_symbolic(
        access_area=db_access_area(1),
        access_sequence=(0x10, 0x03),
        symbol_crc=0,
    )
    print(raw.hex(" "))
```

Writing takes the same address plus raw bytes. Symbolic addresses are never
translated into classic byte offsets. `S7SymbolicTag` is an immutable, hashable
container for an already-known address.

Automatic discovery is intentionally absent. There is no PLC browsing, DB
enumeration, EXPLORE/type-info parser, UDT tree, symbolic-name resolution, or
tag cache. Obtain the AccessArea/LID path from an engineering capture (for
example, a TIA Portal online read inspected in Wireshark), or provide a path
from existing engineering metadata. Browsing is planned for a later phase.

No Siemens dictionaries or code/data from LGPL S7CommPlusDriver were included.
The wire design was cross-checked against the MIT python-snap7 implementation
and the Wireshark protocol model; licensing provenance must be reviewed again
before importing future protocol tables or dictionaries.

## Async cancellation

``AsyncS7CommPlusClient`` currently uses ``asyncio.to_thread()`` rather than a
native asyncio transport. Every connect, disconnect, read, and write is run off
the event-loop thread and serialized by one session lock. Cancelling a caller
cannot stop an already-running operating-system socket call; the facade keeps
the lock until the worker exits and then propagates cancellation. This prevents
a later coroutine from overlapping the cancelled request and consuming its
response or sequence number.
