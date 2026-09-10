"""Provenance-safe codecs for S7CommPlus discovery and symbolic type metadata.

The type-information support emits scalar leaves from flat DB members and
non-array nested STRUCT/UDT members. Arrays remain intentionally unsupported.
"""

import logging
import struct
from collections.abc import Iterator
from dataclasses import dataclass

from ..constants import DataType
from ..errors import S7CommPlusProtocolError
from .codec import _decode_pvalue_at
from .protocol import DB_ACCESS_AREA_BASE
from .protocol import DataType as ProtocolDataType
from .tag import S7SymbolicTag
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

_MAX_TYPEINFO_RECURSION = 32

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
    vartypes: bytes | None = None
    varnames: bytes | None = None


@dataclass(frozen=True)
class OffsetInfo:
    """Layout metadata carried by one OMS type description."""

    optimized_address: int
    nonoptimized_address: int
    declared_length: int | None = None
    storage_hint: int | None = None
    relation_id: int | None = None

    @property
    def has_relation(self) -> bool:
        return self.relation_id is not None


@dataclass(frozen=True)
class VartypeListElement:
    """One independently addressed member in an OMS vartype list."""

    lid: int
    symbol_crc: int
    softdatatype: int
    attribute_flags: int
    bit_offset_info_flags: int
    offset_info: OffsetInfo

    @property
    def optimized_bit_offset(self) -> int:
        return self.bit_offset_info_flags & 0x07

    @property
    def nonoptimized_bit_offset(self) -> int:
        return (self.bit_offset_info_flags >> 4) & 0x07


_SOFTDATATYPE_MAP = {
    0x01: DataType.BIT,
    0x05: DataType.INT,
    0x07: DataType.DINT,
    0x08: DataType.REAL,
    0x0B: DataType.TIME,
    0x13: DataType.STRING,
    0x3E: DataType.WSTRING,
}


def _block(data: bytes, pos: int, name: str) -> tuple[memoryview | None, int]:
    if pos + 2 > len(data):
        raise S7CommPlusProtocolError(f"truncated EXPLORE {name} block length")
    length = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    if not length:
        return None, pos
    end = pos + length
    if end > len(data):
        raise S7CommPlusProtocolError(f"truncated EXPLORE {name} block")
    return memoryview(data)[pos:end], end


def _parse_vartype_list(data: bytes, pos: int) -> tuple[list[VartypeListElement], int]:
    """Parse every block; only the first non-empty block carries FirstId."""
    elements: list[VartypeListElement] = []
    first = True
    while True:
        block, pos = _block(data, pos, "VartypeList")
        if block is None:
            return elements, pos
        cursor = 0
        if first:
            if len(block) < 4:
                raise S7CommPlusProtocolError("truncated VartypeList FirstId")
            _first_id = struct.unpack_from("<I", block, 0)[0]
            cursor = 4
            first = False
        while cursor < len(block):
            if len(block) - cursor < 12:
                raise S7CommPlusProtocolError("truncated VartypeList element")
            lid, crc = struct.unpack_from("<II", block, cursor)
            softdatatype = block[cursor + 8]
            flags = struct.unpack_from(">H", block, cursor + 9)[0]
            bit_flags = block[cursor + 11]
            cursor += 12
            selector = (flags >> 12) & 0x0F
            if selector in (1, 8):
                if len(block) - cursor < 4:
                    raise S7CommPlusProtocolError("truncated Std OffsetInfo")
                first_address, second_address = struct.unpack_from("<HH", block, cursor)
                # StructElemStd (1) uses the legacy order: nonoptimized first,
                # optimized second. Std (8) uses optimized then nonoptimized.
                if selector == 1:
                    nonoptimized, optimized = first_address, second_address
                else:
                    optimized, nonoptimized = first_address, second_address
                offset = OffsetInfo(optimized, nonoptimized)
                cursor += 4
            elif selector in (2, 9):
                if len(block) - cursor < 12:
                    raise S7CommPlusProtocolError("truncated String OffsetInfo")
                declared, storage, optimized, nonoptimized = struct.unpack_from(
                    "<HHII", block, cursor
                )
                offset = OffsetInfo(optimized, nonoptimized, declared, storage)
                cursor += 12
            elif selector in (5, 12):
                # StructElemStruct (old firmware) and Struct (TLS-era firmware)
                # share the same relation-bearing wire layout in the reference:
                # 2x UInt16 LE metadata, optimized/nonoptimized UInt32 LE,
                # relation RID UInt32 LE, then four UInt32 LE struct-info values.
                if len(block) - cursor < 32:
                    raise S7CommPlusProtocolError("truncated Struct OffsetInfo")
                (
                    _unspecified1,
                    _unspecified2,
                    optimized,
                    nonoptimized,
                    relation_id,
                    _info4,
                    _info5,
                    _info6,
                    _info7,
                ) = struct.unpack_from("<HHIIIIIII", block, cursor)
                offset = OffsetInfo(
                    optimized,
                    nonoptimized,
                    relation_id=relation_id,
                )
                cursor += 32
            else:
                raise S7CommPlusProtocolError(
                    f"unsupported OffsetInfoType {selector} for LID 0x{lid:x}"
                )
            elements.append(
                VartypeListElement(lid, crc, softdatatype, flags, bit_flags, offset)
            )


def _parse_varname_list(data: bytes, pos: int) -> tuple[list[str], int]:
    names: list[str] = []
    while True:
        block, pos = _block(data, pos, "VarnameList")
        if block is None:
            return names, pos
        cursor = 0
        while cursor < len(block):
            length = block[cursor]
            cursor += 1
            end = cursor + length
            if end >= len(block):
                raise S7CommPlusProtocolError("truncated VarnameList name")
            raw = bytes(block[cursor:end])
            if block[end] != 0:
                raise S7CommPlusProtocolError("VarnameList name is not terminated")
            try:
                names.append(raw.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise S7CommPlusProtocolError("invalid VarnameList name") from exc
            cursor = end + 1


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
    """Decode one PValue using EXPLORE attribute semantics."""
    value, raw, end = _decode_pvalue_at(data, pos)
    if data[pos + 1] == ProtocolDataType.WSTRING:
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise S7CommPlusProtocolError("invalid EXPLORE WSTRING value") from exc
    return value, end


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
            pvalue_start = pos
            logger.debug(
                "PObject Attribute element_offset=0x%x attribute_id=0x%x "
                "pvalue_start=0x%x",
                element_offset,
                aid,
                pvalue_start,
            )
            value, new_pos = _pvalue(data, pvalue_start)
            if new_pos <= pvalue_start:
                raise S7CommPlusProtocolError(
                    "PValue parser did not advance cursor "
                    f"(start=0x{pvalue_start:x}, end=0x{new_pos:x}, "
                    f"attribute_id=0x{aid:x})"
                )
            pos = new_pos
            obj.attributes[aid] = value
        elif element == _RELATION:
            relation, used = decode_uint32(data, pos)
            pos += used
            if pos + 4 > len(data):
                raise S7CommPlusProtocolError("truncated EXPLORE relation value")
            obj.relations[relation] = struct.unpack_from(">I", data, pos)[0]
            pos += 4
        elif element == _START_TAG_DESCRIPTION:
            continue
        elif element == _VARTYPE_LIST:
            start = pos
            pos = _skip_block_list(data, pos, "VartypeList")
            obj.vartypes = data[start:pos]
        elif element == _VARNAME_LIST:
            start = pos
            pos = _skip_block_list(data, pos, "VarnameList")
            obj.varnames = data[start:pos]
        else:
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
        name_value = obj.attributes.get(OBJECT_VARIABLE_TYPE_NAME_AID, "")
        if not isinstance(name_value, str):
            raise S7CommPlusProtocolError("DB name is not a string value")
        name = name_value.rstrip("\0")
        result.append(S7DataBlockInfo(name, number, relation, relation))
    return result


def _walk_objects(objects: list[_PObject]) -> Iterator[_PObject]:
    for obj in objects:
        yield obj
        yield from _walk_objects(obj.children)


def _type_members(obj: _PObject) -> tuple[list[VartypeListElement], list[str]]:
    """Parse and validate one type object's parallel member/name lists."""
    vartypes = _parse_vartype_list(obj.vartypes or b"\0\0", 0)[0]
    names = _parse_varname_list(obj.varnames or b"\0\0", 0)[0]
    if len(vartypes) != len(names):
        raise S7CommPlusProtocolError(
            f"type-info list length mismatch: {len(vartypes)} elements, {len(names)} names"
        )
    return vartypes, names


def parse_type_info(
    payload: bytes,
    type_info_rid: int,
    *,
    db_name: str,
    access_area: int,
) -> list[S7SymbolicTag]:
    """Parse scalar leaves from flat and non-array nested STRUCT/UDT metadata."""
    status, pos = decode_uint64(payload)
    if status:
        raise S7CommPlusProtocolError(f"EXPLORE failed with PLC status 0x{status:x}")
    if pos + 4 > len(payload):
        raise S7CommPlusProtocolError("truncated EXPLORE response ExploreId")
    pos += 4
    objects, _ = _decode_object_list(payload, pos)

    all_objects = list(_walk_objects(objects))
    objects_by_relation: dict[int, _PObject] = {}
    for candidate in all_objects:
        objects_by_relation.setdefault(candidate.relation_id, candidate)

    root = objects_by_relation.get(type_info_rid)
    if root is None:
        raise S7CommPlusProtocolError(
            f"type-info object RID 0x{type_info_rid:08x} not found"
        )

    tags: list[S7SymbolicTag] = []

    def walk_type(
        obj: _PObject,
        name_prefix: str,
        access_prefix: tuple[int, ...],
        active_relations: frozenset[int],
        depth: int,
    ) -> None:
        if depth > _MAX_TYPEINFO_RECURSION:
            raise S7CommPlusProtocolError(
                f"type-info nesting depth exceeds {_MAX_TYPEINFO_RECURSION}"
            )

        vartypes, names = _type_members(obj)
        for name, member in zip(names, vartypes, strict=True):
            full_name = f"{name_prefix}.{name}"
            access_sequence = access_prefix + (member.lid,)
            relation_id = member.offset_info.relation_id

            if relation_id is not None:
                if relation_id in active_relations:
                    raise S7CommPlusProtocolError(
                        f"cyclic type-info relation 0x{relation_id:08x} at {full_name}"
                    )
                child = objects_by_relation.get(relation_id)
                if child is None:
                    raise S7CommPlusProtocolError(
                        f"type-info relation 0x{relation_id:08x} for {full_name} not found"
                    )
                walk_type(
                    child,
                    full_name,
                    access_sequence,
                    active_relations | {relation_id},
                    depth + 1,
                )
                continue

            datatype = _SOFTDATATYPE_MAP.get(member.softdatatype)
            if datatype is None:
                logger.debug(
                    "Skipping unsupported Softdatatype 0x%02x for %s",
                    member.softdatatype,
                    full_name,
                )
                continue
            tags.append(
                S7SymbolicTag(
                    name=full_name,
                    access_area=access_area,
                    access_sequence=access_sequence,
                    data_type=datatype,
                    symbol_crc=member.symbol_crc,
                )
            )

    walk_type(root, db_name, (), frozenset((type_info_rid,)), 0)
    return tags
