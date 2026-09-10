import struct

import pytest

from pyS7 import DataType
from pyS7.errors import S7CommPlusProtocolError
from pyS7.s7commplus.browse import _parse_vartype_list, parse_type_info
from pyS7.s7commplus.vlq import encode_uint32


def _blocks(*values: bytes) -> bytes:
    return b"".join(struct.pack(">H", len(value)) + value for value in values) + b"\0\0"


def _names(*values: str) -> bytes:
    raw = b"".join(bytes((len(value),)) + value.encode() + b"\0" for value in values)
    return _blocks(raw)


def _std(lid: int, softdatatype: int, address: int = 0) -> bytes:
    return (
        struct.pack("<II", lid, 0)
        + bytes((softdatatype,))
        + struct.pack(">H", 0x8000)
        + b"\0"
        + struct.pack("<HH", address, address + 100)
    )


def _array_mdim(
    lid: int,
    softdatatype: int,
    lower_bounds: tuple[int, ...],
    element_counts: tuple[int, ...],
    *,
    selector: int = 11,
    address: int = 0,
    crc: int = 0,
) -> bytes:
    assert len(lower_bounds) <= 6
    assert len(lower_bounds) == len(element_counts)
    padded_bounds = lower_bounds + (0,) * (6 - len(lower_bounds))
    padded_counts = element_counts + (0,) * (6 - len(element_counts))
    total = 1
    for count in element_counts:
        total *= count
    return (
        struct.pack("<II", lid, crc)
        + bytes((softdatatype,))
        + struct.pack(">H", selector << 12)
        + b"\0"
        + struct.pack(
            "<HHIIiI6i6I",
            0,
            0,
            address,
            address + 100,
            0,
            total,
            *padded_bounds,
            *padded_counts,
        )
    )


def _struct_array_mdim(
    lid: int,
    relation_id: int,
    lower_bounds: tuple[int, ...],
    element_counts: tuple[int, ...],
    *,
    selector: int = 14,
    address: int = 0,
    crc: int = 0,
) -> bytes:
    assert len(lower_bounds) <= 6
    assert len(lower_bounds) == len(element_counts)
    padded_bounds = lower_bounds + (0,) * (6 - len(lower_bounds))
    padded_counts = element_counts + (0,) * (6 - len(element_counts))
    total = 1
    for count in element_counts:
        total *= count
    return (
        struct.pack("<II", lid, crc)
        + b"\x99"
        + struct.pack(">H", selector << 12)
        + b"\0"
        + struct.pack(
            "<HHIIiI6i6I7I",
            0,
            0,
            address,
            address + 100,
            0,
            total,
            *padded_bounds,
            *padded_counts,
            64,
            48,
            relation_id,
            0,
            0,
            0,
            0,
        )
    )


def _pobj(rid: int, contents: bytes = b"") -> bytes:
    return (
        b"\xa1"
        + struct.pack(">I", rid)
        + encode_uint32(1)
        + b"\0\0"
        + contents
        + b"\xa2"
    )


def _type_object(rid: int, elements: list[bytes], names: tuple[str, ...]) -> bytes:
    vartypes = _blocks(struct.pack("<I", 2) + b"".join(elements))
    return _pobj(rid, b"\xab" + vartypes + b"\xac" + _names(*names))


def _payload(*objects: bytes) -> bytes:
    return b"\0\0\0\0\0" + b"".join(objects)


@pytest.mark.parametrize("selector", [4, 11])
def test_array_mdim_offset_info_preserves_dimensions(selector: int) -> None:
    raw = _blocks(
        struct.pack("<I", 2)
        + _array_mdim(
            0x50,
            0x08,
            (5, 1),
            (3, 2),
            selector=selector,
            address=24,
            crc=0x12345678,
        )
    )

    item = _parse_vartype_list(raw, 0)[0][0]

    assert item.lid == 0x50
    assert item.symbol_crc == 0x12345678
    assert item.offset_info.optimized_address == 24
    assert item.offset_info.nonoptimized_address == 124
    assert item.offset_info.array_element_count == 6
    assert item.offset_info.mdim_array_lower_bounds == (5, 1, 0, 0, 0, 0)
    assert item.offset_info.mdim_array_element_counts == (3, 2, 0, 0, 0, 0)
    assert item.offset_info.is_array
    assert item.offset_info.is_multidimensional_array


@pytest.mark.parametrize("selector", [7, 14])
def test_struct_mdim_offset_info_preserves_relation_and_sizes(selector: int) -> None:
    raw = _blocks(
        struct.pack("<I", 2)
        + _struct_array_mdim(
            0x60,
            0x93000001,
            (5, 1),
            (3, 2),
            selector=selector,
            address=32,
        )
    )

    item = _parse_vartype_list(raw, 0)[0][0]

    assert item.offset_info.optimized_address == 32
    assert item.offset_info.nonoptimized_address == 132
    assert item.offset_info.array_element_count == 6
    assert item.offset_info.mdim_array_lower_bounds == (5, 1, 0, 0, 0, 0)
    assert item.offset_info.mdim_array_element_counts == (3, 2, 0, 0, 0, 0)
    assert item.offset_info.nonoptimized_struct_size == 64
    assert item.offset_info.optimized_struct_size == 48
    assert item.offset_info.relation_id == 0x93000001


def test_scalar_mdim_array_uses_public_indexes_and_linear_access_ids() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_array_mdim(0x50, 0x08, (5, 1), (3, 2))],
        ("Matrix",),
    )

    tags = parse_type_info(
        _payload(root),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence, tag.data_type) for tag in tags] == [
        ("DB_Test.Matrix[1,5]", (0x50, 0), DataType.REAL),
        ("DB_Test.Matrix[1,6]", (0x50, 1), DataType.REAL),
        ("DB_Test.Matrix[1,7]", (0x50, 2), DataType.REAL),
        ("DB_Test.Matrix[2,5]", (0x50, 3), DataType.REAL),
        ("DB_Test.Matrix[2,6]", (0x50, 4), DataType.REAL),
        ("DB_Test.Matrix[2,7]", (0x50, 5), DataType.REAL),
    ]


def test_three_dimensional_array_keeps_rightmost_index_fastest() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_array_mdim(0x51, 0x05, (7, 2, -1), (2, 2, 2))],
        ("Cube",),
    )

    tags = parse_type_info(
        _payload(root),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence) for tag in tags] == [
        ("DB_Test.Cube[-1,2,7]", (0x51, 0)),
        ("DB_Test.Cube[-1,2,8]", (0x51, 1)),
        ("DB_Test.Cube[-1,3,7]", (0x51, 2)),
        ("DB_Test.Cube[-1,3,8]", (0x51, 3)),
        ("DB_Test.Cube[0,2,7]", (0x51, 4)),
        ("DB_Test.Cube[0,2,8]", (0x51, 5)),
        ("DB_Test.Cube[0,3,7]", (0x51, 6)),
        ("DB_Test.Cube[0,3,8]", (0x51, 7)),
    ]


def test_struct_mdim_array_inserts_special_access_id() -> None:
    root_rid = 0x92000064
    element_rid = 0x93000001
    root = _type_object(
        root_rid,
        [_struct_array_mdim(0x60, element_rid, (5, 1), (2, 2))],
        ("Devices",),
    )
    child = _type_object(
        element_rid,
        [_std(0x22, 0x08)],
        ("Value",),
    )

    tags = parse_type_info(
        _payload(root, child),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence) for tag in tags] == [
        ("DB_Test.Devices[1,5].Value", (0x60, 0, 1, 0x22)),
        ("DB_Test.Devices[1,6].Value", (0x60, 1, 1, 0x22)),
        ("DB_Test.Devices[2,5].Value", (0x60, 2, 1, 0x22)),
        ("DB_Test.Devices[2,6].Value", (0x60, 3, 1, 0x22)),
    ]


def test_mdim_array_element_count_mismatch_is_rejected() -> None:
    element = bytearray(_array_mdim(0x50, 0x08, (5, 1), (3, 2)))
    # Header is 12 bytes; ArrayMDim total count is at offset 12 + 16.
    struct.pack_into("<I", element, 28, 5)
    root_rid = 0x92000064
    root = _type_object(root_rid, [bytes(element)], ("Matrix",))

    with pytest.raises(S7CommPlusProtocolError, match="element count mismatch"):
        parse_type_info(
            _payload(root),
            root_rid,
            db_name="DB_Test",
            access_area=0x8A0E0064,
        )


def test_truncated_array_mdim_offset_info_is_rejected() -> None:
    element = (
        struct.pack("<II", 0x50, 0)
        + b"\x08"
        + struct.pack(">H", 0xB000)
        + b"\0"
        + b"\0" * 67
    )
    raw = _blocks(struct.pack("<I", 2) + element)

    with pytest.raises(S7CommPlusProtocolError, match="truncated ArrayMDim OffsetInfo"):
        _parse_vartype_list(raw, 0)


def test_truncated_struct_mdim_offset_info_is_rejected() -> None:
    element = (
        struct.pack("<II", 0x60, 0)
        + b"\x99"
        + struct.pack(">H", 0xE000)
        + b"\0"
        + b"\0" * 95
    )
    raw = _blocks(struct.pack("<I", 2) + element)

    with pytest.raises(S7CommPlusProtocolError, match="truncated StructMDim OffsetInfo"):
        _parse_vartype_list(raw, 0)
