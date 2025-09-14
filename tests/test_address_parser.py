import pytest

from pyS7.address_parser import map_address_to_tag
from pyS7.constants import DataType, MemoryArea
from pyS7.errors import S7AddressError
from pyS7.tag import S7Tag


@pytest.mark.parametrize(
    "test_input, expected",
    [
        ("DB50,X0.7", S7Tag(MemoryArea.DB, 50, DataType.BIT, 0, 7, 1)),
        ("DB23,B1", S7Tag(MemoryArea.DB, 23, DataType.BYTE, 1, 0, 1)),
        ("db12,R5", S7Tag(MemoryArea.DB, 12, DataType.REAL, 5, 0, 1)),
        ("DB100,C2", S7Tag(MemoryArea.DB, 100, DataType.CHAR, 2, 0, 1)),
        ("DB42,I3", S7Tag(MemoryArea.DB, 42, DataType.INT, 3, 0, 1)),
        ("DB57,WORD4", S7Tag(MemoryArea.DB, 57, DataType.WORD, 4, 0, 1)),
        ("DB13,DI5", S7Tag(MemoryArea.DB, 13, DataType.DINT, 5, 0, 1)),
        ("DB19,DW6", S7Tag(MemoryArea.DB, 19, DataType.DWORD, 6, 0, 1)),
        ("DB19,DWORD6", S7Tag(MemoryArea.DB, 19, DataType.DWORD, 6, 0, 1)),
        ("DB21,R7", S7Tag(MemoryArea.DB, 21, DataType.REAL, 7, 0, 1)),
        ("DB2,S7.10", S7Tag(MemoryArea.DB, 2, DataType.CHAR, 7, 0, 10)),
        ("M10.7", S7Tag(MemoryArea.MERKER, 0, DataType.BIT, 10, 7, 1)),
        ("I0.2", S7Tag(MemoryArea.INPUT, 0, DataType.BIT, 0, 2, 1)),
        ("IC3", S7Tag(MemoryArea.INPUT, 0, DataType.CHAR, 3, 0, 1)),
        ("Q300.1", S7Tag(MemoryArea.OUTPUT, 0, DataType.BIT, 300, 1, 1)),
        ("QB20", S7Tag(MemoryArea.OUTPUT, 0, DataType.BYTE, 20, 0, 1)),
        ("MW320", S7Tag(MemoryArea.MERKER, 0, DataType.WORD, 320, 0, 1)),
    ],
)
def test_map_address_to_tag(test_input: str, expected: S7Tag) -> None:
    assert map_address_to_tag(address=test_input) == expected


@pytest.mark.parametrize(
    "test_input, exception",
    [
        ("DB12,X10", S7AddressError),  # Missing bit offset
        ("DB12,X10.8", S7AddressError),  # Invalid bit offset
        ("DB12,W22.6", S7AddressError),  # Invalid bit offset
        ("DB12,DI40.1", S7AddressError),  # Invalid bit offset
        ("DB53,DW5.5", S7AddressError),  # Invalid bit offset
        ("DB24,R102.4", S7AddressError),  # Invalid bit offset
        ("I10.11", S7AddressError),  # Invalid bit offset
        ("A1.17", S7AddressError),  # Invalid bit offset
        ("M3.9", S7AddressError),  # Invalid bit offset
        ("DB12,S102", S7AddressError),  # Missing length
        ("DT23", S7AddressError),  # Invalid address
        ("DB1,FLOAT10", S7AddressError),  # FLOAT not good, use REAL instead
        ("DB56,B11.5", S7AddressError),  # Unsupported bit offset for type BYTE
        ("DB1,CHAR11.5", S7AddressError),  # Unsupported bit offset for type CHAR
        ("IC3.1", S7AddressError),  # Unsupported bit offset for type CHAR in input area
        ("DB30,I0.5", S7AddressError),  # Unsupported bit offset for type INT
        ("DBX50.1", S7AddressError),  # Wrong format
        ("DB50.DBX50.1", S7AddressError),  # Wrong format
        ("DB16,DC5", S7AddressError),  # Wrong format
        ("I1,10", S7AddressError),  # Wrong format
        ("M1?10", S7AddressError),  # Wrong format
        ("Q25?10,9", S7AddressError),  # Wrong format
        ("IEU,90", S7AddressError),  # Wrong format
        ("QZ,21", S7AddressError),  # Wrong format
        ("MUN21", S7AddressError),  # Wrong format
    ],
)
def test_invalid_address(test_input: str, exception: S7AddressError) -> None:
    with pytest.raises(exception):  # type: ignore
        map_address_to_tag(test_input)
