# pyS7 3.1.0 release notes

## Siemens TIME support

pyS7 3.1.0 adds Siemens `TIME` as the logical `DataType.TIME` datatype. Parsed
string addresses use DB-only syntax such as `DB1,TIME100`. `TIME` arrays are
also available programmatically by constructing an `S7Tag`.

Both synchronous and asynchronous clients support `TIME` across normal,
detailed, and batch APIs. Reads support `optimize=True` and `optimize=False`.

## Python representation

Reading `DB1,TIME100` returns a `datetime.timedelta`, and writing the address
accepts a `timedelta`:

```python
from datetime import timedelta

value = client.read(["DB1,TIME100"])[0]
client.write(
    ["DB1,TIME100"],
    [timedelta(seconds=1)],
)
```

Values retain exact millisecond precision and use the full signed 32-bit
millisecond range. Sub-millisecond values are rejected rather than rounded or
truncated. Integer millisecond values, including `bool`, are intentionally not
accepted; callers must use `timedelta`.

## Protocol compatibility

The PLC variable remains declared as Siemens `TIME`, and pyS7 continues to
decode its four-byte signed millisecond payload as `DataType.TIME`. Native reads
use the compatible S7ANY DINT transfer type because real S7-1200 hardware
rejected the native S7ANY TIME code with `UNSUPPORTED_DATA_TYPE`. This wire
transfer detail does not change the public `timedelta` semantics.

## Hardware validation

The maintainer validated `TIME` on real Siemens S7-1200 hardware. Validation
covered reads and writes, zero and positive and negative values, exact
millisecond values, `optimize=True`, `optimize=False`, mixed `TIME` and `DINT`
reads, and adjacent-variable integrity.

No current `TIME` hardware-validation claim is made for other Siemens PLC
families.

## Compatibility

`TIME` uses four-byte, big-endian, signed int32 millisecond storage. Parsed
string syntax is DB-only in 3.1.0; use `S7Tag` for programmatic arrays.

## Upgrade notes

This is an additive minor release. Existing datatype and client APIs retain
their 3.0 behavior. Applications adopting `TIME` should pass and expect
`datetime.timedelta` values and should not pass raw integer milliseconds.
