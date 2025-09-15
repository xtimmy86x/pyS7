from typing import Union

import pytest

from pyS7.constants import DataType, DataTypeSize, MemoryArea
from pyS7.tag import S7Tag


def test_tag_creation() -> None:
    tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 10, 0, 1)
    assert tag.memory_area == MemoryArea.DB
    assert tag.db_number == 1
    assert tag.data_type == DataType.INT
    assert tag.start == 10
    assert tag.bit_offset == 0
    assert tag.length == 1


def test_size_calculation() -> None:
    tag = S7Tag(MemoryArea.MERKER, 0, DataType.REAL, 10, 0, 4)
    assert tag.size() == DataTypeSize[DataType.REAL] * 4


@pytest.mark.parametrize(
    "tag1, tag2, result",
    [
        (
            S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 1),
            S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1),
            True,
        ),
        (
            S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 1),
            S7Tag(MemoryArea.DB, 1, DataType.INT, 10, 0, 1),
            False,
        ),
        (
            S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 1),
            S7Tag(MemoryArea.DB, 1, DataType.INT, 30, 0, 1),
            False,
        ),
        (
            S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 1),
            S7Tag(MemoryArea.MERKER, 0, DataType.BYTE, 0, 0, 1),
            False,
        ),
    ],
)
def test_tag_contains(tag1: S7Tag, tag2: S7Tag, result: bool) -> None:
    assert tag1.__contains__(tag2) is result


def test_tag_not_contains() -> None:
    tag1 = S7Tag(MemoryArea.DB, 1, DataType.REAL, 20, 0, 1)
    tag2 = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
    assert tag1.__contains__(tag2) is False


@pytest.mark.parametrize(
    "memory_area, db_number, data_type, start, bit_offset, length, exception",
    [
        (
            "Not Memory Area",
            1,
            DataType.BYTE,
            0,
            0,
            1,
            TypeError,
        ),  # Incorrect memory area
        (
            MemoryArea.DB,
            -1,
            DataType.INT,
            0,
            0,
            1,
            ValueError,
        ),  # Negative db_number (<0)
        (MemoryArea.DB, 1, "Not DataType", 0, 0, 1, TypeError),  # Incorrect datatype
        (MemoryArea.COUNTER, 0, DataType.REAL, -1, 0, 1, ValueError),  # Negative start
        (
            MemoryArea.INPUT,
            1,
            DataType.DWORD,
            0,
            0,
            1,
            ValueError,
        ),  # db_number must be 0
        (
            MemoryArea.INPUT,
            0,
            DataType.DWORD,
            0,
            1,
            1,
            ValueError,
        ),  # bit_offset must be 0
        (MemoryArea.OUTPUT, 0, DataType.BIT, 0, 0, 0, ValueError),  # length = 0
        (
            MemoryArea.MERKER,
            "Not int",
            DataType.DINT,
            0,
            0,
            1,
            TypeError,
        ),  # Incorrect db_number
        (MemoryArea.DB, 10, DataType.WORD, "Not int", 0, 1, TypeError),
        (MemoryArea.DB, 2, DataType.BIT, 0, 6.5, 1, TypeError),
        (MemoryArea.DB, 2, DataType.BIT, 0, 8, 1, ValueError),
        (MemoryArea.DB, 2, DataType.BIT, 0, -1, 1, ValueError),
        (MemoryArea.MERKER, 0, DataType.BYTE, 0, 0, "length", TypeError),
    ],
)
def test_invalid_tag_creation(
    memory_area: MemoryArea,
    db_number: int,
    data_type: DataType,
    start: int,
    bit_offset: int,
    length: int,
    exception: Union[TypeError, ValueError],
) -> None:
    with pytest.raises(exception):  # type: ignore
        S7Tag(memory_area, db_number, data_type, start, bit_offset, length)
