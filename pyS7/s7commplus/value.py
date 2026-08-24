"""Value conversion for raw S7CommPlus scalar reads."""

import struct
from datetime import timedelta
from typing import Any

from ..constants import DataType
from ..errors import S7CommPlusProtocolError
from ..responses import _parse_string, _parse_wstring

_SCALAR_FORMATS = {
    DataType.INT: ">h",
    DataType.DINT: ">i",
    DataType.REAL: ">f",
    DataType.TIME: ">i",
}


def decode_symbolic_value(data_type: DataType, raw: bytes) -> Any:
    """Decode one flat scalar using the same storage semantics as classic S7."""
    if data_type == DataType.BIT:
        if not raw:
            raise S7CommPlusProtocolError("truncated symbolic BIT value")
        return bool(raw[0])
    if data_type == DataType.STRING:
        if len(raw) < 2:
            raise S7CommPlusProtocolError("truncated symbolic STRING value")
        if len(raw) < 2 + raw[1]:
            raise S7CommPlusProtocolError("truncated symbolic STRING payload")
        return _parse_string(raw, 0, len(raw))
    if data_type == DataType.WSTRING:
        if len(raw) < 4:
            raise S7CommPlusProtocolError("truncated symbolic WSTRING value")
        current_length = int.from_bytes(raw[2:4], "big")
        if len(raw) < 4 + current_length * 2:
            raise S7CommPlusProtocolError("truncated symbolic WSTRING payload")
        return _parse_wstring(raw, 0, len(raw) // 2)

    fmt = _SCALAR_FORMATS.get(data_type)
    if fmt is None:
        raise S7CommPlusProtocolError(
            f"unsupported symbolic scalar data type: {data_type!r}"
        )
    required = struct.calcsize(fmt)
    if len(raw) < required:
        raise S7CommPlusProtocolError(
            f"truncated symbolic {data_type.name} value: "
            f"expected {required} bytes, got {len(raw)}"
        )
    value = struct.unpack_from(fmt, raw)[0]
    if data_type == DataType.TIME:
        return timedelta(milliseconds=value)
    return value
