import struct

import pytest

from pyS7 import DataType
from pyS7.errors import S7CommPlusProtocolError
from pyS7.s7commplus.browse import (
    _parse_varname_list,
    _parse_vartype_list,
    parse_type_info,
)
from pyS7.s7commplus.vlq import encode_uint32


def std(lid: int, soft: int, address: int, bit: int = 0, crc: int = 0) -> bytes:
    return (
        struct.pack("<II", lid, crc)
        + bytes((soft,))
        + struct.pack(">H", 0x8000)
        + bytes((bit,))
        + struct.pack("<HH", address, address + 100)
    )


def string(lid: int, soft: int, address: int, crc: int = 0) -> bytes:
    return (
        struct.pack("<II", lid, crc)
        + bytes((soft,))
        + struct.pack(">H", 0x9000)
        + b"\0"
        + struct.pack("<HHII", 254, 256, address, address + 100)
    )


def blocks(*values: bytes) -> bytes:
    return b"".join(struct.pack(">H", len(value)) + value for value in values) + b"\0\0"


def names(*values: str) -> bytes:
    raw = b"".join(bytes((len(value),)) + value.encode() + b"\0" for value in values)
    return blocks(raw)


def pobj(rid: int, contents: bytes = b"", children: bytes = b"") -> bytes:
    return (
        b"\xa1"
        + struct.pack(">I", rid)
        + encode_uint32(1)
        + b"\0\0"
        + contents
        + children
        + b"\xa2"
    )


def payload(*objects: bytes) -> bytes:
    return b"\0\0\0\0\0" + b"".join(objects)


def test_multiblock_vartypes_first_id_only_once_and_zero_terminator() -> None:
    raw = blocks(
        struct.pack("<I", 0x80000002) + std(9, 1, 0, 3, 0x12345678), std(0x19, 5, 2)
    )
    result, used = _parse_vartype_list(raw, 0)
    assert used == len(raw)
    assert [item.lid for item in result] == [9, 0x19]
    assert result[0].symbol_crc == 0x12345678
    assert result[0].optimized_bit_offset == 3
    assert result[1].offset_info.optimized_address == 2


def test_string_offset_info_and_mixed_endian_fields() -> None:
    raw = blocks(struct.pack("<I", 2) + string(0x30, 0x13, 58, 0xA1B2C3D4))
    item = _parse_vartype_list(raw, 0)[0][0]
    assert (item.lid, item.symbol_crc, item.attribute_flags) == (
        0x30,
        0xA1B2C3D4,
        0x9000,
    )
    assert (item.offset_info.declared_length, item.offset_info.storage_hint) == (
        254,
        256,
    )
    assert item.offset_info.optimized_address == 58


def test_varname_list_blocks_and_termination() -> None:
    raw = blocks(b"\x04Bool\0", b"\x04Real\0")
    assert _parse_varname_list(raw, 0) == (["Bool", "Real"], len(raw))
    with pytest.raises(S7CommPlusProtocolError, match="terminated"):
        _parse_varname_list(blocks(b"\x04Bool!"), 0)


def type_object(rid: int, vartypes: bytes, member_names: bytes) -> bytes:
    return pobj(rid, b"\xab" + vartypes + b"\xac" + member_names)


def test_db_test_scalar_subset_pairing_noncontiguous_lids_and_rid_lookup() -> None:
    elements = [
        std(0x09, 0x01, 0, 0),
        std(0x19, 0x05, 2),
        std(0x22, 0x08, 26),
        std(0x28, 0x0B, 42),
        string(0x30, 0x13, 58),
        string(0x35, 0x3E, 1082),
    ]
    vartypes = blocks(
        struct.pack("<I", 0x80000002) + b"".join(elements[:2]), b"".join(elements[2:])
    )
    root = pobj(
        1,
        children=type_object(0x11111111, blocks(struct.pack("<I", 2)), blocks())
        + type_object(
            0x92000064,
            vartypes,
            names("Bool", "Int", "Real", "Time", "String", "Wstring"),
        ),
    )
    tags = parse_type_info(
        payload(root), 0x92000064, db_name="DB_Test", access_area=0x8A0E0064
    )
    assert [(tag.name, tag.access_sequence, tag.data_type) for tag in tags] == [
        ("DB_Test.Bool", (0x09,), DataType.BIT),
        ("DB_Test.Int", (0x19,), DataType.INT),
        ("DB_Test.Real", (0x22,), DataType.REAL),
        ("DB_Test.Time", (0x28,), DataType.TIME),
        ("DB_Test.String", (0x30,), DataType.STRING),
        ("DB_Test.Wstring", (0x35,), DataType.WSTRING),
    ]
    assert tags[2].access_area == 0x8A0E0064


def test_mismatched_lists_rejected() -> None:
    obj = type_object(7, blocks(struct.pack("<I", 2) + std(9, 1, 0)), names())
    with pytest.raises(S7CommPlusProtocolError, match="length mismatch"):
        parse_type_info(payload(obj), 7, db_name="DB", access_area=1)


def test_truncated_and_unsupported_vartype_elements() -> None:
    with pytest.raises(S7CommPlusProtocolError, match="truncated VartypeList element"):
        _parse_vartype_list(blocks(struct.pack("<I", 2) + b"short"), 0)
    unsupported = struct.pack("<II", 9, 0) + b"\x01" + struct.pack(">H", 0xA000) + b"\0"
    with pytest.raises(S7CommPlusProtocolError, match="unsupported OffsetInfoType 10"):
        _parse_vartype_list(blocks(struct.pack("<I", 2) + unsupported), 0)


def test_requested_relation_must_exist() -> None:
    with pytest.raises(S7CommPlusProtocolError, match="not found"):
        parse_type_info(payload(pobj(1)), 2, db_name="DB", access_area=1)
