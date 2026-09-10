import struct

import pytest

from pyS7 import DataType
from pyS7.errors import S7CommPlusProtocolError
from pyS7.s7commplus import S7CommPlusClient
from pyS7.s7commplus.browse import (
    S7DataBlockInfo,
    _parse_vartype_list,
    parse_type_info,
)
from pyS7.s7commplus.tag import S7SymbolicTag
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


def _array1d(
    lid: int,
    softdatatype: int,
    lower_bound: int,
    element_count: int,
    *,
    selector: int = 10,
    address: int = 0,
    crc: int = 0,
) -> bytes:
    return (
        struct.pack("<II", lid, crc)
        + bytes((softdatatype,))
        + struct.pack(">H", selector << 12)
        + b"\0"
        + struct.pack(
            "<HHIIiI",
            0,
            0,
            address,
            address + 100,
            lower_bound,
            element_count,
        )
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


@pytest.mark.parametrize("selector", [3, 10])
def test_array1d_offset_info_preserves_bounds_and_count(selector: int) -> None:
    raw = _blocks(
        struct.pack("<I", 2)
        + _array1d(
            0x40,
            0x08,
            -2,
            4,
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
    assert item.offset_info.array_lower_bound == -2
    assert item.offset_info.array_element_count == 4
    assert item.offset_info.is_array


def test_scalar_array_uses_declared_names_and_zero_based_access_ids() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_array1d(0x40, 0x08, 5, 3)],
        ("Values",),
    )

    tags = parse_type_info(
        _payload(root),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence, tag.data_type) for tag in tags] == [
        ("DB_Test.Values[5]", (0x40, 0), DataType.REAL),
        ("DB_Test.Values[6]", (0x40, 1), DataType.REAL),
        ("DB_Test.Values[7]", (0x40, 2), DataType.REAL),
    ]


def test_negative_array_lower_bound_only_changes_public_name() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_array1d(0x55, 0x05, -2, 3)],
        ("Samples",),
    )

    tags = parse_type_info(
        _payload(root),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence) for tag in tags] == [
        ("DB_Test.Samples[-2]", (0x55, 0)),
        ("DB_Test.Samples[-1]", (0x55, 1)),
        ("DB_Test.Samples[0]", (0x55, 2)),
    ]


def test_scalar_array_inside_struct_keeps_parent_and_array_lids() -> None:
    root_rid = 0x92000064
    struct_rid = 0x93000001

    root = _type_object(
        root_rid,
        [_struct_member(0x31, struct_rid)],
        ("MyStruct",),
    )
    child = _type_object(
        struct_rid,
        [_array1d(0x47, 0x07, 1, 2, selector=3)],
        ("Counters",),
    )

    tags = parse_type_info(
        _payload(root, child),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence, tag.data_type) for tag in tags] == [
        ("DB_Test.MyStruct.Counters[1]", (0x31, 0x47, 0), DataType.DINT),
        ("DB_Test.MyStruct.Counters[2]", (0x31, 0x47, 1), DataType.DINT),
    ]


def test_zero_length_scalar_array_emits_no_tags() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_array1d(0x40, 0x08, 0, 0)],
        ("Empty",),
    )

    assert (
        parse_type_info(
            _payload(root),
            root_rid,
            db_name="DB_Test",
            access_area=0x8A0E0064,
        )
        == []
    )


def test_unsupported_scalar_array_softdatatype_is_skipped() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_array1d(0x40, 0x99, 0, 3)],
        ("Unsupported",),
    )

    assert (
        parse_type_info(
            _payload(root),
            root_rid,
            db_name="DB_Test",
            access_area=0x8A0E0064,
        )
        == []
    )


def test_truncated_array1d_offset_info_is_rejected() -> None:
    element = (
        struct.pack("<II", 0x40, 0)
        + b"\x08"
        + struct.pack(">H", 0xA000)
        + b"\0"
        + b"\0" * 19
    )
    raw = _blocks(struct.pack("<I", 2) + element)

    with pytest.raises(S7CommPlusProtocolError, match="truncated Array1Dim OffsetInfo"):
        _parse_vartype_list(raw, 0)


def test_resolve_tag_accepts_array_element_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = S7CommPlusClient("192.0.2.1")
    db = S7DataBlockInfo("DB_Test", 100, 0x8A0E0064, 0x8A0E0064)
    expected = S7SymbolicTag(
        name="DB_Test.Values[5]",
        access_area=0x8A0E0064,
        access_sequence=(0x40, 0),
        data_type=DataType.REAL,
    )

    monkeypatch.setattr(client, "list_datablocks", lambda: [db])

    def browse(db_number: int | None = None) -> list[S7SymbolicTag]:
        assert db_number == 100
        client._cache_symbols([expected])
        return [expected]

    monkeypatch.setattr(client, "browse", browse)

    assert client.resolve_tag("DB_Test.Values[5]") == expected
