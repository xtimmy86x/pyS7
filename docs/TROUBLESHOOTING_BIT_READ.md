# Troubleshooting: INVALID_DATA_SIZE Error for BIT Data Type

## Problem

When trying to read individual bits from an S7 PLC, you may encounter an error like:

```
pyS7.errors.S7ReadResponseError: S7Tag(memory_area=<MemoryArea.DB: 132>, db_number=1, data_type=<DataType.BIT: 1>, start=0, bit_offset=2, length=1): INVALID_DATA_SIZE
```

Some PLC/configuration combinations may reject native individual BIT reads with an `INVALID_DATA_SIZE` error code.

## Root Cause

pyS7 does not currently maintain a verified list of affected CPU models, firmware versions, or PLC configurations. In particular, the repository does not contain enough hardware evidence to attribute this response solely to firmware or to determine whether optimized DB configuration is correlated with it.

## Solution

### Optimized reads (default)

With `optimize=True`, pyS7 intentionally reads the byte containing every requested BIT and extracts the requested bit from that byte. This applies to isolated BITs as well as multiple BITs in the same byte. The API still returns `bool` values in the requested order.

```python
from pyS7 import S7Client

client = S7Client(address="192.168.1.100", rack=0, slot=1)
client.connect()

result = client.read(["DB1,X0.2"], optimize=True)
print(result[0])  # bool
```

This is a proactive optimized-read strategy, not an error-driven retry: pyS7 does not first send a native BIT request and does not generate duplicate network traffic. BITs sharing a containing byte use one byte work item, which the optimizer may merge with adjacent ranges when safe.

### Native reads for diagnostics

```python
result = client.read(["DB1,X0.2"], optimize=False)
```

Setting `optimize=False` preserves the native S7 BIT read. This is useful for advanced users and protocol diagnostics, but affected PLC/configuration combinations may reject it.

### BIT writes

BIT writes remain native S7 bit-level writes. pyS7 does not use a byte-level read-modify-write sequence, which could overwrite concurrent changes to other bits in the same byte.

### Manual byte reading and bit extraction

You can always read the entire byte and extract the specific bit manually:

```python
# Read the byte containing the bit
byte_data = client.read(["DB1,B0"])  # Read byte 0 of DB1
byte_value = byte_data[0]

# Extract bit 2 (third bit from the right, 0-indexed)
bit_2_value = bool((byte_value >> 2) & 1)
print(f"Bit 2 value: {bit_2_value}")
```

## Understanding Bit Positions

Bits are numbered from 0-7 within a byte, where:
- Bit 0 is the least significant bit (rightmost)
- Bit 7 is the most significant bit (leftmost)

Example: For byte value `0b00000100` (decimal 4):
- Bit 0 = 0 (False)
- Bit 1 = 0 (False)
- Bit 2 = 1 (True)   ← This is the bit that was causing the error
- Bit 3 = 0 (False)
- ... and so on

For PLC-side prerequisites such as PUT/GET permission and absolute-offset-compatible
DB layout, consult the documentation for the specific CPU, firmware, and TIA Portal
configuration, and see pyS7's [compatibility matrix](COMPATIBILITY.md). Siemens
optimized block access is unrelated to pyS7's `optimize=True` read option.
