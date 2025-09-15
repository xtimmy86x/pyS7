from dataclasses import dataclass
from typing import Any

from .constants import DataType, DataTypeSize, MemoryArea


@dataclass(frozen=True)
class S7Tag:
    memory_area: MemoryArea
    db_number: int
    data_type: DataType
    start: int
    bit_offset: int
    length: int

    def __post_init__(self) -> None:
        self._validate_memory_area()
        self._validate_db_number()
        self._validate_data_type()
        self._validate_start()
        self._validate_bit_offset()
        self._validate_length()

    def _validate_memory_area(self) -> None:
        self._ensure_instance(self.memory_area, MemoryArea, "memory_area")

    def _validate_db_number(self) -> None:
        self._ensure_instance(self.db_number, int, "db_number")
        if self.memory_area != MemoryArea.DB and self.db_number > 0:
            raise ValueError(
                f"Invalid 'db_number': Must be 0 when memory_area is {self.memory_area}, but got {self.db_number}."
            )
        self._ensure_non_negative(self.db_number, "db_number")

    def _validate_data_type(self) -> None:
        self._ensure_instance(self.data_type, DataType, "data_type")

    def _validate_start(self) -> None:
        self._ensure_instance(self.start, int, "start")
        self._ensure_non_negative(self.start, "start")

    def _validate_bit_offset(self) -> None:
        self._ensure_instance(self.bit_offset, int, "bit_offset")
        if self.data_type != DataType.BIT and self.bit_offset > 0:
            raise ValueError(
                f"Invalid 'bit_offset': Must be 0 when data_type is not DataType.BIT, but got {self.bit_offset}."
            )
        self._ensure_range(self.bit_offset, "bit_offset", 0, 7)

    def _validate_length(self) -> None:
        self._ensure_instance(self.length, int, "length")
        self._ensure_positive(self.length, "length")

    @staticmethod
    def _ensure_instance(value: Any, expected_type: type, field_name: str) -> None:
        if not isinstance(value, expected_type):
            raise TypeError(
                f"Invalid '{field_name}': Expected type {expected_type.__name__}, got {type(value)}."
            )

    @staticmethod
    def _ensure_non_negative(value: int, field_name: str) -> None:
        if value < 0:
            raise ValueError(
                f"Invalid '{field_name}': Expected non-negative value, got {value}."
            )

    @staticmethod
    def _ensure_positive(value: int, field_name: str) -> None:
        if value <= 0:
            raise ValueError(
                f"Invalid '{field_name}': Expected positive value, got {value}."
            )
        
    @staticmethod
    def _ensure_range(value: int, field_name: str, minimum: int, maximum: int) -> None:
        if value < minimum or value > maximum:
            raise ValueError(
                f"Invalid '{field_name}': Expected value between {minimum} and {maximum}, got {value}."
            )

    def size(self) -> int:
        """Return the S7Tag size in bytes"""
        return DataTypeSize[self.data_type] * self.length

    def __contains__(self, tag) -> bool:  # type: ignore
        if (
            self.memory_area == tag.memory_area
            and self.db_number == tag.db_number
            and self.start <= tag.start
            and self.start + DataTypeSize[self.data_type] * self.length
            >= tag.start + DataTypeSize[tag.data_type] * tag.length
        ):
            return True
        return False
