from dataclasses import dataclass

from .constants import MemoryArea, DataType, DataTypeSize


@dataclass(frozen=True)
class Item:
    memory_area: MemoryArea
    db_number: int
    data_type: DataType
    start: int
    bit_offset: int
    length: int

    def __post_init__(self) -> None:
        if not isinstance(self.memory_area, MemoryArea):
            raise TypeError("memory_area should be of type MemoryArea")

        if not isinstance(self.db_number, int):
            raise TypeError("db_number should be of type int")
        
        if self.db_number < 0:
            raise ValueError("db_number value must be greater then 0")

        if not isinstance(self.data_type, DataType):
            raise TypeError("data_type should be of type DataType")

        if not isinstance(self.start, int):
            raise TypeError("start should be of type int")
        
        if self.start < 0:
            raise ValueError("start value must be greater or equal to 0")

        if not isinstance(self.bit_offset, int):
            raise TypeError("bit_offset should be of type int")

        if self.bit_offset < 0 or self.bit_offset > 7:
            raise ValueError("bit_offset value must be between 0 and 7")

        if not isinstance(self.length, int):
            raise TypeError("length should be of type int")

        if self.length <= 0:
            raise ValueError("length value must be greaten than 0")

    def size(self) -> int:
        """Return the Item size in bytes"""
        return DataTypeSize[self.data_type] * self.length

    def __contains__(self, item: 'Item') -> bool:
        if self.memory_area == item.memory_area and \
           self.db_number == item.db_number and \
           self.start <= item.start and \
           DataTypeSize[self.data_type] * self.length >= DataTypeSize[item.data_type] * item.length:

            return True
        return False
