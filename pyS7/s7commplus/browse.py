"""Minimal, provenance-safe codecs for S7CommPlus discovery.

This module intentionally stops at PLC-program object enumeration.  It does not
contain preset dictionaries, type tables, or a type-information interpreter.
"""

import logging
import struct
from dataclasses import dataclass

from ..errors import S7CommPlusProtocolError
from .protocol import DB_ACCESS_AREA_BASE, DataType
from .vlq import decode_uint32, decode_uint64, encode_uint32

PLC_PROGRAM_RID = 3
PLC_PROGRAM_CLASS_RID = 2520
OMS_TYPE_INFO_CONTAINER_RID = 537
DB_CLASS_RID = 2574
OBJECT_VARIABLE_TYPE_NAME_AID = 233
BLOCK_NUMBER_AID = 2521

_START_OBJECT = 0xA1
_END_OBJECT = 0xA2
_ATTRIBUTE = 0xA3
_RELATION = 0xA4
_START_TAG_DESCRIPTION = 0xA7
_END_TAG_DESCRIPTION = 0xA8
_VARTYPE_LIST = 0xAB
_VARNAME_LIST = 0xAC

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S7DataBlockInfo:
    """One data block discovered in PLC metadata order."""

    name: str
    number: int
    relation_id: int
    access_area: int


@dataclass
class _PObject:
    """Internal representation of one bounded EXPLORE PObject."""

    relation_id: int
    class_id: int
    class_flags: int
    attribute_id: int
    attributes: dict[int, object]
    children: list["_PObject"]
    relations: dict[int, int]


def build_explore_request(rid: int, attribute_ids: tuple[int, ...] = ()) -> bytes:
    """Encode a structured EXPLORE request for an object RID."""
    if not isinstance(rid, int) or isinstance(rid, bool) or not 0 <= rid <= 0xFFFFFFFF:
        raise ValueError("rid must be an unsigned 32-bit integer")
    if any(
        not isinstance(aid, int) or isinstance(aid, bool) or not 0 <= aid <= 0xFFFFFFFF
        for aid in attribute_ids
    ):
        raise ValueError("attribute IDs must be unsigned 32-bit integers")
    return (
        struct.pack(">I", rid)
        + b"\x00\x01\x01\x00\x00"
        + encode_uint32(len(attribute_ids))
        + b"".join(encode_uint32(aid) for aid in attribute_ids)
        + b"\x00" * 5
    )


def _pvalue(data: bytes, pos: int) -> tuple[object, int]:
    if pos + 2 > len(data):
        raise S7CommPlusProtocolError("truncated EXPLORE attribute value")
    flags, datatype = data[pos], data[pos + 1]
    pos += 2
    if flags & ~0x10:
        raise S7CommPlusProtocolError("invalid EXPLORE attribute flags")
    count = 1
    if flags & 0x10:
        count, used = decode_uint32(data, pos)
        pos += used
    fixed = {
        1: 1,
        2: 1,
        3: 2,
        4: None,
        5: None,
        6: 1,
        7: 2,
        8: None,
        9: None,
        10: 1,
        11: 2,
        12: 4,
        13: 8,
        14: 4,
        15: 8,
        16: 8,
        17: None,
        18: 4,
        19: 4,
    }
    if datatype in (DataType.BLOB, DataType.WSTRING):
        length, used = decode_uint32(data, pos)
        pos += used
        end = pos + length
        if end > len(data):
            raise S7CommPlusProtocolError("truncated EXPLORE attribute value")
        return bytes(data[pos:end]), end
    size = fixed.get(datatype)
    if datatype not in fixed:
        raise S7CommPlusProtocolError(f"unsupported EXPLORE datatype 0x{datatype:02x}")
    if size is None:
        values: list[int] = []
        for _ in range(count):
            value, used = (
                decode_uint64(data, pos)
                if datatype in (5, 9, 17)
                else decode_uint32(data, pos)
            )
            pos += used
            values.append(value)
        return (values if flags & 0x10 else values[0]), pos
    end = pos + count * size
    if end > len(data):
        raise S7CommPlusProtocolError("truncated EXPLORE attribute value")
    raw = bytes(data[pos:end])
    return (raw if flags & 0x10 or size > 4 else int.from_bytes(raw, "big")), end


def _skip_block_list(data: bytes, pos: int, element_name: str) -> int:
    """Skip a sequence of UInt16-sized blocks terminated by a zero size."""
    while True:
        if pos + 2 > len(data):
            raise S7CommPlusProtocolError(f"truncated EXPLORE {element_name}")
        block_length = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        if not block_length:
            return pos
        end = pos + block_length
        if end > len(data):
            raise S7CommPlusProtocolError(f"truncated EXPLORE {element_name}")
        pos = end


def _boundary_log(data: bytes, pos: int, obj: _PObject | None) -> None:
    """Log a bounded window around a non-fatal PObject boundary."""
    byte = data[pos] if pos < len(data) else None
    start, end = max(0, pos - 16), min(len(data), pos + 17)
    logger.debug(
        "PObject boundary at offset=0x%x relation_id=%s class_id=%s byte=%s "
        "context=%s",
        pos,
        f"0x{obj.relation_id:08x}" if obj else "none",
        f"0x{obj.class_id:x}" if obj else "none",
        f"0x{byte:02x}" if byte is not None else "EOF",
        data[start:end].hex(),
    )


def _decode_object(data: bytes, pos: int) -> tuple[_PObject, int]:
    """Decode exactly one PObject, retaining nested object boundaries."""
    if pos >= len(data) or data[pos] != _START_OBJECT:
        raise S7CommPlusProtocolError("expected EXPLORE StartOfObject")
    pos += 1
    if pos + 4 > len(data):
        raise S7CommPlusProtocolError("truncated EXPLORE object relation ID")
    relation_id = struct.unpack_from(">I", data, pos)[0]
    pos += 4
    class_id, used = decode_uint32(data, pos)
    pos += used
    class_flags, used = decode_uint32(data, pos)
    pos += used
    attribute_id, used = decode_uint32(data, pos)
    pos += used
    obj = _PObject(relation_id, class_id, class_flags, attribute_id, {}, [], {})

    while pos < len(data):
        element_offset = pos
        element = data[pos]
        pos += 1
        if element == _END_OBJECT:
            return obj, pos
        if element == _START_OBJECT:
            child, pos = _decode_object(data, element_offset)
            obj.children.append(child)
        elif element == _ATTRIBUTE:
            aid, used = decode_uint32(data, pos)
            pos += used
            value, pos = _pvalue(data, pos)
            obj.attributes[aid] = value
        elif element == _RELATION:
            relation, used = decode_uint32(data, pos)
            pos += used
            if pos + 4 > len(data):
                raise S7CommPlusProtocolError("truncated EXPLORE relation value")
            obj.relations[relation] = struct.unpack_from(">I", data, pos)[0]
            pos += 4
        elif element == _START_TAG_DESCRIPTION:
            # This marker has no body of its own.
            continue
        elif element in (_VARTYPE_LIST, _VARNAME_LIST):
            name = "VartypeList" if element == _VARTYPE_LIST else "VarnameList"
            pos = _skip_block_list(data, pos, name)
        else:
            # DecodeObject treats an unhandled element (including 0x00 and A8)
            # as the boundary of this object.  The tag itself has been consumed.
            _boundary_log(data, element_offset, obj)
            return obj, pos

    raise S7CommPlusProtocolError(
        f"truncated EXPLORE object tree (relation_id=0x{relation_id:08x}, "
        f"class_id=0x{class_id:x})"
    )


def _decode_object_list(data: bytes, pos: int) -> tuple[list[_PObject], int]:
    """Decode consecutive top-level objects without searching the payload."""
    objects: list[_PObject] = []
    while pos < len(data) and data[pos] == _START_OBJECT:
        obj, pos = _decode_object(data, pos)
        objects.append(obj)
    if pos < len(data):
        _boundary_log(data, pos, None)
    return objects, pos


def parse_datablocks(payload: bytes) -> list[S7DataBlockInfo]:
    """Extract only DB objects from an EXPLORE PLC-program PObject tree."""
    status, pos = decode_uint64(payload)
    if status:
        raise S7CommPlusProtocolError(f"EXPLORE failed with PLC status 0x{status:x}")
    if pos + 4 > len(payload):
        raise S7CommPlusProtocolError("truncated EXPLORE response ExploreId")
    explore_id = struct.unpack_from(">I", payload, pos)[0]
    pos += 4
    logger.debug(
        "EXPLORE normalized payload: return_value=0x%x explore_id=0x%08x "
        "object_bytes=%s",
        status,
        explore_id,
        payload[pos : pos + 64].hex(),
    )
    if pos == len(payload):
        raise S7CommPlusProtocolError("missing EXPLORE PObject list")
    if payload[pos] != _START_OBJECT:
        raise S7CommPlusProtocolError(
            f"EXPLORE PObject list does not start with StartOfObject "
            f"(got 0x{payload[pos]:02x})"
        )
    objects, _ = _decode_object_list(payload, pos)
    result: list[S7DataBlockInfo] = []
    program = next(
        (obj for obj in objects if obj.class_id == PLC_PROGRAM_CLASS_RID), None
    )
    if program is None:
        return result
    for obj in program.children:
        relation = obj.relation_id
        if obj.class_id != DB_CLASS_RID or relation >> 16 != DB_ACCESS_AREA_BASE >> 16:
            continue
        number = relation & 0xFFFF
        metadata_number = obj.attributes.get(BLOCK_NUMBER_AID)
        if metadata_number is not None and metadata_number != number:
            raise S7CommPlusProtocolError("DB number conflicts with relation ID")
        name_value = obj.attributes.get(OBJECT_VARIABLE_TYPE_NAME_AID, b"")
        if not isinstance(name_value, bytes):
            raise S7CommPlusProtocolError("DB name is not a string value")
        name = (
            name_value.decode("utf-16-be")
            if b"\0" in name_value
            else name_value.decode("utf-8")
        ).rstrip("\0")
        result.append(S7DataBlockInfo(name, number, relation, relation))
    return result
