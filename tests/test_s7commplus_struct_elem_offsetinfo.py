import struct

from pyS7.s7commplus.browse import _parse_vartype_list


def _blocks(*values: bytes) -> bytes:
    return b"".join(struct.pack(">H", len(value)) + value for value in values) + b"\0\0"


def _header(lid: int, softdatatype: int, selector: int) -> bytes:
    return (
        struct.pack("<II", lid, 0)
        + bytes((softdatatype,))
        + struct.pack(">H", selector << 12)
        + b"\0"
    )


def test_struct_elem_std_uses_legacy_swapped_address_order() -> None:
    # OffsetInfoType 1: NonoptimizedAddress first, OptimizedAddress second.
    element = _header(0x09, 0x01, 1) + struct.pack("<HH", 0x1234, 0x5678)
    raw = _blocks(struct.pack("<I", 2) + element)

    item = _parse_vartype_list(raw, 0)[0][0]

    assert item.lid == 0x09
    assert item.offset_info.nonoptimized_address == 0x1234
    assert item.offset_info.optimized_address == 0x5678
    assert item.offset_info.relation_id is None


def test_struct_elem_string_uses_string_offsetinfo_layout() -> None:
    # OffsetInfoType 2 shares the String layout used by selector 9.
    element = _header(0x30, 0x13, 2) + struct.pack(
        "<HHII", 254, 256, 0x11223344, 0x55667788
    )
    raw = _blocks(struct.pack("<I", 2) + element)

    item = _parse_vartype_list(raw, 0)[0][0]

    assert item.lid == 0x30
    assert item.offset_info.declared_length == 254
    assert item.offset_info.storage_hint == 256
    assert item.offset_info.optimized_address == 0x11223344
    assert item.offset_info.nonoptimized_address == 0x55667788
    assert item.offset_info.relation_id is None
