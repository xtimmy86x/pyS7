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


def _struct_member(lid: int, relation_id: int, address: int = 0) -> bytes:
    return (
        struct.pack("<II", lid, 0)
        + b"\x99"
        + struct.pack(">H", 0xC000)
        + b"\0"
        + struct.pack(
            "<HHIIIIIII",
            0,
            0,
            address,
            address + 100,
            relation_id,
            0,
            0,
            0,
            0,
        )
    )


def _struct_array1d(
    lid: int,
    relation_id: int,
    lower_bound: int,
    element_count: int,
    *,
    selector: int = 13,
    address: int = 0,
    crc: int = 0,
) -> bytes:
    return (
        struct.pack("<II", lid, crc)
        + b"\x99"
        + struct.pack(">H", selector << 12)
        + b"\0"
        + struct.pack(
            "<HHIIiIIIIIIII",
            0,
            0,
            address,
            address + 100,
            lower_bound,
            element_count,
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


@pytest.mark.parametrize("selector", [6, 13])
def test_struct_array1d_offset_info_preserves_relation_bounds_and_sizes(
    selector: int,
) -> None:
    raw = _blocks(
        struct.pack("<I", 2)
        + _struct_array1d(
            0x40,
            0x93000001,
            -1,
            3,
            selector=selector,
            address=24,
            crc=0x12345678,
        )
    )

    item = _parse_vartype_list(raw, 0)[0][0]

    assert item.lid == 0x40
    assert item.symbol_crc == 0x12345678
    assert item.offset_info.optimized_address == 24
    assert item.offset_info.nonoptimized_address == 124
    assert item.offset_info.array_lower_bound == -1
    assert item.offset_info.array_element_count == 3
    assert item.offset_info.nonoptimized_struct_size == 64
    assert item.offset_info.optimized_struct_size == 48
    assert item.offset_info.relation_id == 0x93000001
    assert item.offset_info.is_array
    assert item.offset_info.has_relation


def test_struct_array_emits_scalar_leaves_with_special_access_id() -> None:
    root_rid = 0x92000064
    element_rid = 0x93000001
    root = _type_object(
        root_rid,
        [_struct_array1d(0x40, element_rid, 5, 2)],
        ("Devices",),
    )
    child = _type_object(
        element_rid,
        [_std(0x07, 0x01), _std(0x22, 0x08)],
        ("Enabled", "Value"),
    )

    tags = parse_type_info(
        _payload(root, child),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence, tag.data_type) for tag in tags] == [
        ("DB_Test.Devices[5].Enabled", (0x40, 0, 1, 0x07), DataType.BIT),
        ("DB_Test.Devices[5].Value", (0x40, 0, 1, 0x22), DataType.REAL),
        ("DB_Test.Devices[6].Enabled", (0x40, 1, 1, 0x07), DataType.BIT),
        ("DB_Test.Devices[6].Value", (0x40, 1, 1, 0x22), DataType.REAL),
    ]


def test_struct_array_inside_struct_keeps_all_parent_ids() -> None:
    root_rid = 0x92000064
    parent_rid = 0x93000001
    element_rid = 0x94000001

    root = _type_object(root_rid, [_struct_member(0x31, parent_rid)], ("Outer",))
    parent = _type_object(
        parent_rid,
        [_struct_array1d(0x47, element_rid, 1, 2, selector=6)],
        ("Items",),
    )
    element = _type_object(element_rid, [_std(0x19, 0x05)], ("Count",))

    tags = parse_type_info(
        _payload(root, parent, element),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence) for tag in tags] == [
        ("DB_Test.Outer.Items[1].Count", (0x31, 0x47, 0, 1, 0x19)),
        ("DB_Test.Outer.Items[2].Count", (0x31, 0x47, 1, 1, 0x19)),
    ]


def test_struct_array_element_can_contain_nested_struct() -> None:
    root_rid = 0x92000064
    element_rid = 0x93000001
    nested_rid = 0x94000001

    root = _type_object(
        root_rid,
        [_struct_array1d(0x40, element_rid, 0, 1)],
        ("Items",),
    )
    element = _type_object(
        element_rid,
        [_struct_member(0x0A, nested_rid)],
        ("Nested",),
    )
    nested = _type_object(nested_rid, [_std(0x22, 0x08)], ("RealValue",))

    tag = parse_type_info(
        _payload(root, element, nested),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )[0]

    assert tag.name == "DB_Test.Items[0].Nested.RealValue"
    assert tag.access_sequence == (0x40, 0, 1, 0x0A, 0x22)
    assert tag.data_type is DataType.REAL


def test_struct_array_missing_relation_is_rejected() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_struct_array1d(0x40, 0x93001234, 0, 2)],
        ("Items",),
    )

    with pytest.raises(S7CommPlusProtocolError, match="0x93001234.*not found"):
        parse_type_info(
            _payload(root),
            root_rid,
            db_name="DB_Test",
            access_area=0x8A0E0064,
        )


def test_struct_array_relation_cycle_is_rejected() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_struct_array1d(0x40, root_rid, 0, 1)],
        ("Loop",),
    )

    with pytest.raises(S7CommPlusProtocolError, match="cyclic type-info relation"):
        parse_type_info(
            _payload(root),
            root_rid,
            db_name="DB_Test",
            access_area=0x8A0E0064,
        )


def test_truncated_struct_array1d_offset_info_is_rejected() -> None:
    element = (
        struct.pack("<II", 0x40, 0)
        + b"\x99"
        + struct.pack(">H", 0xD000)
        + b"\0"
        + b"\0" * 47
    )
    raw = _blocks(struct.pack("<I", 2) + element)

    with pytest.raises(
        S7CommPlusProtocolError, match="truncated Struct1Dim OffsetInfo"
    ):
        _parse_vartype_list(raw, 0)
