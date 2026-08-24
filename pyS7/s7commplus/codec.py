"""Defensive, transport-independent S7CommPlus symbolic codecs."""

import logging
import struct
from collections.abc import Sequence

from ..errors import S7CommPlusProtocolError, S7SymbolicAccessError
from .protocol import (
    DB_VALUE_ACTUAL,
    MAX_ACCESS_SEQUENCE,
    MAX_PACKET_SIZE,
    PROTOCOL_ID,
    DataType,
    FunctionCode,
    Opcode,
    ProtocolVersion,
)
from .vlq import decode_int32, decode_int64, decode_uint32, decode_uint64, encode_uint32

_MAX_PVALUE_DEPTH = 32

logger = logging.getLogger(__name__)


def _is_packed_struct_id(struct_id: int) -> bool:
    """Return whether a STRUCT ID selects the packed wire representation."""
    return 0x90000000 < struct_id < 0x9FFFFFFF or 0x02000000 < struct_id < 0x02FFFFFF


def validate_access(
    access_area: int, access_sequence: Sequence[int], symbol_crc: int = 0
) -> tuple[int, ...]:
    for name, value in (("access_area", access_area), ("symbol_crc", symbol_crc)):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= 0xFFFFFFFF
        ):
            raise ValueError(f"{name} must be an unsigned 32-bit integer")
    lids = tuple(access_sequence)
    if not lids or len(lids) > MAX_ACCESS_SEQUENCE:
        raise ValueError(f"access_sequence must contain 1..{MAX_ACCESS_SEQUENCE} LIDs")
    if any(
        not isinstance(lid, int) or isinstance(lid, bool) or not 0 <= lid <= 0xFFFFFFFF
        for lid in lids
    ):
        raise ValueError("every LID must be an unsigned 32-bit integer")
    return lids


def encode_frame(version: int, payload: bytes) -> bytes:
    try:
        ProtocolVersion(version)
    except ValueError as exc:
        raise ValueError("invalid protocol version") from exc
    if len(payload) > 0xFFFF:
        raise ValueError("invalid protocol version or oversized frame")
    return (
        struct.pack(">BBH", PROTOCOL_ID, version, len(payload))
        + payload
        + struct.pack(">BBH", PROTOCOL_ID, version, 0)
    )


def decode_frame(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < 8:
        raise S7CommPlusProtocolError("truncated S7CommPlus frame")
    protocol_id, version, length = struct.unpack_from(">BBH", frame)
    try:
        ProtocolVersion(version)
    except ValueError as exc:
        raise S7CommPlusProtocolError("invalid S7CommPlus frame header") from exc
    if protocol_id != PROTOCOL_ID:
        raise S7CommPlusProtocolError("invalid S7CommPlus frame header")
    if length > MAX_PACKET_SIZE or len(frame) != 4 + length + 4:
        raise S7CommPlusProtocolError("incorrect S7CommPlus packet length")
    if frame[-4:] != struct.pack(">BBH", PROTOCOL_ID, version, 0):
        raise S7CommPlusProtocolError("invalid S7CommPlus frame trailer")
    return version, frame[4:-4]


def encode_request_header(
    function: int, sequence: int, session_id: int, flags: int = 0x36
) -> bytes:
    return struct.pack(
        ">BHHHHIB", Opcode.REQUEST, 0, function, 0, sequence, session_id, flags
    )


def parse_response(payload: bytes, function: int, sequence: int) -> bytes:
    if len(payload) < 10:
        raise S7CommPlusProtocolError("truncated S7CommPlus response header")
    opcode, reserved1, actual_function, reserved2, actual_sequence, _flags = (
        struct.unpack_from(">BHHHHB", payload)
    )
    if opcode not in (Opcode.RESPONSE, Opcode.RESPONSE2) or reserved1 or reserved2:
        raise S7CommPlusProtocolError("invalid S7CommPlus response header")
    if actual_function != function:
        raise S7CommPlusProtocolError(
            f"unexpected response function 0x{actual_function:04x}"
        )
    if actual_sequence != sequence:
        raise S7CommPlusProtocolError("response sequence number does not match request")
    return payload[10:]


def extract_embedded_response_integrity(
    payload: bytes, function: int
) -> tuple[bytes, int]:
    """Extract an IntegrityId from a function-specific response envelope.

    Only EXPLORE currently uses an embedded response IntegrityId.  Its envelope
    is ReturnValue (a 64-bit VLQ), a fixed-width ExploreId, the IntegrityId VLQ,
    and then the PObject stream.  The returned payload preserves every
    application field except the session-owned IntegrityId.
    """
    if function != FunctionCode.EXPLORE:
        raise S7CommPlusProtocolError(
            "response function has no embedded IntegrityId layout"
        )
    _, return_value_length = decode_uint64(payload)
    integrity_offset = return_value_length + 4
    if integrity_offset > len(payload):
        raise S7CommPlusProtocolError("truncated EXPLORE response ExploreId")
    integrity_id, integrity_length = decode_uint32(payload, integrity_offset)
    normalized = (
        payload[:integrity_offset] + payload[integrity_offset + integrity_length :]
    )
    return normalized, integrity_id


def encode_object_qualifier(version: int, key: int = 0) -> bytes:
    result = bytearray(struct.pack(">I", 1256))
    result += encode_uint32(1257) + bytes((0, DataType.RID)) + struct.pack(">I", 0)
    result += encode_uint32(1258) + bytes((0, DataType.AID)) + encode_uint32(0)
    result += encode_uint32(1259) + bytes((0, DataType.UDINT))
    result += (
        struct.pack(">I", key)
        if version == ProtocolVersion.V1
        else encode_uint32(key) + b"\0"
    )
    return bytes(result)


def encode_item_address(
    access_area: int, access_sequence: Sequence[int], symbol_crc: int = 0
) -> tuple[bytes, int]:
    lids = validate_access(access_area, access_sequence, symbol_crc)
    encoded = (
        encode_uint32(symbol_crc)
        + encode_uint32(access_area)
        + encode_uint32(len(lids) + 1)
    )
    encoded += encode_uint32(DB_VALUE_ACTUAL) + b"".join(
        encode_uint32(lid) for lid in lids
    )
    return encoded, 4 + len(lids)


def build_symbolic_read(
    access_area: int, access_sequence: Sequence[int], symbol_crc: int, version: int
) -> bytes:
    address, fields = encode_item_address(access_area, access_sequence, symbol_crc)
    result = (
        struct.pack(">I", 0)
        + encode_uint32(1)
        + encode_uint32(fields)
        + address
        + encode_object_qualifier(version)
    )
    return result + struct.pack(">I", 0)


def build_symbolic_write(
    access_area: int,
    access_sequence: Sequence[int],
    data: bytes,
    symbol_crc: int,
    version: int,
) -> bytes:
    if not isinstance(data, bytes) or len(data) > MAX_PACKET_SIZE:
        raise ValueError("data must be bytes no larger than the packet limit")
    address, fields = encode_item_address(access_area, access_sequence, symbol_crc)
    pvalue = bytes((0, DataType.BLOB)) + encode_uint32(len(data)) + data
    return (
        struct.pack(">I", 0)
        + encode_uint32(1)
        + encode_uint32(fields)
        + address
        + encode_uint32(1)
        + pvalue
        + b"\0"
        + encode_object_qualifier(version)
        + struct.pack(">I", 0)
    )


def _decode_pvalue_at(
    data: bytes, offset: int, *, depth: int = 0
) -> tuple[object, bytes, int]:
    """Decode one PValue and return its value, raw value bytes, and end offset.

    ``offset`` always points at the flags byte.  This function owns and consumes
    the flags, datatype, and complete (possibly nested) body; its returned
    offset points at the first byte following the PValue.

    This cursor-oriented decoder is shared by symbolic values and EXPLORE
    attributes.  STRUCT values are intentionally opaque to callers, but are
    walked completely so the following PObject element remains aligned.
    """
    if depth >= _MAX_PVALUE_DEPTH:
        raise S7CommPlusProtocolError("PValue nesting depth exceeds 32")
    if offset < 0 or offset + 2 > len(data):
        raise S7CommPlusProtocolError("truncated PValue header")
    flags, datatype = data[offset : offset + 2]
    logger.debug(
        "PValue enter offset=0x%x flags=0x%02x datatype=0x%02x",
        offset,
        flags,
        datatype,
    )
    if flags & ~0x10:
        raise S7CommPlusProtocolError("invalid PValue flags")
    pos = offset + 2

    if datatype == DataType.STRUCT:
        if pos + 4 > len(data):
            raise S7CommPlusProtocolError("truncated STRUCT id")
        struct_id = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        packed = _is_packed_struct_id(struct_id)
        logger.debug(
            "STRUCT id=0x%08x form=%s", struct_id, "packed" if packed else "normal"
        )
        if packed:
            if pos + 8 > len(data):
                raise S7CommPlusProtocolError("truncated packed STRUCT timestamp")
            pos += 8
            transport_flags, used = decode_uint32(data, pos)
            pos += used
            count, used = decode_uint32(data, pos)
            pos += used
            if transport_flags & 0x400:
                count, used = decode_uint32(data, pos)
                pos += used
            end = pos + count
            if end > len(data):
                raise S7CommPlusProtocolError("truncated packed STRUCT payload")
        else:
            while True:
                key, used = decode_uint32(data, pos)
                pos += used
                if key == 0:
                    end = pos
                    break
                if pos + 2 > len(data):
                    raise S7CommPlusProtocolError("truncated PValue header")
                logger.debug(
                    "STRUCT member key=%d datatype=0x%02x", key, data[pos + 1]
                )
                _, _, pos = _decode_pvalue_at(data, pos, depth=depth + 1)
        raw = bytes(data[offset + 2 : end])
        logger.debug("PValue exit start=0x%x end=0x%x", offset, end)
        return raw, raw, end

    count = 1
    if flags & 0x10:
        count, used = decode_uint32(data, pos)
        pos += used
    fixed = {
        DataType.BOOL: 1,
        DataType.USINT: 1,
        DataType.SINT: 1,
        DataType.BYTE: 1,
        DataType.UINT: 2,
        DataType.INT: 2,
        DataType.WORD: 2,
        DataType.DWORD: 4,
        DataType.REAL: 4,
        DataType.LWORD: 8,
        DataType.LREAL: 8,
        DataType.TIMESTAMP: 8,
        # Unlike the VLQ-encoded AID, an RID is always a wire-order UInt32.
        DataType.RID: 4,
    }
    if datatype in (DataType.BLOB, DataType.WSTRING):
        length, used = decode_uint32(data, pos)
        pos += used
    elif datatype == DataType.AID and not flags & 0x10:
        value, used = decode_uint32(data, pos)
        raw = struct.pack(">I", value)
        end = pos + used
        logger.debug("PValue exit start=0x%x end=0x%x", offset, end)
        return value, raw, end
    elif datatype in (
        DataType.UDINT,
        DataType.ULINT,
        DataType.DINT,
        DataType.LINT,
        DataType.TIMESPAN,
    ):
        values: list[int] = []
        for _ in range(count):
            if datatype in (DataType.LINT, DataType.TIMESPAN):
                value, used = decode_int64(data, pos)
            elif datatype == DataType.DINT:
                value, used = decode_int32(data, pos)
            elif datatype == DataType.ULINT:
                value, used = decode_uint64(data, pos)
            else:
                value, used = decode_uint32(data, pos)
            pos += used
            values.append(value)
        if datatype == DataType.DINT:
            raw = b"".join(struct.pack(">i", item) for item in values)
        elif datatype in (DataType.LINT, DataType.TIMESPAN):
            raw = b"".join(struct.pack(">q", item) for item in values)
        else:
            raw = bytes(data[offset + 2 : pos])
        logger.debug("PValue exit start=0x%x end=0x%x", offset, pos)
        return (values if flags & 0x10 else values[0]), raw, pos
    elif datatype in fixed:
        length = count * fixed[DataType(datatype)]
    else:
        raise S7CommPlusProtocolError(f"unsupported PValue datatype 0x{datatype:02x}")
    if length > MAX_PACKET_SIZE or pos + length > len(data):
        raise S7CommPlusProtocolError("truncated or oversized PValue")
    raw = bytes(data[pos : pos + length])
    decoded: object = raw
    if not flags & 0x10 and length <= 4:
        decoded = int.from_bytes(raw, "big")
    end = pos + length
    logger.debug("PValue exit start=0x%x end=0x%x", offset, end)
    return decoded, raw, end


def decode_pvalue(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode the raw value used by symbolic read responses."""
    _, raw, end = _decode_pvalue_at(data, offset)
    return raw, end - offset


def parse_symbolic_read(payload: bytes) -> bytes:
    result, used = decode_uint64(payload)
    if result:
        raise S7SymbolicAccessError(
            f"symbolic read failed with PLC status 0x{result:x}", error_code=result
        )
    item, item_used = decode_uint32(payload, used)
    if item != 1:
        raise S7CommPlusProtocolError("symbolic read response does not contain item 1")
    value, value_used = decode_pvalue(payload, used + item_used)
    pos = used + item_used + value_used
    terminator, term_used = decode_uint32(payload, pos)
    if terminator != 0:
        raise S7CommPlusProtocolError("missing symbolic read value terminator")
    pos += term_used
    if pos >= len(payload):
        raise S7CommPlusProtocolError("missing symbolic read error terminator")
    error_item, error_used = decode_uint32(payload, pos)
    if error_item:
        code, _ = decode_uint64(payload, pos + error_used)
        raise S7SymbolicAccessError(
            f"symbolic item {error_item} failed with PLC status 0x{code:x}",
            error_code=code,
        )
    pos += error_used
    if pos != len(payload):
        raise S7CommPlusProtocolError("unexpected trailing symbolic read data")
    return value


def parse_symbolic_write(payload: bytes) -> None:
    result, used = decode_uint64(payload)
    if result:
        raise S7SymbolicAccessError(
            f"symbolic write failed with PLC status 0x{result:x}", error_code=result
        )
    item, item_used = decode_uint32(payload, used)
    if item:
        code, code_used = decode_uint64(payload, used + item_used)
        if used + item_used + code_used != len(payload):
            raise S7CommPlusProtocolError("unexpected trailing symbolic write data")
        raise S7SymbolicAccessError(
            f"symbolic item {item} failed with PLC status 0x{code:x}", error_code=code
        )
    if used + item_used != len(payload):
        raise S7CommPlusProtocolError("unexpected trailing symbolic write data")
