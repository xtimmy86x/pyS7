"""Bounded S7CommPlus unsigned variable-length quantities."""

from ..errors import S7CommPlusProtocolError


def encode_uint32(value: int) -> bytes:
    """Encode an unsigned 32-bit integer, most-significant group first."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= 0xFFFFFFFF
    ):
        raise ValueError("VLQ value must be an unsigned 32-bit integer")
    groups = [value & 0x7F]
    value >>= 7
    while value:
        groups.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(groups))


def decode_uint32(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode a canonical, bounded unsigned 32-bit VLQ."""
    if offset < 0 or offset > len(data):
        raise S7CommPlusProtocolError("invalid VLQ offset")
    value = 0
    for consumed in range(1, 6):
        if offset + consumed > len(data):
            raise S7CommPlusProtocolError("truncated VLQ")
        octet = data[offset + consumed - 1]
        value = (value << 7) | (octet & 0x7F)
        if not octet & 0x80:
            if value > 0xFFFFFFFF:
                raise S7CommPlusProtocolError("VLQ exceeds 32-bit range")
            return value, consumed
    raise S7CommPlusProtocolError("unterminated VLQ")


def decode_uint64(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode the S7CommPlus 64-bit VLQ (the ninth byte has 8 data bits)."""
    if offset < 0 or offset > len(data):
        raise S7CommPlusProtocolError("invalid VLQ offset")
    value = 0
    for consumed in range(1, 9):
        if offset + consumed > len(data):
            raise S7CommPlusProtocolError("truncated VLQ")
        octet = data[offset + consumed - 1]
        value = (value << 7) | (octet & 0x7F)
        if not octet & 0x80:
            return value, consumed
    if offset + 9 > len(data):
        raise S7CommPlusProtocolError("truncated 64-bit VLQ")
    return (value << 8) | data[offset + 8], 9
