# Experimental S7CommPlus symbolic access

S7CommPlus is the newer Siemens protocol used by S7-1200 and S7-1500 PLCs.
Optimized data blocks do not have a stable public byte layout: their variables
must be addressed by an AccessArea and an ordered LID (local identifier) path.

This backend is deliberately separate. Continue to use `S7Client` and
`AsyncS7Client` for classic S7Comm/S7ANY configurations. There is no automatic
selection or fallback. S7CommPlus support is experimental and its API may evolve
before it is declared stable.

## Supported subset

Phase 1/2 implements ISO-on-TCP (TPKT/COTP), InitSSL negotiation, an
**unauthenticated protocol V1 session**, and raw GetMultiVariables /
SetMultiVariables symbolic access. Protocol V2/V3 integrity/authentication and
TLS are not implemented. Consequently, support is expected only for older or
appropriately configured S7-1200/1500 firmware that accepts an unauthenticated
V1 session. It has not yet been verified on real hardware. TLS verification is
not weakened: TLS is simply unavailable in this phase.

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
