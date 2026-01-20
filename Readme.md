# pyS7

pyS7 is a lightweight, pure Python library that implements the Siemens S7 communication protocol over ISO-on-TCP (RFC1006). It is designed for software developers and integrators who need to read and write data from Siemens S7-200, S7-300, S7-400, S7-1200, and S7-1500 PLCs directly from their applications.

> ⚠️ Neither this project nor its authors are affiliated with Siemens. S7-200, S7-300, S7-400, S7-1200, and S7-1500 are registered trademarks of Siemens AG.

## Table of contents
- [Features](#features)
- [Safety notice](#safety-notice)
- [Installation](#installation)
- [Quick start](#quick-start)
  - [Reading data](#reading-data)
  - [Writing data](#writing-data)
  - [Reading CPU status and information](#reading-cpu-status-and-information)
  - [String data types](#string-data-types)
- [Advanced connection methods](#advanced-connection-methods)
  - [TSAP connection](#tsap-connection)
- [PDU size and performance optimization](#pdu-size-and-performance-optimization)
- [Best practices](#best-practices)
- [Additional examples](#additional-examples)
- [Troubleshooting](#troubleshooting)
- [Supported addresses](#supported-addresses)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Features
- **Pure Python** – no external dependencies, making it easy to install on a wide range of platforms.
- **Intuitive API** – designed to be readable and approachable, with typing support to improve IDE assistance.
- **Optimised multi-variable reads** – automatically groups contiguous tags to reduce the number of requests sent to the PLC.
- **Automatic chunking** – transparently splits large STRING/WSTRING reads that exceed PDU size into multiple smaller requests.
- **CPU diagnostics** – read the PLC's operating status (RUN/STOP) and detailed CPU information (model, firmware version, etc.) using the System Status List (SZL) protocol.
- **Broad S7 family compatibility** – supports the 200/300/400/1200/1500 series of Siemens PLCs.

## Safety notice
Industrial safety must always remain your top priority. By using pyS7 you accept full responsibility for any damage, data loss, downtime, or other unintended effects that might result. Make sure you understand the machine, the process, and the implications of each read/write operation before interacting with a live system.

The project is under active development: the API may evolve and the code has not yet undergone extensive production testing.

## Installation
pyS7 requires Python 3.8 or later.

```console
pip install pys7
```

To install the latest version directly from GitHub:

```console
pip install git+https://github.com/xtimmy86x/pyS7
```

## Quick start

### Reading data

```python
from pyS7 import S7Client

if __name__ == "__main__":

    # Create a client to connect to an S7-300/400/1200/1500 PLC
    client = S7Client(address="192.168.5.100", rack=0, slot=1)

    # Open the connection to the PLC
    client.connect()

    try:
        # Define area tags to read
        tags = [
            "DB1,X0.0",  # Bit 0 of DB1
            "DB1,X0.6",  # Bit 6 of DB1
            "DB1,I30",   # INT at byte 30 of DB1
            "M54.4",     # Bit 4 of the marker memory
            "IW22",      # WORD at byte 22 of the input area
            "QR24",      # REAL at byte 24 of the output area
            "DB1,S10.5"  # String of 5 characters starting at byte 10 of DB1
        ]

        data = client.read(tags=tags)

        print(data)  # [True, False, 123, True, 10, -2.54943805634653e-12, 'Hello']
    finally:
        client.disconnect()

# Or use context manager for automatic cleanup
with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    data = client.read(["DB1,I0", "DB1,I2"])
    print(data)
```

### Writing data
```python
from pyS7 import S7Client, DataType, S7Tag, MemoryArea

if __name__ == "__main__":

    client = S7Client(address="192.168.5.100", rack=0, slot=1)

    client.connect()

    tags = [
        "DB1,X0.0",     # => S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, 0, 1) - BIT 0 (first bit) of DB1
        "DB1,X0.6",     # => S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, 6, 1) - BIT 7 (7th bit) of DB1
        "DB1,I30",      # => S7Tag(MemoryArea.DB, 1, DataType.INT, 30, 0, 1) - INT at address 30 of DB1
        "M54.4",        # => S7Tag(MemoryArea.MERKER, 0, DataType.BIT, 4, 4, 1) - BIT 4 (fifth bit) in the merker (memento) area
        "IW22",         # => S7Tag(MemoryArea.INPUT, 0, DataType.WORD, 22, 0, 1) - WORD at address 22 in input area
        "QR24",         # => S7Tag(MemoryArea.OUTPUT, 0, DataType.REAL, 24, 0, 1) - REAL at address 24 in output area
        "DB1,S10.5",    # => S7Tag(MemoryArea.DB, 1, DataType.CHAR, 10, 0, 5) - Sequence of CHAR (string) of length 5 starting at address 10 of DB1
        S7Tag(memory_area=MemoryArea.DB, db_number=5, data_type=DataType.REAL, start=50, bit_offset=0, length=3) # => Sequence of REAL of length 3 starting at address 50 of DB5 
    ]

    values = [
        False,
        True,
        25000,
        True,
        120,
        1.2345,
        "Hello",
        (3.14, 6.28, 9.42),
    ]

    client.write(tags=tags, values=values)

```

### Reading CPU status and information

Check the current operating status and get detailed information about the PLC CPU:

```python
from pyS7 import S7Client

if __name__ == "__main__":
    client = S7Client(address="192.168.5.100", rack=0, slot=1)
    client.connect()

    # Get CPU status
    status = client.get_cpu_status()
    print(f"CPU Status: {status}")  # "RUN" or "STOP"

    # Get CPU information
    info = client.get_cpu_info()
    print(f"CPU Model: {info['module_type_name']}")
    print(f"Firmware: {info['firmware_version']}")  # May be "N/A" on some PLCs
    print(f"Hardware: {info['hardware_version']}")

    # Use in application logic
    if status == "RUN":
        print("CPU is running - ready for operations")
        data = client.read(["DB1,I0"])
    elif status == "STOP":
        print("CPU is stopped - operations not possible")
    
    client.disconnect()
```

See [CPU_STATUS_READING.md](docs/CPU_STATUS_READING.md) for detailed information about CPU diagnostics.

> **Note:** Some PLCs may return "N/A" for firmware version. This is normal behavior and depends on the PLC model and configuration.

### String data types

pyS7 supports two string types:

#### STRING (ASCII)
- **Encoding**: ASCII (1 byte per character)
- **Max length**: 254 characters
- **Size**: length + 2 bytes (header)
- **Address format**: `DB<n>,S<offset>.<length>`
- **Use for**: English text, simple data

```python
# Read ASCII string
tags = ["DB1,S10.20"]  # STRING at byte 10, max 20 chars
values = client.read(tags)
print(values[0])  # "Hello World"

# Write ASCII string
client.write(["DB1,S10.20"], ["New text"])
```

#### WSTRING (Unicode)
- **Encoding**: UTF-16 BE (2 bytes per character)
- **Max length**: 254 characters
- **Size**: (length × 2) + 2 bytes (header)
- **Address format**: `DB<n>,WS<offset>.<length>`
- **Use for**: International text, emojis, special characters
- **Availability**: S7-1200/1500 (not available on S7-300/400)

```python
# Read Unicode string
tags = ["DB1,WS100.30"]  # WSTRING at byte 100, max 30 chars
values = client.read(tags)
print(values[0])  # "Hello 世界! 🌍"

# Write Unicode string  
client.write(["DB1,WS100.30"], ["Café Müller 東京"])
```

#### Automatic chunking for large strings

When a STRING or WSTRING exceeds the negotiated PDU size, pyS7 automatically splits the read into multiple smaller chunks and reassembles the complete string:

```python
# STRING[254] with PDU 240 - automatically chunked
tags = ["DB1,S100.254"]  # Declared as STRING[254] in PLC
values = client.read(tags)
print(values[0])  # Complete string, transparently chunked

# Works with WSTRING too
tags = ["DB1,WS200.254"]  # WSTRING[254]
values = client.read(tags)
print(values[0])  # Complete Unicode string, automatically chunked
```

**How it works:**
1. pyS7 detects if STRING/WSTRING response would exceed PDU size
2. Reads the 2-byte (STRING) or 4-byte (WSTRING) header to get actual length
3. Splits data into chunks that fit within PDU limits
4. Reassembles chunks and returns complete string
5. All done transparently - you just get the string!

**PDU size considerations:**
- PDU size is negotiated during connection (typically 240-960 bytes)
- Maximum data per chunk = PDU size - 26 bytes (protocol overhead)
- For PDU 240: max chunk = 214 bytes
- STRING[254] = 256 bytes → automatically split into 214 + 42 byte chunks
- WSTRING[254] = 512 bytes → split into 214 + 214 + 84 byte chunks

**Note:** Only STRING and WSTRING support automatic chunking. For other data types (BYTE, WORD, INT, etc.) that exceed PDU size, you must manually split the read into smaller arrays.

## Advanced connection methods

### TSAP connection

In addition to the traditional rack/slot connection method, pyS7 supports direct TSAP (Transport Service Access Point) specification. This is useful for:
- Non-standard PLC configurations
- Third-party S7-compatible devices
- Custom communication setups where rack/slot values don't apply

#### Using TIA Portal TSAP notation

The easiest way to use TSAP is with Siemens TIA Portal notation (e.g., "03.00", "03.01"):

```python
from pyS7 import S7Client

# Connect using TIA Portal TSAP format
client = S7Client(
    address="192.168.5.100",
    local_tsap="03.00",   # PG/PC connection (standard)
    remote_tsap="03.01"   # Rack 0, Slot 1
)

client.connect()
```

Common TIA Portal TSAP values:
- **PG/PC connection**: local `"03.00"`, remote `"03.01"` (Rack 0, Slot 1)
- **OP connection**: local `"22.00"`, remote `"03.01"`
- **HMI connection**: local `"10.00"`, remote `"03.01"`

#### Using hexadecimal TSAP values

You can also use integer hex values directly:

```python
from pyS7 import S7Client

# Connect using hex TSAP values
client = S7Client(
    address="192.168.5.100",
    local_tsap=0x0300,   # Equivalent to "03.00"
    remote_tsap=0x0301   # Equivalent to "03.01"
)

client.connect()
```

#### Converting between formats

```python
from pyS7 import S7Client

# Convert TIA Portal string to integer
local_tsap = S7Client.tsap_from_string("03.00")
print(f"0x{local_tsap:04X}")  # Output: 0x0300

# Convert integer to TIA Portal string
tsap_str = S7Client.tsap_to_string(0x0301)
print(tsap_str)  # Output: "03.01"
```

#### TSAP calculation helper

If you know the rack and slot but want to use TSAP, use the `tsap_from_rack_slot()` helper:

```python
from pyS7 import S7Client

# Calculate remote TSAP from rack and slot
remote_tsap = S7Client.tsap_from_rack_slot(rack=0, slot=1)
remote_tsap_str = S7Client.tsap_to_string(remote_tsap)
print(f"Rack 0, Slot 1 -> {remote_tsap_str}")  # Output: "03.01"

# Use the calculated TSAP
client = S7Client(
    address="192.168.5.100",
    local_tsap="03.00",
    remote_tsap=remote_tsap_str
)

client.connect()
```

#### TSAP formula

The remote TSAP is calculated from rack and slot using:
```
remote_tsap = 0x0100 | (rack × 32 + slot)
```

Examples:
- Rack 0, Slot 1: `0x0101` = `"01.01"`
- Rack 0, Slot 2: `0x0102` = `"01.02"`
- Rack 1, Slot 0: `0x0120` = `"01.32"`
- Rack 1, Slot 1: `0x0121` = `"01.33"`

#### TSAP validation

The library automatically validates TSAP values:
- Both `local_tsap` and `remote_tsap` must be provided together
- Values must be in the range 0x0000 to 0xFFFF (0-65535)
- Values must be integers

```python
# This will raise ValueError: both TSAP values required
client = S7Client(address="192.168.5.100", local_tsap=0x0100)

# This will raise ValueError: TSAP out of range
client = S7Client(address="192.168.5.100", local_tsap=0x10000, remote_tsap=0x0101)
```
## PDU size and performance optimization

### Understanding PDU size

The PDU (Protocol Data Unit) size is the maximum amount of data that can be exchanged in a single request/response. It's negotiated during connection and affects performance:

```python
from pyS7 import S7Client

client = S7Client(
    address="192.168.5.100",
    rack=0,
    slot=1,
    pdu_size=960  # Request PDU 960 (default is 960)
)

client.connect()
print(f"Negotiated PDU: {client.pdu_size} bytes")  # Actual PDU may be lower
```

**Common PDU sizes:**
- **S7-300/400**: Typically 240 bytes (can be configured up to 960)
- **S7-1200/1500**: Usually 480 or 960 bytes
- **Protocol overhead**: ~26 bytes per request (TPKT + COTP + S7 headers)

### Performance tips

1. **Use optimized reads** (enabled by default):
```python
# Automatically groups contiguous tags into fewer requests
data = client.read(tags, optimize=True)  # Default
```

2. **Group related tags in the same DB**:
```python
# Good: Contiguous addresses can be read in one request
tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,I6"]

# Less efficient: Each tag requires separate request
tags = ["DB1,I0", "DB5,I0", "DB10,I0", "DB15,I0"]
```

3. **Read arrays instead of individual values**:
```python
# Efficient: Read 10 INTs in one tag
tags = [S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 10)]

# Less efficient: Read 10 individual INTs
tags = [f"DB1,I{i*2}" for i in range(10)]
```

4. **Consider PDU limits for large data**:
```python
# For BYTE arrays exceeding PDU, split manually
max_bytes = client.pdu_size - 26  # Account for overhead
if data_size > max_bytes:
    # Read in chunks
    chunk1 = client.read([S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, max_bytes)])
    chunk2 = client.read([S7Tag(MemoryArea.DB, 1, DataType.BYTE, max_bytes, 0, remaining)])
```

### Handling PDU size errors

If a tag exceeds the PDU size, pyS7 will raise a clear error:

```python
try:
    # BYTE[300] exceeds PDU 240
    data = client.read([S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 300)])
except S7AddressError as e:
    print(e)
    # "S7Tag(...) requires 326 bytes but PDU size is 240 bytes.
    #  Maximum data size for this PDU: 214 bytes (current tag needs 300 bytes).
    #  For BYTE arrays, read in smaller chunks.
    #  For STRING/WSTRING, automatic chunking is supported."
```

**Solutions:**
1. Increase PDU size if PLC supports it
2. Split reads into smaller chunks
3. For STRING/WSTRING, automatic chunking handles this automatically

## Best practices

### Connection management

```python
# Use context manager for automatic cleanup
with S7Client("192.168.5.100", 0, 1) as client:
    data = client.read(["DB1,I0"])
    # Connection automatically closed on exit

# Or manual connection management
client = S7Client("192.168.5.100", 0, 1)
try:
    client.connect()
    data = client.read(["DB1,I0"])
finally:
    client.disconnect()  # Always disconnect
```

### Error handling

```python
from pyS7 import S7Client, S7CommunicationError, S7AddressError

try:
    client = S7Client("192.168.5.100", 0, 1)
    client.connect()
    
    data = client.read(["DB1,I0"])
    
except S7ConnectionError as e:
    print(f"Connection failed: {e}")
except S7CommunicationError as e:
    print(f"Communication error: {e}")
except S7AddressError as e:
    print(f"Invalid address or tag: {e}")
finally:
    if client.is_connected:
        client.disconnect()
```

### Type safety with S7Tag

```python
from pyS7 import S7Tag, DataType, MemoryArea

# Explicit typing for better IDE support and validation
tag = S7Tag(
    memory_area=MemoryArea.DB,
    db_number=1,
    data_type=DataType.INT,
    start=10,
    bit_offset=0,
    length=5  # Read 5 consecutive INTs
)

data = client.read([tag])
print(data[0])  # Tuple of 5 integers
```
## Additional examples
More demonstration scripts are available in the repository's [`examples/`](examples/) directory.

## Troubleshooting
Having issues? Check the [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for common problems and solutions.

## Supported addresses
pyS7 adopts a PLC addressing convention inspired by [nodeS7](https://github.com/plcpeople/nodeS7) and [nodes7](https://github.com/st-one-io/nodes7). The table below maps common pyS7 addresses to their Step7/TIA Portal equivalents and highlights the associated data types.

| pyS7 Address                  | Step7/TIA Portal Address         | Data type     | Description |
| ----------------------------- | --------------------- | ------------- | ----------- |
| `DB2,X0.7`                    | `DB2.DBX0.7`          | Boolean       | Bit 7 (eighth) of byte 0 of DB 2 |
| `DB36,B2`                     | `DB36.DBB2`           | Number        | Byte 2 (0-255) of DB 36 |
| `DB102,C4`                    | `DB102.DBB4`          | String        | Byte 4 of DB 102 as a Char |
| `DB10,I3`                     | `DB10.DBW3`           | Number        | Signed 16-bit number at byte 3 of DB 10 |
| `DB17,W4`                     | `DB17.DBW4`           | Number        | Unsigned 16-bit number at byte 4 of DB 17 |
| `DB103,DI3`                   | `DB103.DBD13`         | Number        | Signed 32-bit number at byte 3 of DB 103 |
| `DB51,DW6`                    | `DB51.DBD6`           | Number        | Unsigned 32-bit number at byte 6 of DB 51 |
| `DB21,R14`                    | `DB21.DBD14`          | Number        | Floating point 32-bit number at byte 14 of DB 21 |
| `DB21,LR14`                   | `DB21.DBD14`          | Number        | Floating point 64-bit number at byte 14 of DB 21 |
| `DB102,S10.15`                | -                     | String        | String of length 15 starting at byte 10 of DB 102 (ASCII, 1 byte/char) |
| `DB102,WS50.20`               | -                     | String        | Wide String of length 20 starting at byte 50 of DB 102 (UTF-16, 2 bytes/char) |
| `I3.0` or `E3.0`              | `I3.0` or `E3.0`      | Boolean       | Bit 0 of byte 3 of input area |
| `Q2.6` or `A2.6`              | `Q2.6` or `A2.6`      | Boolean       | Bit 6 of byte 2 of output area |
| `M7.1`                        | `M7.1`                | Boolean       | Bit 1 of byte 7 of memory area |
| `IB10` or `EB10`              | `IB10` or `EB10`      | Number        | Byte 10 (0 -255) of input area |
| `QB5` or `AB5`                | `QB5` or `AB5`        | Number        | Byte 5 (0 -255) of output area |
| `MB16`                        | `MB16`                | Number        | Byte 16 (0 -255) of memory area |
| `IC3` or `EC3`                | `IB3` or `EB3`        | String        | Byte 3 of input area as a Char |
| `QC14` or `AC14`              | `QB14` or `AB14`      | String        | Byte 14 of output area as a Char |
| `MC9`                         | `MB9`                 | String        | Byte 9 of memory area as a Char |
| `II12` or `EI12`              | `IW12` or `EW12`      | Number        | Signed 16-bit number at byte 12 of input area |
| `QI14` or `AI14`              | `QW14` or `AW14`      | Number        | Signed 16-bit number at byte 14 of output area |
| `MI14`                        | `MW14`                | Number        | Signed 16-bit number at byte 14 of memory area |
| `IW24` or `EW24`              | `IW24` or `EW24`      | Number        | Unsigned 16-bit number at byte 24 of input area |
| `QW8` or `AW8`                | `QW8` or `AW8`        | Number        | Unsigned 16-bit number at byte 8 of output area |
| `MW40`                        | `MW40`                | Number        | Unsigned 16-bit number at byte 40 of memory area |
| `IDI62` or `EDI62`            | `ID62` or `ED62`      | Number        | Signed 32-bit number at byte 62 of input area |
| `QDI38` or `ADI38`            | `QD38` or `AD38`      | Number        | Signed 32-bit number at byte 38 of output area |
| `MDI26`                       | `MD26`                | Number        | Signed 32-bit number at byte 26 of memory area |
| `ID28` or `ED28`              | `ID28` or `ED28`      | Number        | Unsigned 32-bit number at byte 28 of input area |
| `QD46` or `AD46`              | `QD46` or `AD46`      | Number        | Unsigned 32-bit number at byte 46 of output area |
| `MD72`                        | `MD72`                | Number        | Unsigned 32-bit number at byte 72 of memory area |
| `IR34` or `ER34`              | `IR34` or `ER34`      | Number        | Floating point 32-bit number at byte 34 of input area |
| `QR36` or `AR36`              | `QR36` or `AR36`      | Number        | Floating point 32-bit number at byte 36 of output area |
| `MR84`                        | `MR84`                | Number        | Floating point 32-bit number at byte 84 of memory area |
| `ILR34` or `ELR34`            | `ILR34` or `ELR34`    | Number        | Floating point 64-bit number at byte 34 of input area |
| `QLR36` or `ALR36`            | `QLR36` or `ALR36`    | Number        | Floating point 64-bit number at byte 36 of output area |
| `MLR84`                       | `MLR84`               | Number        | Floating point 64-bit number at byte 84 of memory area |

## License
This project is distributed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Acknowledgements
Special thanks to [filocara](https://github.com/FiloCara) for the original project that inspired this work.
