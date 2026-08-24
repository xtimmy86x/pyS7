"""Defensive, transport-independent S7CommPlus symbolic codecs."""

import struct
from collections.abc import Sequence

from ..errors import S7CommPlusProtocolError, S7SymbolicAccessError
from .protocol import (
    DB_VALUE_ACTUAL,
    MAX_ACCESS_SEQUENCE,
    MAX_PACKET_SIZE,
    PROTOCOL_ID,
    DataType,
    Opcode,
    ProtocolVersion,
)
from .vlq import decode_uint32, decode_uint64, encode_uint32


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


def decode_pvalue(data: bytes, offset: int) -> tuple[bytes, int]:
    if offset < 0 or offset + 2 > len(data):
        raise S7CommPlusProtocolError("truncated PValue header")
    flags, datatype = data[offset : offset + 2]
    if flags & ~0x10:
        raise S7CommPlusProtocolError("invalid PValue flags")
    pos = offset + 2
    fixed = {
        DataType.BOOL: 1,
        DataType.USINT: 1,
        DataType.SINT: 1,
        DataType.BYTE: 1,
        DataType.UINT: 2,
        DataType.INT: 2,
        DataType.WORD: 2,
        DataType.DWORD: 4,
        DataType.DINT: 4,
        DataType.REAL: 4,
        DataType.LWORD: 8,
        DataType.LREAL: 8,
        DataType.TIMESTAMP: 8,
    }
    if datatype == DataType.BLOB:
        length, used = decode_uint32(data, pos)
        pos += used
    elif datatype in fixed:
        count, used = decode_uint32(data, pos) if flags & 0x10 else (1, 0)
        pos += used
        length = count * fixed[DataType(datatype)]
    else:
        raise S7CommPlusProtocolError(f"unsupported PValue datatype 0x{datatype:02x}")
    if length > MAX_PACKET_SIZE or pos + length > len(data):
        raise S7CommPlusProtocolError("truncated or oversized PValue")
    return bytes(data[pos : pos + length]), pos + length - offset


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
