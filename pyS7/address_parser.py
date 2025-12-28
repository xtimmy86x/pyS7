import re
from dataclasses import dataclass
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
"""

@dataclass(frozen=True)
class _TokenInfo:
    data_type: DataType
    length: int = 1
    bit_offset_required: bool = False
    bit_offset_is_length: bool = False


TOKEN_TABLE: Dict[str, _TokenInfo] = {
    "X": _TokenInfo(DataType.BIT, bit_offset_required=True),
    "B": _TokenInfo(DataType.BYTE),
    "BYTE": _TokenInfo(DataType.BYTE),
    "C": _TokenInfo(DataType.CHAR),
    "CHAR": _TokenInfo(DataType.CHAR),
    "I": _TokenInfo(DataType.INT),
    "INT": _TokenInfo(DataType.INT),
    "W": _TokenInfo(DataType.WORD),
    "WORD": _TokenInfo(DataType.WORD),
    "DI": _TokenInfo(DataType.DINT),
    "DINT": _TokenInfo(DataType.DINT),
    "DW": _TokenInfo(DataType.DWORD),
    "DWORD": _TokenInfo(DataType.DWORD),
    "D": _TokenInfo(DataType.DWORD),
    "R": _TokenInfo(DataType.REAL),
    "REAL": _TokenInfo(DataType.REAL),
    "LR": _TokenInfo(DataType.LREAL),
    "LREAL": _TokenInfo(DataType.LREAL),    
    "S": _TokenInfo(DataType.CHAR, bit_offset_required=True, bit_offset_is_length=True),
}


def build_tag(
    memory_area: MemoryArea,
    db_number: int,
    data_type: DataType,
    start: int,
    bit_offset: int,
    length: int,
) -> S7Tag:
    return S7Tag(
        memory_area=memory_area,
        db_number=db_number,
        data_type=data_type,
        start=start,
        bit_offset=bit_offset,
        length=length,
    )


def _token_to_tag(
    token: str,
    memory_area: MemoryArea,
    db_number: int,
    start: int,
    bit_offset: Optional[str],
    address: str,
) -> S7Tag:
    info = TOKEN_TABLE.get(token)
    if info is None:
        raise S7AddressError(f"Impossible to parse address: '{address}'")

    if info.bit_offset_is_length:
        if bit_offset is None:
            raise S7AddressError(f"{address}")
        length = int(bit_offset)
        bit_offset_int = 0
    elif info.bit_offset_required:
        if bit_offset is None:
            raise S7AddressError("Missing bit_offset value")
        bit_offset_int = int(bit_offset)
        if not 0 <= bit_offset_int <= 7:
            raise S7AddressError("The bit offset must be a value between 0 and 7 included")
        length = info.length
    else:
        if bit_offset is not None:
            raise S7AddressError(f"Bit offset non supported for address '{address}'")
        bit_offset_int = 0
        length = info.length

    return build_tag(memory_area, db_number, info.data_type, start, bit_offset_int, length)

def map_address_to_tag(address: str) -> S7Tag:
    address = address.upper()
    match: Optional[re.Match[str]]

    if address.startswith("DB"):
        match = re.match(r"DB(\d+),([A-Z]+)(\d+)(?:\.(\d+))?", address)

        if match is None:
            raise S7AddressError(f"Impossible to parse address '{address}'")
        db_number_s, token, start_s, bit_offset = match.groups()
        db_number = int(db_number_s)
        start = int(start_s)
        return _token_to_tag(token, MemoryArea.DB, db_number, start, bit_offset, address)

    if address.startswith("I") or address.startswith("E"):
        match = re.match(r"[IE]([A-Z]+)?(\d+)(?:\.(\d+))?", address)
        if match is None:
            raise S7AddressError(f"{address}")
        token, start_s, bit_offset = match.groups()
        if token is None and bit_offset is None:
            raise S7AddressError(f"{address}")
        start = int(start_s)
        token = token if token is not None else "X"
        return _token_to_tag(token, MemoryArea.INPUT, 0, start, bit_offset, address)
    
    if address.startswith("Q") or address.startswith("A"):
        match = re.match(r"[QA]([A-Z]+)?(\d+)(?:\.(\d+))?", address)
        if match is None:
            raise S7AddressError(f"{address}")
        token, start_s, bit_offset = match.groups()
        if token is None and bit_offset is None:
            raise S7AddressError(f"{address}")
        start = int(start_s)
        token = token if token is not None else "X"
        return _token_to_tag(token, MemoryArea.OUTPUT, 0, start, bit_offset, address)
    
    if address.startswith("M"):
        match = re.match(r"M([A-Z]+)?(\d+)(?:\.(\d+))?", address)
        if match is None:
            raise S7AddressError(f"{address}")
        token, start_s, bit_offset = match.groups()
        if token is None and bit_offset is None:
            raise S7AddressError(f"{address}")
        start = int(start_s)
        token = token if token is not None else "X"
        return _token_to_tag(token, MemoryArea.MERKER, 0, start, bit_offset, address)
    
    raise S7AddressError(f"Unsupported address '{address}'")
