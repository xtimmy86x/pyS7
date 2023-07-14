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
        
        if not isinstance(self.data_type, DataType):
            raise TypeError("data_type should be of type DataType")
        
        if not isinstance(self.start, int):
            raise TypeError("start should be of type int")
        
        if not isinstance(self.bit_offset, int):
            raise TypeError("bit_offset should be of type int")
        
        if not isinstance(self.length, int):
            raise TypeError("length should be of type int")

    def size(self) -> int:
        """Return the Item size in bytes"""
        return DataTypeSize[self.data_type] * self.length

    def __contains__(self, item) -> bool:
        if self.memory_area == item.memory_area and \
           self.db_number == item.db_number and \
           self.start <= item.start and \
           DataTypeSize[self.data_type] * self.length >= DataTypeSize[item.data_type] * item.length:

            return True
        return False
