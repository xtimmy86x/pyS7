# CPU Information Reading - Technical Notes

## Overview
This document explains how CPU information is retrieved using SZL (System Status List) protocol and clarifies discrepancies with TIA Portal.

## SZL 0x0011 - Module Identification

### Structure
Each module record in SZL 0x0011 contains 28 bytes:

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-1 | 2 bytes | Index | Module index (e.g., 0x0001 for CPU) |
| 2-21 | 20 bytes | Order Number | ASCII string (e.g., "6ES7 211-1BE40-0XB0") |
| 22-23 | 2 bytes | Reserved | Reserved/unknown |
| 24-25 | 2 bytes | Hardware Version | Version encoding (see below) |
| 26-27 | 2 bytes | Firmware Version | Version encoding (not reliable on all PLCs) |

### Hardware Version Decoding

The hardware version is encoded differently depending on the PLC model:

**S7-1200 Example (tested on 6ES7 211-1BE40-0XB0):**
- Byte 24: `0x00` (unused/zero)
- Byte 25: `0x0E` (14 decimal)
- **Result**: V14
- **Encoding**: Decimal value in byte 25

**Other PLCs (S7-300/400 style):**
- Byte 24: `0x56` → High nibble=5, Low nibble=6
- **Result**: V5.6
- **Encoding**: BCD nibbles in byte 24

Our implementation handles both formats:
```python
if hw_byte1 > 0:
    # Format 1: Nibbles contain version (V5.6)
    hw_major = (hw_byte1 >> 4) & 0x0F
    hw_minor = hw_byte1 & 0x0F
    module["hardware_version"] = f"V{hw_major}.{hw_minor}"
else:
    # Format 2: Byte 2 contains decimal version (V14)
    module["hardware_version"] = f"V{hw_byte2}"
```

### Firmware Version Issue

**Problem**: TIA Portal shows `V 4.5.2` but SZL 0x0011 bytes 26-27 contain `0x20 0x20` (spaces).

**Tested Scenarios**:
1. ✅ SZL 0x0011: Returns order number and hardware version correctly
2. ❌ SZL 0x001C (Component Identification): Returns error code `0x85` (not supported on S7-1200)
3. ❌ Firmware field in SZL 0x0011: Contains spaces (`0x20 0x20`), not version data

**Conclusion**: 
- The firmware version `V 4.5.2` shown in TIA Portal likely comes from:
  - The project file (user configuration)
  - A different SZL ID not universally supported (e.g., 0x001C, 0x0F12)
  - Initial connection handshake data
- S7-1200 PLCs do not consistently expose firmware version via SZL queries
- Our implementation returns `"N/A"` when firmware data is not available

## Test Results

### Your S7-1200 PLC (6ES7 211-1BE40-0XB0)

**TIA Portal shows:**
```
Order Number: 6ES7 211-1BE40-0XB0
Hardware: 14
Firmware: V 4.5.2
```

**pyS7 reads (SZL 0x0011):**
```python
{
    'module_type_name': '6ES7 211-1BE40-0XB0',  # ✅ Matches
    'hardware_version': 'V14',                   # ✅ Matches
    'firmware_version': 'N/A',                   # ❌ Not available in this SZL
    'index': '0x0001'
}
```

### Raw Bytes Analysis

**First module record (bytes 0-27):**
```
Offset  Hex                                      ASCII/Decoded
------  ---------------------------------------- -----------------
0-1     00 01                                    Index: 0x0001
2-21    36 45 53 37 20 32 31 31 2D 31 42 45     "6ES7 211-1BE4"
        34 30 2D 30 58 42 30 20                 "0-0XB0 "
22-23   00 00                                    Reserved
24-25   00 0E                                    HW: 0x000E = 14 dec = V14
26-27   20 20                                    FW: spaces (no data)
```

## Recommendations

### For Applications
```python
info = client.get_cpu_info()

# Always check if firmware version is available
if info['firmware_version'] != 'N/A':
    print(f"Firmware: {info['firmware_version']}")
else:
    print("Firmware: See TIA Portal project")

# Hardware version is reliable
print(f"Hardware: {info['hardware_version']}")
```

### For Debugging
Use the debug script to see raw SZL responses:
```bash
python examples/debug/debug_cpu_info.py
```

## Future Enhancements

Potential improvements:
1. Add support for other SZL IDs (0x001C, 0x0F12) where available
2. Implement fallback mechanism to try multiple SZL IDs
3. Parse connection negotiation data for firmware version
4. Add PLC model detection to use appropriate decoding strategy

## References

- Siemens S7 Protocol Documentation
- SZL (System Status List) Specification
- TIA Portal Hardware Configuration
