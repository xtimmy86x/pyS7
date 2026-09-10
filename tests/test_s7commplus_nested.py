import struct

import pytest

from pyS7 import DataType
from pyS7.errors import S7CommPlusProtocolError, S7CommPlusSymbolNotFoundError
from pyS7.s7commplus import S7CommPlusClient
from pyS7.s7commplus.browse import S7DataBlockInfo, parse_type_info
from pyS7.s7commplus.tag import S7SymbolicTag
from pyS7.s7commplus.vlq import encode_uint32


def _blocks(*values: bytes) -> bytes:
    return b"".join(struct.pack(">H", len(value)) + value for value in values) + b"\0\0"


def _names(*values: str) -> bytes:
    raw = b"".join(bytes((len(value),)) + value.encode() + b"\0" for value in values)
    return _blocks(raw)


def _std(lid: int, softdatatype: int, address: int = 0, crc: int = 0) -> bytes:
    return (
        struct.pack("<II", lid, crc)
        + bytes((softdatatype,))
        + struct.pack(">H", 0x8000)
        + b"\0"
        + struct.pack("<HH", address, address + 100)
    )


def _struct_member(
    lid: int,
    relation_id: int,
    *,
    address: int = 0,
    crc: int = 0,
    selector: int = 12,
) -> bytes:
    return (
        struct.pack("<II", lid, crc)
        + b"\x99"
        + struct.pack(">H", selector << 12)
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
    # ReturnValue VLQ=0 + ExploreId UInt32=0, then the PObject list.
    return b"\0\0\0\0\0" + b"".join(objects)


def test_nested_struct_emits_scalar_leaves_with_parent_lid() -> None:
    root_rid = 0x92000064
    struct_rid = 0x93000001
    root = _type_object(
        root_rid,
        [_struct_member(0x31, struct_rid)],
        ("MyStruct",),
    )
    child = _type_object(
        struct_rid,
        [_std(0x07, 0x01), _std(0x22, 0x08)],
        ("BoolValue", "RealValue"),
    )

    tags = parse_type_info(
        _payload(root, child),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence, tag.data_type) for tag in tags] == [
        ("DB_Test.MyStruct.BoolValue", (0x31, 0x07), DataType.BIT),
        ("DB_Test.MyStruct.RealValue", (0x31, 0x22), DataType.REAL),
    ]


def test_nested_struct_recurses_more_than_one_level() -> None:
    root_rid = 0x92000064
    outer_rid = 0x93000001
    inner_rid = 0x94000001
    root = _type_object(
        root_rid, [_struct_member(0x31, outer_rid)], ("Outer",)
    )
    outer = _type_object(
        outer_rid, [_struct_member(0x07, inner_rid)], ("Inner",)
    )
    inner = _type_object(inner_rid, [_std(0x03, 0x08)], ("Value",))

    tags = parse_type_info(
        _payload(root, outer, inner),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert len(tags) == 1
    assert tags[0].name == "DB_Test.Outer.Inner.Value"
    assert tags[0].access_sequence == (0x31, 0x07, 0x03)
    assert tags[0].data_type is DataType.REAL


def test_flat_and_nested_members_are_emitted_together() -> None:
    root_rid = 0x92000064
    struct_rid = 0x93000001
    root = _type_object(
        root_rid,
        [_std(0x22, 0x08), _struct_member(0x31, struct_rid)],
        ("FlatReal", "MyStruct"),
    )
    child = _type_object(
        struct_rid,
        [_std(0x07, 0x01), _std(0x19, 0x05)],
        ("BoolValue", "IntValue"),
    )

    tags = parse_type_info(
        _payload(root, child),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )

    assert [(tag.name, tag.access_sequence) for tag in tags] == [
        ("DB_Test.FlatReal", (0x22,)),
        ("DB_Test.MyStruct.BoolValue", (0x31, 0x07)),
        ("DB_Test.MyStruct.IntValue", (0x31, 0x19)),
    ]


@pytest.mark.parametrize("selector", [5, 12])
def test_struct_offset_info_selectors_preserve_relation(selector: int) -> None:
    root_rid = 0x92000064
    child_rid = 0x93000001
    root = _type_object(
        root_rid,
        [_struct_member(0x41, child_rid, selector=selector)],
        ("Struct",),
    )
    child = _type_object(child_rid, [_std(0x09, 0x01)], ("Value",))

    tag = parse_type_info(
        _payload(root, child),
        root_rid,
        db_name="DB_Test",
        access_area=0x8A0E0064,
    )[0]

    assert tag.access_sequence == (0x41, 0x09)


def test_nested_relation_missing_is_rejected() -> None:
    root_rid = 0x92000064
    missing_rid = 0x93001234
    root = _type_object(
        root_rid,
        [_struct_member(0x31, missing_rid)],
        ("MissingStruct",),
    )

    with pytest.raises(S7CommPlusProtocolError, match="0x93001234.*not found"):
        parse_type_info(
            _payload(root),
            root_rid,
            db_name="DB_Test",
            access_area=0x8A0E0064,
        )


def test_nested_relation_cycle_is_rejected() -> None:
    root_rid = 0x92000064
    root = _type_object(
        root_rid,
        [_struct_member(0x31, root_rid)],
        ("Loop",),
    )

    with pytest.raises(S7CommPlusProtocolError, match="cyclic type-info relation"):
        parse_type_info(
            _payload(root),
            root_rid,
            db_name="DB_Test",
            access_area=0x8A0E0064,
        )


def test_resolve_tag_accepts_nested_exact_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = S7CommPlusClient("192.0.2.1")
    db = S7DataBlockInfo("DB_Test", 100, 0x8A0E0064, 0x8A0E0064)
    expected = S7SymbolicTag(
        name="DB_Test.MyStruct.RealValue",
        access_area=0x8A0E0064,
        access_sequence=(0x31, 0x22),
        data_type=DataType.REAL,
    )

    monkeypatch.setattr(client, "list_datablocks", lambda: [db])

    def browse(db_number: int | None = None) -> list[S7SymbolicTag]:
        assert db_number == 100
        client._cache_symbols([expected])
        return [expected]

    monkeypatch.setattr(client, "browse", browse)

    assert client.resolve_tag("DB_Test.MyStruct.RealValue") == expected


@pytest.mark.parametrize(
    "name",
    ["DB_Test", ".Value", "DB_Test.", "DB_Test..Value"],
)
def test_resolve_tag_rejects_malformed_nested_names(name: str) -> None:
    client = S7CommPlusClient("192.0.2.1")
    with pytest.raises(S7CommPlusSymbolNotFoundError, match="symbolic tag"):
        client.resolve_tag(name)
