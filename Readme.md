# pyS7

Forked from original repository: FiloCara/pyS7

pyS7 is a lightweight python library for data communication with Siemens PLCs. It partially implements the Siemens S7 Communication protocol over ISO-on-TCP (RFC1006), allowing for both data reading and data writing.

Niether the software nor the author are affiliated with Siemens in any way. S7-200, S7-300, S7-400, S7-1200 and S7-1500 are trademarks of Siemens AG.

Key Features:

* **Pure Python**: No external dependencies for easy setup and platform compatibility.

* **User-friendly API**, Intuitive and straightforward, offering simplicity and efficiency.

* **Multi-variable reading optimization**: Enhanced support for simultaneous multi-variable reading, by packing together tags occupying adjacent areas of memory.

**Disclaimer**: Safety should always be your first priority when interacting with manufacturing machines. Therefore, when using this code, it is crucial to have a solid understanding of the machines and the tasks at hand. By choosing to use this code, you agree to assume all risks and accept responsibility for any damages or loss, including but not limited to data corruption, machine downtime, or other adverse effects.

Furthermore, please be aware that this code is under development. It is not battle-tested and changes to the API should be expected.

## Install

```console
pip install git+https://github.com/FiloCara/pyS7
```

## Example

### Reading data

```python
from pyS7 import S7Client

if __name__ == "__main__":

    # Create a new 'S7Client' object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = S7Client(address="192.168.5.100", rack=0, slot=1)

    # Establish connection with the PLC
    client.connect()

    # Define area tags to read
    tags = [
        "DB1,X0.0",     # Read BIT 0 (first bit) of DB1
        "DB1,X0.6",     # Read BIT 7 (7th bit) of DB1
        "DB1,I30",      # Read INT at address 30 of DB1
        "M54.4",        # Read BIT 4 (fifth bit) in the merker (memento) area
        "IW22",         # Read WORD at address 22 in input area
        "QR24",         # Read REAL at address 24 in output area
        "DB1,S10.5"     # Read sequence of CHAR of length 5 starting at address 10 of DB1
    ]

    # Read the data from the PLC using the specified tag list
    data = client.read(tags=tags)

    print(data)  # [True, False, 123, True, 10, -2.54943805634653e-12, 'Hello']
```

### Writing data
```python
from pyS7 import S7Client, DataType, S7Tag, MemoryArea

if __name__ == "__main__":

    # Create a new 'S7Client' object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = S7Client(address="192.168.5.100", rack=0, slot=1)

    # Establish connection with the PLC
    client.connect()

    # Define area tags to write
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

    # Defines values to write
    values = [
        False,
        True,
        25000,
        True,
        120,
        1.2345,
        "Hello",
        (3.14, 6.28, 9.42)
    ]

    # Write data to the PLC using tags and values
    client.write(tags=tags, values=tags)

```

Look at the _examples_ folder for more self-explanatory examples. 

## Supported variables

pyS7 uses a naming convention for PLC addresses, which slightly differs from the one used by Siemens Step7 and Tia portal. This convention is inspired by [https://github.com/plcpeople/nodeS7/](https://github.com/plcpeople/nodeS7/) and [https://github.com/st-one-io/nodes7](https://github.com/st-one-io/nodes7). 

Please refer to the following table for getting the correct addresses and the supported types:

| pyS7 Address                  | Step7 Address         | Data type     | Description |
| ----------------------------- | --------------------- | ------------- | ----------- |
| `DB2,X0.7`                    | `DB2.DBX0.7`          | Boolean       | Bit 7 (eighth) of byte 0 of DB 2 |
| `DB36,B2`                     | `DB36.DBB2`           | Number        | Byte 2 (0-255) of DB 36 |
| `DB102,C4`                    | `DB102.DBB4`          | String        | Byte 4 of DB 102 as a Char |
| `DB10,I3`                     | `DB10.DBW3`           | Number        | Signed 16-bit number at byte 3 of DB 10 |
| `DB17,W4`                     | `DB17.DBW4`           | Number        | Unsigned 16-bit number at byte 4 of DB 17 |
| `DB103,DI3`                   | `DB103.DBD13`         | Number        | Signed 32-bit number at byte 3 of DB 103 |
| `DB51,DW6`                    | `DB51.DBD6`           | Number        | Unsigned 32-bit number at byte 6 of DB 51 |
| `DB21,R14`                    | `DB21.DBD14`          | Number        | Floating point 32-bit number at byte 14 of DB 21 |
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


## License

This project is licensed under the terms of the MIT license.
For more information, see the [LICENSE](https://github.com/FiloCara/pyS7/blob/main/LICENSE) file.
