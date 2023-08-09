import pytest

import pyS7
from pyS7.address_parser import map_address_to_item
from pyS7.constants import DataType, MemoryArea
from pyS7.item import Item


@pytest.mark.parametrize("test_input, expected",
    [
        ("DB50,X0.7", Item(memory_area=MemoryArea.DB, db_number=50, data_type=DataType.BIT, start=0, bit_offset=7, length=1)),
        ("DB23,B1", Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.BYTE, start=1, bit_offset=0, length=1)),
        ("db12,R5", Item(memory_area=MemoryArea.DB, db_number=12, data_type=DataType.REAL, start=5, bit_offset=0, length=1)),
        ("DB100,C2", Item(memory_area=MemoryArea.DB, db_number=100, data_type=DataType.CHAR, start=2, bit_offset=0, length=1)),
        ("DB42,I3", Item(memory_area=MemoryArea.DB, db_number=42, data_type=DataType.INT, start=3, bit_offset=0, length=1)),
        ("DB57,WORD4", Item(memory_area=MemoryArea.DB, db_number=57, data_type=DataType.WORD, start=4, bit_offset=0, length=1)),
        ("DB13,DI5", Item(memory_area=MemoryArea.DB, db_number=13, data_type=DataType.DINT, start=5, bit_offset=0, length=1)),
        ("DB19,DW6", Item(memory_area=MemoryArea.DB, db_number=19, data_type=DataType.DWORD, start=6, bit_offset=0, length=1)),
        ("DB21,R7", Item(memory_area=MemoryArea.DB, db_number=21, data_type=DataType.REAL, start=7, bit_offset=0, length=1)),
        ("DB2,S7.10", Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.CHAR, start=7, bit_offset=0, length=10)),
        ("M10.7", Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.BIT, start=10, bit_offset=7, length=1)),
        ("I0.2", Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BIT, start=0, bit_offset=2, length=1)),
        ("Q300.1", Item(memory_area=MemoryArea.OUTPUT, db_number=0, data_type=DataType.BIT, start=300, bit_offset=1, length=1)),
        ("QB20", Item(memory_area=MemoryArea.OUTPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=1)),
        ("MW320", Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.WORD, start=320, bit_offset=0, length=1))
    ]
)
def test_map_address_to_item(test_input, expected) -> None:
    assert map_address_to_item(address=test_input) == expected


@pytest.mark.parametrize("test_input, exception",
    [
        ("DBX50.1", pyS7.errors.AddressError),          # Wrong format
        ("DB50.DBX50.1", pyS7.errors.AddressError),     # Wrong format
        ("DB12,X10", pyS7.errors.AddressError),         # Missing bit offset
        ("DB12,X10.8", pyS7.errors.AddressError),       # Invalid bit offset
        ("DT23", pyS7.errors.AddressError),             # Invalid address
        ("DB1,FLOAT10", pyS7.errors.AddressError),      # FLOAT not good, use REAL instead
        ("DB56,B11.5", pyS7.errors.AddressError),       # Unsupported bit offset for type BYTE
        ("DB1,CHAR11.5", pyS7.errors.AddressError),     # Unsupported bit offset for type CHAR
        ("DB30,I0.5", pyS7.errors.AddressError),        # Unsupported bit offset for type INT
        ("DB16,DC5", pyS7.errors.AddressError),         # Wrong format
    ]
)
def test_invalid_address(test_input, exception) -> None:
    with pytest.raises(exception):
        map_address_to_item(test_input)
