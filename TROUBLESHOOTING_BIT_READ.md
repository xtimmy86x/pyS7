# Troubleshooting: INVALID_DATA_SIZE Error for BIT Data Type

## Problem

When trying to read individual bits from an S7 PLC, you may encounter an error like:

```
pyS7.errors.S7ReadResponseError: S7Tag(memory_area=<MemoryArea.DB: 132>, db_number=1, data_type=<DataType.BIT: 1>, start=0, bit_offset=2, length=1): INVALID_DATA_SIZE
```

This error occurs because some S7 PLCs do not support reading individual bits directly and will return an `INVALID_DATA_SIZE` error code.

## Root Cause

The issue stems from PLC firmware limitations where certain S7 controllers require bit operations to be performed on byte-aligned data rather than individual bit addresses. When the PLC receives a request to read a single bit, it may reject the request with an `INVALID_DATA_SIZE` error.

## Solution

### Option 1: Use the Built-in Workaround Function

The library now provides an enhanced error message and a utility function to help work around this limitation:

```python
from pyS7 import S7Client, extract_bit_from_byte

client = S7Client(address="192.168.1.100", rack=0, slot=1)
client.connect()

try:
    # Try direct bit read first
    result = client.read(["DB1,X0.2"])
except Exception as e:
    if "INVALID_DATA_SIZE" in str(e):
        # Use workaround: read entire byte and extract the bit
        byte_value = client.read(["DB1,B0"])[0]  # Read the byte
        bit_value = extract_bit_from_byte(byte_value, 2)  # Extract bit 2
        print(f"Bit value: {bit_value}")
```

### Option 2: Use Optimized Read Operations

Optimized read operations may handle bit reads more effectively:

```python
# This might work better for some PLCs
result = client.read_optimized(["DB1,X0.2"])
```

### Option 3: Manual Byte Reading and Bit Extraction

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

## Alternative Approaches

1. **Check PLC Documentation**: Some PLCs may have specific requirements for bit addressing
2. **Use Word/Byte Operations**: Consider reading larger data blocks and processing multiple bits at once
3. **Update PLC Firmware**: Newer firmware versions may have better support for individual bit operations
4. **Use Different Memory Areas**: Some memory areas (like Merker/Memory bits) may have better bit access support

## Prevention

To avoid this issue in new code:
1. Always wrap individual bit reads in try-catch blocks
2. Consider reading bytes and extracting bits as the primary approach for problematic PLCs
3. Test bit read operations early in your development cycle
4. Use the provided `extract_bit_from_byte()` utility function for consistent bit extraction