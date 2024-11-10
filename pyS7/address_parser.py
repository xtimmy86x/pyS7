import re
from typing import Dict, Optional

from .constants import DataType, MemoryArea
from .errors import S7AddressError
from .tag import S7Tag

"""
### Supported variables

| Address                       | Step7 equivalent      | Data type  | Description |
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
"""

DataTypeMap: Dict[str, DataType] = {
    "X": DataType.BIT,
    "B": DataType.BYTE,
    "BYTE": DataType.BYTE,
    "C": DataType.CHAR,
    "CHAR": DataType.CHAR,
    "I": DataType.INT,
    "INT": DataType.INT,
    "W": DataType.WORD,
    "WORD": DataType.WORD,
    "DI": DataType.DINT,
    "DINT": DataType.DINT,
    "D": DataType.DWORD,
    "R": DataType.REAL,
    "REAL": DataType.REAL,
}


def map_address_to_tag(address: str) -> S7Tag:
    address = address.upper()

    match: Optional[re.Match[str]]

    if address.startswith("DB"):
        match = re.match(r"DB(\d+),([a-zA-Z]+)(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise S7AddressError(f"Impossible to parse address '{address}'")

        db_number, str_data_type, start, bit_offset = match.groups()

        if str_data_type == "X":
            db_number = int(db_number)
            data_type = DataType.BIT
            start = int(start)

            if bit_offset is None:
                raise S7AddressError("Missing bit_offset value")

            bit_offset = int(bit_offset)
            if not 0 <= bit_offset <= 7:
                raise S7AddressError(
                    "The bit offset must be a value between 0 and 7 included"
                )

            length = 1

        elif str_data_type == "B" or str_data_type == "BYTE":
            db_number = int(db_number)
            data_type = DataType.BYTE
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise S7AddressError(
                    f"Bit offset non supported for address '{address}'"
                )

            bit_offset = 0

        elif str_data_type == "C" or str_data_type == "CHAR":
            db_number = int(db_number)
            data_type = DataType.CHAR
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise S7AddressError(
                    f"Bit offset non supported for address '{address}'"
                )

            bit_offset = 0

        elif str_data_type == "I" or str_data_type == "INT":
            db_number = int(db_number)
            data_type = DataType.INT
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise S7AddressError(
                    f"Bit offset non supported for address '{address}'"
                )

            bit_offset = 0

        elif str_data_type == "W" or str_data_type == "WORD":
            db_number = int(db_number)
            data_type = DataType.WORD
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise S7AddressError(
                    f"Bit offset non supported for address '{address}'"
                )

            bit_offset = 0

        elif str_data_type == "DI" or str_data_type == "DINT":
            db_number = int(db_number)
            data_type = DataType.DINT
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise S7AddressError(
                    f"Bit offset non supported for address '{address}'"
                )

            bit_offset = 0

        elif str_data_type == "DW" or str_data_type == "DWORD":
            db_number = int(db_number)
            data_type = DataType.DWORD
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise S7AddressError(
                    f"Bit offset non supported for address '{address}'"
                )

            bit_offset = 0

        elif str_data_type == "R" or str_data_type == "REAL":
            db_number = int(db_number)
            data_type = DataType.REAL
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise S7AddressError(
                    f"Bit offset non supported for address '{address}'"
                )

            bit_offset = 0

        elif str_data_type == "S":
            db_number = int(db_number)
            data_type = DataType.CHAR
            start = int(start)

            # For String addresses the bit offset corresponds to the length
            if bit_offset is None:
                raise S7AddressError(f"{address}")

            length = int(bit_offset)
            bit_offset = 0

        else:
            raise S7AddressError(f"Impossible to parse address: '{address}")

        return S7Tag(
            memory_area=MemoryArea.DB,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length,
        )

    elif address.startswith("I") or address.startswith("E"):
        match = re.match(r"^[I,E]([B,C,I,W,DI,D,R])?(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise S7AddressError(f"{address}")

        str_data_type, start, bit_offset = match.groups()

        if str_data_type is None and bit_offset is None:
            raise S7AddressError(f"{address}")

        memory_area = MemoryArea.INPUT
        db_number = 0
        data_type = (
            DataTypeMap[str_data_type] if str_data_type is not None else DataType.BIT
        )
        start = int(start)
        bit_offset = int(bit_offset) if bit_offset is not None else 0

        if not 0 <= bit_offset <= 7:
            raise S7AddressError(
                "The bit offset must be a value between 0 and 7 included"
            )

        length = 1

        return S7Tag(
            memory_area=memory_area,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length,
        )

    elif address.startswith("Q") or address.startswith("A"):
        match = re.match(r"[Q,A]([B,C,I,W,DI,D,R])?(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise S7AddressError(f"{address}")

        str_data_type, start, bit_offset = match.groups()

        if str_data_type is None and bit_offset is None:
            raise S7AddressError(f"{address}")

        memory_area = MemoryArea.OUTPUT
        db_number = 0
        data_type = (
            DataTypeMap[str_data_type] if str_data_type is not None else DataType.BIT
        )
        start = int(start)
        bit_offset = int(bit_offset) if bit_offset is not None else 0

        if not 0 <= bit_offset <= 7:
            raise S7AddressError(
                "The bit offset must be a value between 0 and 7 included"
            )

        length = 1

        return S7Tag(
            memory_area=memory_area,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length,
        )

    elif address.startswith("M"):
        match = re.match(r"M([B,C,I,W,DI,D,R])?(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise S7AddressError(f"{address}")

        str_data_type, start, bit_offset = match.groups()

        if str_data_type is None and bit_offset is None:
            raise S7AddressError(f"{address}")

        memory_area = MemoryArea.MERKER
        db_number = 0
        data_type = (
            DataTypeMap[str_data_type] if str_data_type is not None else DataType.BIT
        )
        start = int(start)
        bit_offset = int(bit_offset) if bit_offset is not None else 0

        if not 0 <= bit_offset <= 7:
            raise S7AddressError(
                "The bit offset must be a value between 0 and 7 included"
            )

        length = 1

        return S7Tag(
            memory_area=memory_area,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length,
        )

    else:
        raise S7AddressError(f"Unsupported address '{address}'")
