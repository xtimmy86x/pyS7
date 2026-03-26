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
| **SINT** | 1 byte | -128 to 127 | `int` | Signed 8-bit integer |
| **USINT** | 1 byte | 0 to 255 | `int` | Unsigned 8-bit integer (same as BYTE) |
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
| `DB10,SINT5` | `DB10.DBB5` | SInt | Signed byte 5 (-128 to 127) of DB 10 |
| `DB10,USINT6` | `DB10.DBB6` | USInt | Unsigned byte 6 (0-255) of DB 10 |
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
## Advanced Methods

### read_detailed()

Read multiple tags with per-tag error handling. Unlike `read()` which fails fast on the first error, `read_detailed()` continues processing all tags and returns detailed results for each one.

**Signature:**
```python
def read_detailed(
    tags: Sequence[Union[str, S7Tag]], 
    optimize: bool = True
) -> List[ReadResult]
```

**Parameters:**
- `tags`: List of tag addresses (strings) or S7Tag objects
- `optimize`: Whether to optimize by grouping contiguous tags (default: True)

**Returns:**
- List of `ReadResult` objects, one per tag in the same order

**ReadResult fields:**
- `tag`: The S7Tag object
- `success`: bool indicating if read succeeded
- `value`: The read value (if success=True) or None
- `error`: Error message (if success=False) or None
- `error_code`: S7 error code (if available) or None

**Example:**
```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    # Some tags may fail (e.g., DB99 doesn't exist)
    tags = ["DB1,I0", "DB99,I0", "DB1,R4", "DB1,X8.0"]
    results = client.read_detailed(tags)
    
    for result in results:
        if result.success:
            print(f"✓ {result.tag}: {result.value}")
        else:
            print(f"✗ {result.tag}: {result.error}")
            if result.error_code:
                print(f"  Error code: 0x{result.error_code:02X}")
    
    # Collect only successful values
    successful_data = {
        str(r.tag): r.value 
        for r in results 
        if r.success
    }
    
    # Retry only failed reads
    failed_tags = [str(r.tag) for r in results if not r.success]
    if failed_tags:
        retry_results = client.read_detailed(failed_tags)
```

**Use cases:**
- Batch operations where partial success is acceptable
- Diagnostic/monitoring with some inaccessible areas
- Discovering which data blocks are accessible
- Error categorization and reporting
- Implementing retry logic for failed reads only

**See also:** [examples/read_detailed_demo.py](../examples/read_detailed_demo.py)

### write_detailed()

Write multiple tags with per-tag error handling. Unlike `write()` which fails fast, `write_detailed()` attempts all writes and returns detailed results for each one.

**Signature:**
```python
def write_detailed(
    tags: Sequence[Union[str, S7Tag]], 
    values: Sequence[Value]
) -> List[WriteResult]
```

**Parameters:**
- `tags`: List of tag addresses (strings) or S7Tag objects
- `values`: List of values to write (must match length of tags)

**Returns:**
- List of `WriteResult` objects, one per tag in the same order

**WriteResult fields:**
- `tag`: The S7Tag object
- `success`: bool indicating if write succeeded
- `error`: Error message (if success=False) or None
- `error_code`: S7 error code (if available) or None

**Example:**
```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    tags = ["DB1,I0", "DB1,R4", "DB99,I0", "DB1,X8.0"]
    values = [100, 3.14, 200, True]
    
    results = client.write_detailed(tags, values)
    
    success_count = 0
    for i, result in enumerate(results):
        if result.success:
            print(f"✓ {tags[i]}: Written successfully")
            success_count += 1
        else:
            print(f"✗ {tags[i]}: {result.error}")
    
    print(f"\nSuccess rate: {success_count}/{len(results)}")
    
    # Retry only failed writes
    failed_indices = [i for i, r in enumerate(results) if not r.success]
    if failed_indices:
        retry_tags = [tags[i] for i in failed_indices]
        retry_values = [values[i] for i in failed_indices]
        retry_results = client.write_detailed(retry_tags, retry_values)
```

**Use cases:**
- Batch writes where partial success is acceptable
- Implementing retry logic for failed writes only
- Detailed error reporting in production systems
- Writing to multiple PLCs/areas with varying accessibility

**See also:** [examples/write_detailed_demo.py](../examples/write_detailed_demo.py)

### batch_write()

Transactional batch write with automatic rollback on failure. Reads original values before writing, then verifies the write. If verification fails, automatically restores original values.

**Signature:**
```python
@contextmanager
def batch_write(
    auto_commit: bool = True,
    rollback_on_error: bool = True
) -> BatchWriteTransaction
```

**Parameters:**
- `auto_commit`: If True, automatically commit on context exit (default: True)
- `rollback_on_error`: If True, rollback on commit failure (default: True)

**Returns:**
- `BatchWriteTransaction` object (context manager)

**BatchWriteTransaction methods:**
- `add(tag, value)`: Add a tag/value pair to the batch
- `commit()`: Execute the write and verify
- `rollback()`: Restore original values (if commit failed)

**Example:**
```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    # Auto-commit mode (recommended)
    with client.batch_write() as batch:
        batch.add("DB1,I0", 100)
        batch.add("DB1,I2", 200)
        batch.add("DB1,R4", 3.14)
        # Automatically commits on exit
        # Rolls back on any error
    
    # Manual mode (explicit control)
    batch = client.batch_write(auto_commit=False)
    batch.add("DB1,I0", 100)
    batch.add("DB1,I2", 200)
    
    try:
        batch.commit()  # Write and verify
        print("Batch write successful")
    except Exception as e:
        print(f"Batch write failed: {e}")
        batch.rollback()  # Restore original values
        print("Rolled back to original values")
    
    # Method chaining
    batch = client.batch_write(auto_commit=False)
    (batch
        .add("DB1,I0", 100)
        .add("DB1,I2", 200)
        .add("DB1,R4", 3.14))
    
    batch.commit()
```

**Behavior:**
1. `add()`: Stores tag/value pairs (no PLC communication)
2. `commit()`: 
   - Reads original values from PLC
   - Writes new values to PLC
   - Reads back to verify
   - If verification fails and `rollback_on_error=True`, writes original values
3. `rollback()`: Explicitly restore original values (only after commit)

**Use cases:**
- Critical writes that must succeed or revert
- Multi-tag updates that must be atomic
- Production systems requiring data consistency
- Testing/debugging with automatic cleanup

**Limitations:**
- Cannot rollback after context exit
- Empty batch raises ValueError on commit
- Original values captured at commit time (not add time)

**See also:** [examples/batch_write_demo.py](../examples/batch_write_demo.py)

## ClientMetrics

Performance monitoring and diagnostics for S7 client operations.

### Overview

`ClientMetrics` is a lightweight telemetry system that tracks connection status, operation counts, performance metrics, and errors. It's enabled by default and adds minimal overhead.

**Import:**
```python
from pyS7 import S7Client, ClientMetrics
```

**Enable/Disable:**
```python
# Enabled by default
client = S7Client("192.168.1.10", 0, 1)
assert client.metrics is not None

# Explicitly enable
client = S7Client("192.168.1.10", 0, 1, enable_metrics=True)

# Disable for maximum performance
client = S7Client("192.168.1.10", 0, 1, enable_metrics=False)
assert client.metrics is None
```

### Properties

All properties are read-only and thread-safe.

#### Connection Metrics

| Property | Type | Description |
|----------|------|-------------|
| `connected` | `bool` | Current connection status |
| `connection_start_time` | `Optional[float]` | Timestamp when connected (None if disconnected) |
| `connection_count` | `int` | Total successful connections |
| `disconnection_count` | `int` | Total disconnections |
| `connection_uptime` | `float` | Seconds since connection (0 if disconnected) |

**Example:**
```python
print(f"Connected: {client.metrics.connected}")
print(f"Uptime: {client.metrics.connection_uptime:.1f}s")
print(f"Reconnections: {client.metrics.connection_count - 1}")
```

#### Operation Metrics

| Property | Type | Description |
|----------|------|-------------|
| `read_count` | `int` | Total read operations attempted |
| `write_count` | `int` | Total write operations attempted |
| `total_operations` | `int` | Sum of read + write operations |
| `read_errors` | `int` | Failed read operations |
| `write_errors` | `int` | Failed write operations |
| `timeout_errors` | `int` | Operations that timed out |
| `total_errors` | `int` | Sum of all errors |

**Example:**
```python
print(f"Total operations: {client.metrics.total_operations}")
print(f"Reads: {client.metrics.read_count} ({client.metrics.read_errors} errors)")
print(f"Writes: {client.metrics.write_count} ({client.metrics.write_errors} errors)")
```

#### Performance Metrics

| Property | Type | Description |
|----------|------|-------------|
| `last_read_duration` | `float` | Duration of last read (seconds) |
| `last_write_duration` | `float` | Duration of last write (seconds) |
| `avg_read_duration` | `float` | Average read duration (seconds) |
| `avg_write_duration` | `float` | Average write duration (seconds) |
| `operations_per_minute` | `float` | Operations/minute since connection |

**Example:**
```python
print(f"Last read: {client.metrics.last_read_duration*1000:.1f}ms")
print(f"Avg read: {client.metrics.avg_read_duration*1000:.1f}ms")
print(f"Avg write: {client.metrics.avg_write_duration*1000:.1f}ms")
print(f"Throughput: {client.metrics.operations_per_minute:.1f} ops/min")
```

#### Data Transfer Metrics

| Property | Type | Description |
|----------|------|-------------|
| `total_bytes_read` | `int` | Total bytes read from PLC |
| `total_bytes_written` | `int` | Total bytes written to PLC |
| `total_read_duration` | `float` | Cumulative read time (seconds) |
| `total_write_duration` | `float` | Cumulative write time (seconds) |
| `avg_bytes_per_read` | `float` | Average bytes per read operation |
| `avg_bytes_per_write` | `float` | Average bytes per write operation |

**Example:**
```python
total_kb = (client.metrics.total_bytes_read + client.metrics.total_bytes_written) / 1024
print(f"Total data: {total_kb:.1f} KB")
print(f"Avg read size: {client.metrics.avg_bytes_per_read:.0f} bytes")
print(f"Avg write size: {client.metrics.avg_bytes_per_write:.0f} bytes")
```

#### Quality Metrics

| Property | Type | Description |
|----------|------|-------------|
| `error_rate` | `float` | Percentage of failed operations (0-100) |
| `success_rate` | `float` | Percentage of successful operations (0-100) |

**Example:**
```python
if client.metrics.error_rate > 5.0:
    print(f"⚠️ High error rate: {client.metrics.error_rate:.1f}%")
else:
    print(f"✅ Healthy: {client.metrics.success_rate:.1f}% success")
```

### Methods

#### as_dict()

Export all metrics as a dictionary.

**Signature:**
```python
def as_dict(self) -> Dict[str, Any]
```

**Returns:** Dictionary containing all metric values and computed properties.

**Example:**
```python
import json

metrics_dict = client.metrics.as_dict()
print(json.dumps(metrics_dict, indent=2))

# Output:
# {
#   "connected": true,
#   "connection_start_time": 1709467200.123,
#   "connection_count": 1,
#   "disconnection_count": 0,
#   "connection_uptime": 45.6,
#   "read_count": 100,
#   "write_count": 50,
#   ...
# }
```

**Use cases:**
- Logging to files or databases
- Integration with monitoring systems
- JSON/REST API export
- Debugging and analysis

#### reset()

Reset all metrics to initial state.

**Signature:**
```python
def reset(self) -> None
```

**Example:**
```python
# Perform operations
client.read(["DB1,I0"])
print(f"Operations: {client.metrics.total_operations}")  # 1

# Reset metrics
client.metrics.reset()
print(f"Operations: {client.metrics.total_operations}")  # 0
print(f"Connected: {client.metrics.connected}")  # False
```

**Use cases:**
- Fresh metrics after maintenance
- Periodic metric collection
- Testing and benchmarking
- Error recovery

**Note:** Resets connection state (sets `connected=False`). May want to call `record_connection()` after if still connected.

#### \_\_str\_\_()

Get human-readable metrics summary.

**Example:**
```python
print(client.metrics)

# Output:
# === S7Client Metrics ===
# Connected: True (uptime: 45.6s)
# Operations: 150 (100 reads, 50 writes)
# Success rate: 98.67%
# Avg read: 12.3ms | Avg write: 15.7ms
# Errors: 2 total (1 read, 1 write, 0 timeouts)
# Data: 1234 bytes read, 567 bytes written
```

**Use cases:**
- Quick console output
- Logging
- Debug printing

### Thread Safety

All `ClientMetrics` operations are thread-safe:

```python
import threading

def worker():
    for _ in range(100):
        client.read(["DB1,I0"])

def monitor():
    while True:
        print(f"Ops: {client.metrics.total_operations}")
        time.sleep(1)

# Safe concurrent access
threading.Thread(target=worker).start()
threading.Thread(target=monitor).start()
```

Internal `threading.Lock` ensures:
- ✅ No data races
- ✅ Consistent snapshots in `as_dict()`
- ✅ Safe concurrent reads/writes

### Integration Examples

#### Home Assistant

```python
from homeassistant.components.sensor import SensorEntity

class PLCUptimeSensor(SensorEntity):
    @property
    def state(self):
        return self.client.metrics.connection_uptime
    
    @property
    def unit_of_measurement(self):
        return "s"
```

#### Prometheus

```python
from prometheus_client import Gauge

plc_uptime = Gauge('plc_uptime_seconds', 'PLC connection uptime')
plc_success_rate = Gauge('plc_success_rate', 'PLC operation success rate')

# Update periodically
plc_uptime.set(client.metrics.connection_uptime)
plc_success_rate.set(client.metrics.success_rate)
```

#### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Periodic logging
logger.info(
    "PLC metrics - Ops: %d, Success: %.1f%%, Avg: %.1fms",
    client.metrics.total_operations,
    client.metrics.success_rate,
    client.metrics.avg_read_duration * 1000
)
```

### Performance Impact

Metrics collection has minimal performance impact:

- **Memory:** ~1KB per client
- **CPU:** Nanoseconds per operation (lock + arithmetic)
- **Overhead:** < 0.1% in typical usage

For absolute maximum performance, disable metrics:

```python
client = S7Client("192.168.1.10", 0, 1, enable_metrics=False)
```

### See Also

- **[Metrics Guide](METRICS.md)** - Complete metrics documentation
- **[Examples](../examples/metrics_demo.py)** - Usage examples
- **[Home Assistant Integration](../examples/homeassistant_metrics_integration.py)** - HA patterns

## AsyncS7Client

Asyncio-based S7 PLC client. Drop-in async replacement for `S7Client` — all I/O methods are coroutines, request-building and response-parsing reuse the synchronous helpers (pure computation, no blocking I/O).

### Overview

**Import:**
```python
from pyS7 import AsyncS7Client, AsyncBatchWriteTransaction
```

**Constructor:**
```python
AsyncS7Client(
    address: str,
    rack: int = 0,
    slot: int = 0,
    connection_type: ConnectionType = ConnectionType.S7Basic,
    port: int = 102,
    timeout: float = 5.0,
    local_tsap: Optional[Union[int, str]] = None,
    remote_tsap: Optional[Union[int, str]] = None,
    max_pdu: int = 960,
    enable_metrics: bool = True,
)
```

All constructor parameters match `S7Client`. The client supports both rack/slot and TSAP-based connections.

### Context Manager

```python
async with AsyncS7Client('192.168.0.1', 0, 1) as client:
    values = await client.read(['DB1,I0', 'DB1,R4'])
```

Automatically calls `connect()` on entry and `disconnect()` on exit.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `connection_state` | `ConnectionState` | Current connection state |
| `last_error` | `Optional[str]` | Last error message (None if no error) |
| `is_connected` | `bool` | True if connected |
| `pdu_size` | `int` | Negotiated PDU size |
| `metrics` | `Optional[ClientMetrics]` | Metrics instance (None if disabled) |

### Methods

#### connect()

```python
async def connect() -> None
```

Establish an async TCP connection to the PLC and negotiate COTP/PDU parameters. Raises `S7ConnectionError` or `S7TimeoutError` on failure.

#### disconnect()

```python
async def disconnect() -> None
```

Close the async TCP connection.

#### read()

```python
async def read(
    tags: Sequence[Union[str, S7Tag]],
    optimize: bool = True
) -> List[Value]
```

Read tags from the PLC. Identical API to `S7Client.read()`.

```python
values = await client.read(['DB1,X0.0', 'DB1,I2', 'DB1,R4'])
```

#### read_detailed()

```python
async def read_detailed(
    tags: Sequence[Union[str, S7Tag]],
    optimize: bool = True
) -> List[ReadResult]
```

Read tags with per-tag success/error details. Does not raise on individual tag failures.

```python
results = await client.read_detailed(['DB1,I0', 'DB99,I0', 'DB1,R4'])
for r in results:
    if r.success:
        print(f"{r.tag}: {r.value}")
    else:
        print(f"{r.tag} failed: {r.error}")
```

#### write()

```python
async def write(
    tags: Sequence[Union[str, S7Tag]],
    values: Sequence[Value]
) -> None
```

Write values to PLC tags. Identical API to `S7Client.write()`.

```python
await client.write(['DB1,I0', 'DB1,R4'], [42, 3.14])
```

#### write_detailed()

```python
async def write_detailed(
    tags: Sequence[Union[str, S7Tag]],
    values: Sequence[Value]
) -> List[WriteResult]
```

Write values with per-tag success/error details.

```python
results = await client.write_detailed(['DB1,I0', 'DB1,I2'], [100, 200])
for r in results:
    print(f"{r.tag}: {'OK' if r.success else r.error}")
```

#### get_cpu_status()

```python
async def get_cpu_status() -> str
```

Returns `"RUN"` or `"STOP"`.

```python
status = await client.get_cpu_status()
```

#### get_cpu_info()

```python
async def get_cpu_info() -> Dict[str, Any]
```

Returns dict with `module_type_name`, `hardware_version`, `firmware_version`, `index`, `modules`.

```python
info = await client.get_cpu_info()
print(info['module_type_name'])
```

#### batch_write()

```python
def batch_write(
    auto_commit: bool = True,
    rollback_on_error: bool = True
) -> AsyncBatchWriteTransaction
```

Create an async batch write transaction. See [AsyncBatchWriteTransaction](#asyncbatchwritetransaction).

### AsyncBatchWriteTransaction

Async context manager for atomic multi-tag writes with automatic rollback.

**Methods:**
- `add(tag, value)` → returns self for chaining
- `await commit()` → execute all writes, returns `List[WriteResult]`
- `await rollback()` → restore original values

**Example:**
```python
async with client.batch_write() as batch:
    batch.add('DB1,I0', 100)
    batch.add('DB1,I2', 200)
    batch.add('DB1,R4', 3.14)
    # Auto-commits on exit, rolls back on error

# Manual control
batch = client.batch_write(auto_commit=False)
batch.add('DB1,I0', 100).add('DB1,I2', 200)

try:
    results = await batch.commit()
except Exception:
    await batch.rollback()
```

### Concurrency

`AsyncS7Client` uses an internal `asyncio.Lock` to serialise all send/receive cycles. Multiple coroutines can safely share a single client instance:

```python
async def read_loop(client: AsyncS7Client, tag: str):
    while True:
        value = await client.read([tag])
        print(f"{tag} = {value[0]}")
        await asyncio.sleep(1)

async def main():
    async with AsyncS7Client('192.168.0.1', 0, 1) as client:
        await asyncio.gather(
            read_loop(client, 'DB1,I0'),
            read_loop(client, 'DB1,R4'),
        )
```

### Static Helpers

Delegated from `S7Client`:
- `AsyncS7Client.tsap_from_string(s)` – Convert TIA Portal TSAP string to int
- `AsyncS7Client.tsap_to_string(v)` – Convert int to TIA Portal TSAP string
- `AsyncS7Client.tsap_from_rack_slot(rack, slot)` – Calculate TSAP from rack/slot

### See Also

- **[Advanced Usage: Async Client](ADVANCED_USAGE.md#async-client)** - Patterns and use cases
- **[Example](../examples/async_client_demo.py)** - Complete async example
