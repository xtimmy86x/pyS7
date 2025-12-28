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
- [Additional examples](#additional-examples)
- [Supported addresses](#supported-addresses)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Features
- **Pure Python** – no external dependencies, making it easy to install on a wide range of platforms.
- **Intuitive API** – designed to be readable and approachable, with typing support to improve IDE assistance.
- **Optimised multi-variable reads** – automatically groups contiguous tags to reduce the number of requests sent to the PLC.
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

    # Define area tags to read
    tags = [
        "DB1,X0.0",  # Bit 0 of DB1
        "DB1,X0.6",  # Bit 7 of DB1
        "DB1,I30",   # INT at byte 30 of DB1
        "M54.4",     # Bit 5 of the marker memory
        "IW22",      # WORD at byte 22 of the input area
        "QR24",      # REAL at byte 24 of the output area
        "DB1,S10.5"  # String of 5 characters starting at byte 10 of DB1
    ]

    data = client.read(tags=tags)

    print(data)  # [True, False, 123, True, 10, -2.54943805634653e-12, 'Hello']
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

## Additional examples
More demonstration scripts are available in the repository's [`examples/`](examples/) directory.

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
| `DB102,S10.15`                | -                     | String        | String of length 15 starting at byte 10 of DB 102 |
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
