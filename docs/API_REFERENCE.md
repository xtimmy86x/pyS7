# API Reference

Complete reference for pyS7 data types, address formats, and supported operations.

## Table of Contents
- [Data Types](#data-types)
- [Address Format](#address-format)
- [Memory Areas](#memory-areas)
- [Supported Addresses](#supported-addresses)
- [String Types](#string-types)

## Data Types

### Numeric Types

| Type | Size | Range | Python Type | Description |
|------|------|-------|-------------|-------------|
| **BYTE** | 1 byte | 0 to 255 | `int` | Unsigned 8-bit integer |
| **INT** | 2 bytes | -32,768 to 32,767 | `int` | Signed 16-bit integer |
| **WORD** | 2 bytes | 0 to 65,535 | `int` | Unsigned 16-bit integer |
| **DINT** | 4 bytes | -2,147,483,648 to 2,147,483,647 | `int` | Signed 32-bit integer |
| **DWORD** | 4 bytes | 0 to 4,294,967,295 | `int` | Unsigned 32-bit integer |
| **REAL** | 4 bytes | ±3.4E±38 | `float` | Single precision floating point |
| **LREAL** | 8 bytes | ±1.7E±308 | `float` | Double precision floating point |

### Binary Types

| Type | Size | Values | Python Type | Description |
|------|------|--------|-------------|-------------|
| **BIT** | 1 bit | 0 or 1 | `bool` | Boolean value |

### Character Types

| Type | Size | Range | Python Type | Description |
|------|------|-------|-------------|-------------|
| **CHAR** | 1 byte | ASCII | `str` | Single ASCII character |
| **STRING** | Variable | 0-254 chars | `str` | ASCII string (1 byte/char + 2 byte header) |
| **WSTRING** | Variable | 0-254 chars | `str` | Unicode string (2 bytes/char + 4 byte header) |

## Address Format

pyS7 uses a flexible address format inspired by nodeS7 and nodes7.

### General Format

```
<MemoryArea><DBNumber>,<DataType><Offset>.<BitOffset>
```

### Components

- **MemoryArea**: DB, M (Merker), I/E (Input), Q/A (Output), etc.
- **DBNumber**: For DB areas, the data block number
- **DataType**: X (bit), B (byte), I (int), W (word), R (real), etc.
- **Offset**: Byte offset in the memory area
- **BitOffset**: For bit types, the bit position (0-7)

### Examples

```python
# Data Block addresses
"DB1,X0.0"      # Bit 0 of byte 0 in DB1
"DB1,B10"       # Byte at offset 10 in DB1
"DB1,I20"       # INT at offset 20 in DB1
"DB1,R30"       # REAL at offset 30 in DB1
"DB1,S40.50"    # STRING of length 50 at offset 40 in DB1

# Marker (Merker) memory
"M0.0"          # Bit 0 of marker byte 0
"MW10"          # WORD at marker offset 10

# Input area
"I0.0"          # Bit 0 of input byte 0
"IW2"           # WORD at input offset 2

# Output area
"Q0.0"          # Bit 0 of output byte 0
"QW4"           # WORD at output offset 4
```

## Memory Areas

### Data Blocks (DB)

Access to data blocks requires DB number specification:

```python
from pyS7 import S7Tag, DataType, MemoryArea

# String format
tags = ["DB1,I0", "DB2,R10", "DB5,X20.3"]

# S7Tag format
tag = S7Tag(
    memory_area=MemoryArea.DB,
    db_number=1,
    data_type=DataType.INT,
    start=0,
    bit_offset=0,
    length=1
)
```

### Marker Memory (M)

Global memory shared across PLC program:

```python
tags = [
    "M0.0",     # Bit
    "MB10",     # Byte
    "MW20",     # Word
    "MD30"      # Double word
]
```

### Input Area (I/E)

Physical inputs to the PLC:

```python
tags = [
    "I0.0",     # Input bit (I or E notation)
    "E0.0",     # Same as I0.0
    "IB2",      # Input byte
    "IW4"       # Input word
]
```

### Output Area (Q/A)

Physical outputs from the PLC:

```python
tags = [
    "Q0.0",     # Output bit (Q or A notation)
    "A0.0",     # Same as Q0.0
    "QB2",      # Output byte
    "QW4"       # Output word
]
```

## Supported Addresses

Complete table mapping pyS7 addresses to Step7/TIA Portal equivalents:

| pyS7 Address | Step7/TIA Portal | Data type | Description |
|-------------|------------------|-----------|-------------|
| `DB2,X0.7` | `DB2.DBX0.7` | Boolean | Bit 7 of byte 0 of DB 2 |
| `DB36,B2` | `DB36.DBB2` | Byte | Byte 2 (0-255) of DB 36 |
| `DB102,C4` | `DB102.DBB4` | Char | Byte 4 of DB 102 as a Char |
| `DB10,I3` | `DB10.DBW3` | Int | Signed 16-bit number at byte 3 of DB 10 |
| `DB17,W4` | `DB17.DBW4` | Word | Unsigned 16-bit number at byte 4 of DB 17 |
| `DB103,DI13` | `DB103.DBD13` | DInt | Signed 32-bit number at byte 13 of DB 103 |
| `DB51,DW6` | `DB51.DBD6` | DWord | Unsigned 32-bit number at byte 6 of DB 51 |
| `DB21,R14` | `DB21.DBD14` | Real | Floating point 32-bit number at byte 14 of DB 21 |
| `DB21,LR14` | `DB21.DBD14` | LReal | Floating point 64-bit number at byte 14 of DB 21 |
| `DB102,S10.15` | - | String | String of length 15 starting at byte 10 of DB 102 |
| `DB102,WS50.20` | - | WString | Wide String of length 20 starting at byte 50 of DB 102 |
| `I3.0` or `E3.0` | `I3.0` or `E3.0` | Boolean | Bit 0 of byte 3 of input area |
| `Q2.6` or `A2.6` | `Q2.6` or `A2.6` | Boolean | Bit 6 of byte 2 of output area |
| `M7.1` | `M7.1` | Boolean | Bit 1 of byte 7 of marker area |
| `IB10` or `EB10` | `IB10` or `EB10` | Byte | Byte 10 (0-255) of input area |
| `QB5` or `AB5` | `QB5` or `AB5` | Byte | Byte 5 (0-255) of output area |
| `MB16` | `MB16` | Byte | Byte 16 (0-255) of marker area |
| `IC3` or `EC3` | `IB3` or `EB3` | Char | Byte 3 of input area as a Char |
| `QC14` or `AC14` | `QB14` or `AB14` | Char | Byte 14 of output area as a Char |
| `MC9` | `MB9` | Char | Byte 9 of marker area as a Char |
| `II12` or `EI12` | `IW12` or `EW12` | Int | Signed 16-bit number at byte 12 of input area |
| `QI14` or `AI14` | `QW14` or `AW14` | Int | Signed 16-bit number at byte 14 of output area |
| `MI14` | `MW14` | Int | Signed 16-bit number at byte 14 of marker area |
| `IW24` or `EW24` | `IW24` or `EW24` | Word | Unsigned 16-bit number at byte 24 of input area |
| `QW8` or `AW8` | `QW8` or `AW8` | Word | Unsigned 16-bit number at byte 8 of output area |
| `MW40` | `MW40` | Word | Unsigned 16-bit number at byte 40 of marker area |
| `IDI62` or `EDI62` | `ID62` or `ED62` | DInt | Signed 32-bit number at byte 62 of input area |
| `QDI38` or `ADI38` | `QD38` or `AD38` | DInt | Signed 32-bit number at byte 38 of output area |
| `MDI26` | `MD26` | DInt | Signed 32-bit number at byte 26 of marker area |
| `ID28` or `ED28` | `ID28` or `ED28` | DWord | Unsigned 32-bit number at byte 28 of input area |
| `QD46` or `AD46` | `QD46` or `AD46` | DWord | Unsigned 32-bit number at byte 46 of output area |
| `MD72` | `MD72` | DWord | Unsigned 32-bit number at byte 72 of marker area |
| `IR34` or `ER34` | `IR34` or `ER34` | Real | Floating point 32-bit number at byte 34 of input area |
| `QR36` or `AR36` | `QR36` or `AR36` | Real | Floating point 32-bit number at byte 36 of output area |
| `MR84` | `MR84` | Real | Floating point 32-bit number at byte 84 of marker area |
| `ILR34` or `ELR34` | `ILR34` or `ELR34` | LReal | Floating point 64-bit number at byte 34 of input area |
| `QLR36` or `ALR36` | `QLR36` or `ALR36` | LReal | Floating point 64-bit number at byte 36 of output area |
| `MLR84` | `MLR84` | LReal | Floating point 64-bit number at byte 84 of marker area |

## String Types

### STRING (ASCII)

**Encoding**: ASCII (1 byte per character)  
**Max length**: 254 characters  
**Size**: length + 2 bytes (header)  
**PLC compatibility**: S7-300/400/1200/1500  

**Address format**: `DB<n>,S<offset>.<length>`

**Structure in PLC memory:**
```
Byte 0: Max length (declared)
Byte 1: Current length (actual)
Byte 2-N: Character data
```

**Example:**
```python
# Read ASCII string
tags = ["DB1,S10.20"]  # STRING at byte 10, max 20 chars
values = client.read(tags)
print(values[0])  # "Hello World"

# Write ASCII string
client.write(["DB1,S10.20"], ["New text"])

# Automatic chunking for large strings
tags = ["DB1,S100.254"]  # STRING[254] - automatically chunked if exceeds PDU
values = client.read(tags)  # Complete string returned transparently
```

### WSTRING (Unicode)

**Encoding**: UTF-16 BE (2 bytes per character)  
**Max length**: 254 characters  
**Size**: (length × 2) + 4 bytes (header)  
**PLC compatibility**: S7-1200/1500 (NOT available on S7-300/400)  

**Address format**: `DB<n>,WS<offset>.<length>`

**Structure in PLC memory:**
```
Byte 0-1: Max length (declared, big-endian)
Byte 2-3: Current length (actual, big-endian)
Byte 4-N: UTF-16 character data (big-endian)
```

**Example:**
```python
# Read Unicode string
tags = ["DB1,WS100.30"]  # WSTRING at byte 100, max 30 chars
values = client.read(tags)
print(values[0])  # "Hello 世界! 🌍"

# Write Unicode string  
client.write(["DB1,WS100.30"], ["Café Müller 東京"])

# Automatic chunking for large WSTRING
tags = ["DB1,WS200.254"]  # WSTRING[254] - automatically chunked
values = client.read(tags)  # Complete Unicode string
```

### String Arrays

Read multiple strings at once:

```python
from pyS7 import S7Tag, DataType, MemoryArea

# Multiple individual strings
tags = [
    "DB1,S10.20",   # First string
    "DB1,S32.50",   # Second string
    "DB1,S84.30"    # Third string
]
data = client.read(tags)
# data = ["String1", "String2", "String3"]

# Array of identical strings (not directly supported - use multiple tags)
# In PLC: ARRAY[1..5] OF STRING[20]
tags = [f"DB1,S{10 + i*22}.20" for i in range(5)]  # Each STRING[20] = 22 bytes
data = client.read(tags)
```

### String Limitations

**PDU Size:**
- STRING: max 254 chars = 256 bytes total (2 header + 254 data)
- WSTRING: max 254 chars = 512 bytes total (4 header + 508 data)
- If STRING/WSTRING exceeds PDU, automatic chunking is applied
- See [ADVANCED_USAGE.md](ADVANCED_USAGE.md#automatic-string-chunking) for details

**Character Encoding:**
- STRING: ASCII only (characters 0-127 safe, 128-255 extended ASCII)
- WSTRING: Full Unicode support (UTF-16, all languages, emojis)
- Non-ASCII characters in STRING may display incorrectly

**Writing Strings:**
- If written string is shorter than declared length, rest is null-padded
- If longer than declared length, it will be truncated
- Current length byte is automatically updated

**Example with validation:**
```python
def safe_string_write(client, tag, value, max_length):
    """Write string with length validation."""
    if len(value) > max_length:
        print(f"Warning: Truncating string from {len(value)} to {max_length} chars")
        value = value[:max_length]
    
    client.write([tag], [value])
    
    # Verify
    readback = client.read([tag])[0]
    if readback != value:
        print(f"Warning: Readback mismatch: '{readback}' != '{value}'")

# Usage
safe_string_write(client, "DB1,S10.20", "Hello World", max_length=20)
```
