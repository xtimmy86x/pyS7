import re

from .constants import MemoryArea, DataType
from .errors import AddressError
from .item import Item

"""
### Variable addressing

The variables and their addresses configured on the **S7 Endpoint** follow a slightly different scheme than used on Step 7 or TIA Portal. Here are some examples that may guide you on addressing your variables:

| Address                       | Step7 equivalent      | JS Data type  | Description |
| ----------------------------- | --------------------- | ------------- | ----------- |
| `DB5,X0.1`                    | `DB5.DBX0.1`          | Boolean       | Bit 1 of byte 0 of DB 5 |
| `DB23,B1` or `DB23,BYTE1`     | `DB23.DBB1`           | Number        | Byte 1 (0-255) of DB 23 |
| `DB100,C2` or `DB100,CHAR2`   | `DB100.DBB2`          | String        | Byte 2 of DB 100 as a Char |
| `DB42,I3` or `DB42,INT3`      | `DB42.DBW3`           | Number        | Signed 16-bit number at byte 3 of DB 42 |
| `DB57,WORD4`                  | `DB57.DBW4`           | Number        | Unsigned 16-bit number at byte 4 of DB 57 |
| `DB13,DI5` or `DB13,DINT5`    | `DB13.DBD5`           | Number        | Signed 32-bit number at byte 5 of DB 13 |
| `DB19,DW6` or `DB19,DWORD6`   | `DB19.DBD6`           | Number        | Unsigned 32-bit number at byte 6 of DB 19 |
| `DB21,R7` or `DB21,REAL7`     | `DB21.DBD7`           | Number        | Floating point 32-bit number at byte 7 of DB 21 |
| `DB2,S7.10`                   | -                     | String        | String of length 10 starting at byte 7 of DB 2 |
| `I1.0` or `E1.0`              | `I1.0` or `E1.0`      | Boolean       | Bit 0 of byte 1 of input area |
| `Q2.1` or `A2.1`              | `Q2.1` or `A2.1`      | Boolean       | Bit 1 of byte 2 of output area |
| `M3.2`                        | `M3.2`                | Boolean       | Bit 2 of byte 3 of memory area |
| `IB4` or `EB4`                | `IB4` or `EB4`        | Number        | Byte 4 (0 -255) of input area |
| `QB5` or `AB5`                | `QB5` or `AB5`        | Number        | Byte 5 (0 -255) of output area |
| `MB6`                         | `MB6`                 | Number        | Byte 6 (0 -255) of memory area |
| `IC7` or `EC7`                | `IB7` or `EB7`        | String        | Byte 7 of input area as a Char |
| `QC8` or `AC8`                | `QB8` or `AB8`        | String        | Byte 8 of output area as a Char |
| `MC9`                         | `MB9`                 | String        | Byte 9 of memory area as a Char |
| `II10` or `EI10`              | `IW10` or `EW10`      | Number        | Signed 16-bit number at byte 10 of input area |
| `QI12` or `AI12`              | `QW12` or `AW12`      | Number        | Signed 16-bit number at byte 12 of output area |
| `MI14`                        | `MW14`                | Number        | Signed 16-bit number at byte 14 of memory area |
| `IW16` or `EW16`              | `IW16` or `EW16`      | Number        | Unsigned 16-bit number at byte 16 of input area |
| `QW18` or `AW18`              | `QW18` or `AW18`      | Number        | Unsigned 16-bit number at byte 18 of output area |
| `MW20`                        | `MW20`                | Number        | Unsigned 16-bit number at byte 20 of memory area |
| `IDI22` or `EDI22`            | `ID22` or `ED22`      | Number        | Signed 32-bit number at byte 22 of input area |
| `QDI24` or `ADI24`            | `QD24` or `AD24`      | Number        | Signed 32-bit number at byte 24 of output area |
| `MDI26`                       | `MD26`                | Number        | Signed 32-bit number at byte 26 of memory area |
| `ID28` or `ED28`              | `ID28` or `ED28`      | Number        | Unsigned 32-bit number at byte 28 of input area |
| `QD30` or `AD30`              | `QD30` or `AD30`      | Number        | Unsigned 32-bit number at byte 30 of output area |
| `MD32`                        | `MD32`                | Number        | Unsigned 32-bit number at byte 32 of memory area |
| `IR34` or `ER34`              | `IR34` or `ER34`      | Number        | Floating point 32-bit number at byte 34 of input area |
| `QR36` or `AR36`              | `QR36` or `AR36`      | Number        | Floating point 32-bit number at byte 36 of output area |
| `MR38`                        | `MR38`                | Number        | Floating point 32-bit number at byte 38 of memory area |


TODO: Not yet immplemented
| `DB1,DT0`                     | -                     | Date**        | A timestamp in the DATE_AND_TIME format |
| `DB1,DTZ10`                   | -                     | Date**        | A timestamp in the DATE_AND_TIME format, in UTC |
| `DB2,DTL2`                    | -                     | Date**        | A timestamp in the DTL format |
| `DB2,DTLZ12`                  | -                     | Date**        | A timestamp in the DTL format, in UTC |
| `DB57,RWORD4`                 | `DB57.DBW4`           | Number        | Unsigned 16-bit number at byte 4 of DB 57, interpreted as Little-Endian |
| `DB13,RDI5` or `DB13,RDINT5`  | `DB13.DBD5`           | Number        | Signed 32-bit number at byte 5 of DB 13, interpreted as Little-Endian |
| `MRW20`                       | `MW20`                | Number        | Unsigned 16-bit number at byte 20 of memory area, interpreted as Little-Endian |
"""

DataTypeMap: dict[str, DataType] = {
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

def map_address_to_item(address: str) -> Item:
    address = address.upper()

    match: re.Match[str] | None

    if address.startswith("DB"):

        match = re.match(r"DB(\d+),([a-zA-Z]+)(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise AddressError(f"Impossible to parse address '{address}'")

        db_number, str_data_type, start, bit_offset = match.groups()

        if str_data_type == "X":
            db_number = int(db_number)
            data_type = DataType.BIT
            start = int(start)
            
            if bit_offset is None:
                raise AddressError(
                    f"Missing bit_offset value")
            
            bit_offset = int(bit_offset)
            if not 0 <= bit_offset <= 7:
                raise AddressError(
                    f"The bit offset must be a value between 0 and 7 included")
            
            length = 1

        elif str_data_type == "B" or str_data_type == "BYTE":
            db_number = int(db_number)
            data_type = DataType.BYTE
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise AddressError(
                    f"Bit offset non supported for address '{address}'")

            bit_offset = 0

        elif str_data_type == "C" or str_data_type == "CHAR":
            db_number = int(db_number)
            data_type = DataType.CHAR
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise AddressError(
                    f"Bit offset non supported for address '{address}'")

            bit_offset = 0

        elif str_data_type == "I" or str_data_type == "INT":
            db_number = int(db_number)
            data_type = DataType.INT
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise AddressError(
                    f"Bit offset non supported for address '{address}'")

            bit_offset = 0

        elif str_data_type == "W" or str_data_type == "WORD":
            db_number = int(db_number)
            data_type = DataType.WORD
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise AddressError(
                    f"Bit offset non supported for address '{address}'")

            bit_offset = 0

        elif str_data_type == "DI" or str_data_type == "DINT":
            db_number = int(db_number)
            data_type = DataType.DINT
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise AddressError(
                    f"Bit offset non supported for address '{address}'")

            bit_offset = 0

        elif str_data_type == "DW" or str_data_type == "DWORD":
            db_number = int(db_number)
            data_type = DataType.DWORD
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise AddressError(
                    f"Bit offset non supported for address '{address}'")

            bit_offset = 0

        elif str_data_type == "R" or str_data_type == "REAL":
            db_number = int(db_number)
            data_type = DataType.REAL
            start = int(start)
            length = 1

            if bit_offset is not None:
                raise AddressError(
                    f"Bit offset non supported for address '{address}'")

            bit_offset = 0

        elif str_data_type == "S":
            db_number = int(db_number)
            data_type = DataType.CHAR
            start = int(start)

            # For String addresses the bit offset corresponds to the length
            if bit_offset is None:
                raise AddressError(f"{address}")

            length = int(bit_offset)
            bit_offset = 0

        else:
            raise AddressError(f"Impossible to parse address: '{address}")

        return Item(
            memory_area=MemoryArea.DB,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length
        )

    elif address.startswith("I") or address.startswith("E"):
        match = re.match(
            r"[I,E]([B,C,I,W,DI,D,R])?(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise AddressError(f"{address}")

        str_data_type, start, bit_offset = match.groups()

        memory_area = MemoryArea.INPUT
        db_number = 0
        data_type = DataTypeMap[str_data_type] if str_data_type is not None else DataType.BIT
        start = int(start)
        bit_offset = int(bit_offset) if bit_offset is not None else 0

        if not 0 <= bit_offset <= 7:
            raise AddressError(
                f"The bit offset must be a value between 0 and 7 included")

        length = 1

        return Item(
            memory_area=memory_area,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length
        )

    elif address.startswith("Q") or address.startswith("A"):
        match = re.match(
            r"[Q,A]([B,C,I,W,DI,D,R])?(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise AddressError(f"{address}")

        str_data_type, start, bit_offset = match.groups()

        memory_area = MemoryArea.OUTPUT
        db_number = 0
        data_type = DataTypeMap[str_data_type] if str_data_type is not None else DataType.BIT
        start = int(start)
        bit_offset = int(bit_offset) if bit_offset is not None else 0

        if not 0 <= bit_offset <= 7:
            raise AddressError(
                f"The bit offset must be a value between 0 and 7 included")

        length = 1

        return Item(
            memory_area=memory_area,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length
        )

    elif address.startswith("M"):
        match = re.match(
            r"M([B,C,I,W,DI,D,R])?(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise AddressError("")

        str_data_type, start, bit_offset = match.groups()

        memory_area = MemoryArea.MERKER
        db_number = 0
        data_type = DataTypeMap[str_data_type] if str_data_type is not None else DataType.BIT
        start = int(start)
        bit_offset = int(bit_offset) if bit_offset is not None else 0

        if not 0 <= bit_offset <= 7:
            raise AddressError(
                f"The bit offset must be a value between 0 and 7 included")

        length = 1

        return Item(
            memory_area=memory_area,
            db_number=db_number,
            data_type=data_type,
            start=start,
            bit_offset=bit_offset,
            length=length
        )

    else:
        raise AddressError(f"Unsupported address '{address}'")
