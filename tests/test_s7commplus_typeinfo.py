import struct

import pytest

from pyS7 import DataType
from pyS7.errors import S7CommPlusProtocolError
from pyS7.s7commplus.browse import (
    _decode_object,
    _parse_varname_list,
    _parse_vartype_list,
    _pvalue,
    parse_type_info,
)
from pyS7.s7commplus.codec import _is_packed_struct_id
from pyS7.s7commplus.protocol import DataType as PValueDataType
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


def pstruct(struct_id: int, contents: bytes) -> bytes:
    return bytes((0, PValueDataType.STRUCT)) + struct.pack(">I", struct_id) + contents


REAL_PLC_NORMAL_STRUCT = bytes.fromhex(
    "00 17 00 00 06 06 8c 07 00 04 00 8c 08 00 04 00 8c 09 00 04 0c 00"
)


def test_real_plc_normal_struct_pvalue_lands_on_following_byte() -> None:
    """Regression fixture captured at type-info response offset 0x4f."""
    wire = REAL_PLC_NORMAL_STRUCT + b"\xff"

    value, end = _pvalue(wire, 0)

    assert end == len(REAL_PLC_NORMAL_STRUCT)
    assert wire[end] == 0xFF
    # STRUCT values remain opaque, but include the ID, all three keyed UDINT
    # PValues (0, 0, 12), and the key-list terminator.
    assert value == REAL_PLC_NORMAL_STRUCT[2:]
    assert not _is_packed_struct_id(0x00000606)


def test_real_plc_dint_attribute_stops_before_following_struct_attribute() -> None:
    captured = bytes.fromhex(
        "a3 8b 5f 00 08 02 a3 84 63 "
        "00 17 00 00 06 06 8c 07 00 04 00 8c 08 00 04 00 "
        "8c 09 00 04 0c 00 a3"
    )

    value, end = _pvalue(captured, 3)

    assert value == 2
    assert end == 6
    assert captured[end] == 0xA3
    assert captured[end : end + 3] == bytes.fromhex("a3 84 63")
    _, struct_end = _pvalue(captured, 9)
    assert captured[struct_end] == 0xA3


def test_real_plc_struct_attribute_does_not_create_false_object_boundaries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep the complete provenance-safe sequence beginning at offset 0x4c."""
    captured = bytes.fromhex(
        "a3 84 63 00 17 00 00 06 06 8c 07 00 04 00 8c 08 00 04 00 8c 09 00 04 0c 00 a3"
    )
    prefix = b"\0" * 0x4C
    assert (
        prefix + captured == prefix + b"\xa3\x84\x63" + REAL_PLC_NORMAL_STRUCT + b"\xa3"
    )

    # Complete the second attribute and object so _decode_object can prove that
    # the final A3 is interpreted only after the STRUCT has been consumed.
    object_wire = (
        b"\xa1"
        + struct.pack(">I", 0x92000064)
        + b"\x01\x00\x00"
        + captured
        + b"\x01\x00\x01\x01"
        + b"\xa2"
    )
    caplog.set_level("DEBUG", logger="pyS7.s7commplus.browse")
    caplog.set_level("DEBUG", logger="pyS7.s7commplus.codec")

    obj, end = _decode_object(object_wire, 0)

    assert end == len(object_wire)
    assert obj.attributes[611] == REAL_PLC_NORMAL_STRUCT[2:]
    assert obj.attributes[1] == 1
    assert not [
        record for record in caplog.records if "PObject boundary" in record.message
    ]

    pvalue_offset = 0x4F
    _, fixture_end = _pvalue(prefix + captured, pvalue_offset)
    assert fixture_end == 0x65
    assert (prefix + captured)[fixture_end] == 0xA3

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "element_offset=0x8 attribute_id=0x263 pvalue_start=0xb" in message
        for message in messages
    )
    assert any("STRUCT id=0x00000606 form=normal" in message for message in messages)
    assert any("STRUCT member key=1543 datatype=0x04" in message for message in messages)
    assert any("STRUCT member key=1544 datatype=0x04" in message for message in messages)
    assert any("STRUCT member key=1545 datatype=0x04" in message for message in messages)
    assert any("PValue exit start=0xb end=0x21" in message for message in messages)


def test_attribute_rejects_a_pvalue_decoder_that_does_not_advance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    object_wire = pobj(1, b"\xa3\x01\x00\x04\x00")
    monkeypatch.setattr(
        "pyS7.s7commplus.browse._pvalue", lambda data, pos: (None, pos)
    )

    with pytest.raises(S7CommPlusProtocolError, match="did not advance cursor"):
        _decode_object(object_wire, 0)


def test_normal_struct_is_consumed_through_terminator() -> None:
    wire = pstruct(
        0x1234,
        encode_uint32(1)
        + bytes((0, PValueDataType.RID))
        + struct.pack(">I", 0x90000001)
        + encode_uint32(2)
        + bytes((0, PValueDataType.BOOL, 1))
        + b"\0",
    )
    framed = wire + b"\xa3"
    _, end = _pvalue(framed, 0)
    assert end == len(wire)
    assert framed[end:] == b"\xa3"


def test_nested_normal_struct_is_consumed_recursively() -> None:
    inner = pstruct(2, b"\x01" + bytes((0, PValueDataType.BOOL, 1)) + b"\0")
    outer = pstruct(1, b"\x01" + inner + b"\0")
    assert _pvalue(outer + b"!", 0)[1] == len(outer)


@pytest.mark.parametrize(
    ("transport_flags", "counts", "payload_bytes"),
    [
        (0, b"\x03", b"abc"),
        (0x400, encode_uint32(1) + encode_uint32(4), b"data"),
    ],
)
def test_packed_struct_uses_effective_raw_byte_count(
    transport_flags: int, counts: bytes, payload_bytes: bytes
) -> None:
    wire = pstruct(
        0x92000064,
        struct.pack(">Q", 0x0102030405060708)
        + encode_uint32(transport_flags)
        + counts
        + payload_bytes,
    )
    assert _pvalue(wire + b"!", 0)[1] == len(wire)


@pytest.mark.parametrize(
    ("wire", "message"),
    [
        (bytes((0, PValueDataType.STRUCT)) + b"\0\0\0", "STRUCT id"),
        (pstruct(0x92000064, b"\0" * 7), "timestamp"),
        (pstruct(0x92000064, b"\0" * 8 + b"\x80"), "VLQ"),
        (pstruct(0x92000064, b"\0" * 8 + b"\0\x80"), "VLQ"),
        (pstruct(0x92000064, b"\0" * 8 + b"\0\x04ab"), "payload"),
        (pstruct(1, b"\x01" + bytes((0, PValueDataType.BOOL))), "truncated"),
        (pstruct(1, b"\x01" + bytes((0, 0xFF))), "unsupported"),
    ],
)
def test_struct_truncation_and_malformed_nested_values_are_rejected(
    wire: bytes, message: str
) -> None:
    with pytest.raises(S7CommPlusProtocolError, match=message):
        _pvalue(wire, 0)


def test_struct_recursion_depth_is_bounded() -> None:
    wire = pstruct(1, b"\0")
    for _ in range(32):
        wire = pstruct(1, b"\x01" + wire + b"\0")
    with pytest.raises(S7CommPlusProtocolError, match="nesting depth"):
        _pvalue(wire, 0)


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
