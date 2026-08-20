"""Transport-independent S7 validation, conversion, and response parsing."""

import logging
import struct
from datetime import timedelta

from .constants import (
    MAX_PDU_SIZE,
    MIN_PDU_SIZE,
    READ_RES_OVERHEAD,
    RECOMMENDED_MIN_PDU,
    WRITE_RES_OVERHEAD,
    DataType,
    DataTypeSize,
    ReturnCode,
)
from .errors import S7ConnectionError
from .requests import Value
from .responses import (
    _parse_string,
    _parse_wstring,
    _return_code_name,
    extract_bit_from_byte,
)
from .results import ReadResult, WriteResult
from .tag import S7Tag


def tsap_from_string(tsap_str: str) -> int:
    if not isinstance(tsap_str, str):
        raise ValueError(f"tsap_str must be a string, got {type(tsap_str).__name__}")
    parts = tsap_str.split(".")
    if len(parts) != 2:
        raise ValueError(
            "TSAP string must be in format 'XX.YY' (e.g., '03.00', '22.00'), "
            f"got '{tsap_str}'"
        )
    try:
        byte1, byte2 = int(parts[0], 16), int(parts[1], 16)
    except ValueError as exc:
        raise ValueError(
            "TSAP string must contain hexadecimal numbers (e.g., '03.00', "
            f"'22.00'), got '{tsap_str}'"
        ) from exc
    if not 0 <= byte1 <= 255:
        raise ValueError(f"First byte must be in range 0x00-0xFF, got 0x{byte1:02X}")
    if not 0 <= byte2 <= 255:
        raise ValueError(f"Second byte must be in range 0x00-0xFF, got 0x{byte2:02X}")
    return (byte1 << 8) | byte2


def tsap_to_string(tsap: int) -> str:
    if not isinstance(tsap, int):
        raise ValueError(f"tsap must be an integer, got {type(tsap).__name__}")
    if not 0x0000 <= tsap <= 0xFFFF:
        raise ValueError(
            "tsap must be in range 0x0000-0xFFFF (0-65535), "
            f"got 0x{tsap:04X} ({tsap})"
        )
    return f"{(tsap >> 8) & 0xFF:02x}.{tsap & 0xFF:02x}"


def tsap_from_rack_slot(rack: int, slot: int) -> int:
    if not isinstance(rack, int) or not isinstance(slot, int):
        raise ValueError("rack and slot must be integers")
    if not 0 <= rack <= 7:
        raise ValueError(f"rack must be in range 0-7, got {rack}")
    if not 0 <= slot <= 31:
        raise ValueError(f"slot must be in range 0-31, got {slot}")
    return 0x0100 | (rack * 32 + slot)


def validate_single_tsap(tsap_value: int, tsap_name: str) -> None:
    if not isinstance(tsap_value, int):
        raise ValueError(
            f"{tsap_name} must be an integer, got {type(tsap_value).__name__}"
        )
    if not 0x0000 <= tsap_value <= 0xFFFF:
        raise ValueError(
            f"{tsap_name} must be in range 0x0000-0xFFFF (0-65535), "
            f"got 0x{tsap_value:04X} ({tsap_value})"
        )


def validate_tsap(local_tsap: int | None, remote_tsap: int | None) -> None:
    if (local_tsap is None) != (remote_tsap is None):
        raise ValueError(
            "Both local_tsap and remote_tsap must be provided together, or neither. "
            f"Got local_tsap={local_tsap}, remote_tsap={remote_tsap}"
        )
    if local_tsap is not None:
        validate_single_tsap(local_tsap, "local_tsap")
    if remote_tsap is not None:
        validate_single_tsap(remote_tsap, "remote_tsap")


def validate_and_adjust_pdu(
    requested: int, negotiated: int, logger: logging.Logger
) -> int:
    if requested > MAX_PDU_SIZE:
        logger.warning(
            f"Requested PDU size ({requested} bytes) exceeds protocol maximum ({MAX_PDU_SIZE} bytes). "
            f"Using {MAX_PDU_SIZE} bytes instead. Consider reducing max_pdu parameter in S7Client constructor."
        )
        requested = MAX_PDU_SIZE
    if negotiated <= 0 or negotiated < MIN_PDU_SIZE:
        raise S7ConnectionError(
            f"PLC returned invalid PDU size: {negotiated} bytes. Minimum required: {MIN_PDU_SIZE} bytes. "
            "Check PLC configuration or try a different connection type."
        )
    if negotiated > MAX_PDU_SIZE:
        logger.warning(
            f"PLC returned unusually large PDU size: {negotiated} bytes, clamping to protocol maximum: {MAX_PDU_SIZE} bytes"
        )
        negotiated = MAX_PDU_SIZE
    if negotiated < RECOMMENDED_MIN_PDU:
        logger.warning(
            f"⚠️  PLC negotiated very small PDU: {negotiated} bytes. This may limit functionality and performance. "
            f"Recommended minimum: {RECOMMENDED_MIN_PDU} bytes. Consider: 1) Checking PLC configuration, "
            "2) Using larger PDU in TIA Portal, 3) Reading/writing smaller data chunks."
        )
    if negotiated < requested:
        reduction_percent = ((requested - negotiated) / requested) * 100
        if reduction_percent >= 20:
            logger.info(
                f"PDU size reduced by {reduction_percent:.0f}%: requested {requested} bytes, "
                f"negotiated {negotiated} bytes. Operations will be automatically adjusted to fit smaller PDU."
            )
    return negotiated


def read_item_data_length(
    transport_size: int, length_field: int, fallback_size: int
) -> int:
    if transport_size in (0x03, 0x04, 0x05):
        data_length = (length_field + 7) // 8
    elif transport_size in (0x07, 0x09):
        data_length = length_field
    else:
        data_length = (length_field + 7) // 8 if length_field > 0 else 0
    return data_length if data_length > 0 else fallback_size


def parse_tag_value(
    tag: S7Tag, data_bytes: bytes, tags_map: dict[S7Tag, S7Tag] | None = None
) -> Value:
    del tags_map
    if tag.data_type == DataType.BIT:
        return bool(data_bytes[0])
    if tag.data_type == DataType.STRING:
        return _parse_string(data_bytes, 0, tag.length)
    if tag.data_type == DataType.WSTRING:
        return _parse_wstring(data_bytes, 0, tag.length)
    formats = {
        DataType.BYTE: ">B",
        DataType.USINT: ">B",
        DataType.SINT: ">b",
        DataType.INT: ">h",
        DataType.WORD: ">H",
        DataType.DINT: ">i",
        DataType.DWORD: ">I",
        DataType.REAL: ">f",
        DataType.LREAL: ">d",
        DataType.TIME: ">i",
    }
    if tag.length > 1:
        fmt = formats.get(tag.data_type)
        if fmt is None:
            return ()
        size = DataTypeSize[tag.data_type]
        if tag.data_type == DataType.TIME:
            return tuple(
                timedelta(
                    milliseconds=struct.unpack(
                        fmt, data_bytes[i * size : (i + 1) * size]
                    )[0]
                )
                for i in range(tag.length)
            )
        return tuple(
            struct.unpack(fmt, data_bytes[i * size : (i + 1) * size])[0]
            for i in range(tag.length)
        )
    if tag.data_type == DataType.CHAR:
        return str(struct.unpack(">c", data_bytes)[0].decode("ascii"))
    fmt = formats.get(tag.data_type)
    if fmt is not None:
        result = struct.unpack(fmt, data_bytes)[0]
        if tag.data_type == DataType.TIME:
            return timedelta(milliseconds=result)
        return result  # type: ignore[no-any-return]
    raise ValueError(f"Unsupported data type for parsing: {tag.data_type}")


def parse_write_response_detailed(data: bytes, tags: list[S7Tag]) -> list[WriteResult]:
    results: list[WriteResult] = []
    offset = WRITE_RES_OVERHEAD
    for tag in tags:
        try:
            return_code = struct.unpack_from(">B", data, offset)[0]
            offset += 1
            if return_code == ReturnCode.SUCCESS.value:
                results.append(WriteResult(tag=tag, success=True))
            else:
                results.append(
                    WriteResult(
                        tag=tag,
                        success=False,
                        error=f"PLC returned error: {_return_code_name(return_code)}",
                        error_code=return_code,
                    )
                )
        except Exception as exc:
            results.append(
                WriteResult(
                    tag=tag, success=False, error=f"Failed to parse response: {exc}"
                )
            )
    return results


def parse_read_response_detailed(
    data: bytes, tags: list[S7Tag], tags_map: dict[S7Tag, S7Tag] | None = None
) -> list[ReadResult]:
    results: list[ReadResult] = []
    offset = READ_RES_OVERHEAD
    for tag in tags:
        try:
            return_code = data[offset]
            if return_code == ReturnCode.SUCCESS.value:
                transport_size, length_field = (
                    data[offset + 1],
                    struct.unpack_from(">H", data, offset + 2)[0],
                )
                offset += 4
                length = read_item_data_length(transport_size, length_field, tag.size())
                payload = data[offset : offset + length]
                if len(payload) < length:
                    raise ValueError(
                        f"Response too short for tag data: expected {length} bytes, got {len(payload)}"
                    )
                offset += length + (length & 1)
                try:
                    results.append(
                        ReadResult(
                            tag=tag,
                            success=True,
                            value=parse_tag_value(tag, payload[: tag.size()], tags_map),
                        )
                    )
                except Exception as exc:
                    results.append(
                        ReadResult(
                            tag=tag,
                            success=False,
                            error=f"Failed to parse value: {exc}",
                        )
                    )
            else:
                results.append(
                    ReadResult(
                        tag=tag,
                        success=False,
                        error=f"PLC returned error: {_return_code_name(return_code)}",
                        error_code=return_code,
                    )
                )
                offset += 2
        except Exception as exc:
            results.append(
                ReadResult(
                    tag=tag, success=False, error=f"Failed to parse response: {exc}"
                )
            )
    return results


def parse_optimized_read_response_detailed(
    data: bytes, tags_map: dict[S7Tag, list[tuple[int, S7Tag]]]
) -> list[tuple[int, ReadResult]]:
    results: list[tuple[int, ReadResult]] = []
    offset = READ_RES_OVERHEAD
    for packed_tag, original_tags in tags_map.items():
        try:
            if offset >= len(data):
                raise ValueError(
                    f"Response too short: expected return code at offset {offset}, got {len(data)} bytes"
                )
            code = data[offset]
            if code != ReturnCode.SUCCESS.value:
                for idx, tag in original_tags:
                    results.append(
                        (
                            idx,
                            ReadResult(
                                tag=tag,
                                success=False,
                                error=f"PLC returned error: {_return_code_name(code)}",
                                error_code=code,
                            ),
                        )
                    )
                offset += 2
                continue
            if offset + 4 > len(data):
                raise ValueError(
                    f"Response too short while reading item header at offset {offset}"
                )
            size = read_item_data_length(
                data[offset + 1],
                struct.unpack_from(">H", data, offset + 2)[0],
                packed_tag.size(),
            )
            offset += 4
            payload = data[offset : offset + size]
            if len(payload) < size:
                raise ValueError(
                    f"Response too short for packed tag data: need {offset + size}, got {len(data)}"
                )
            for idx, tag in original_tags:
                try:
                    rel, tag_size = tag.start - packed_tag.start, tag.size()
                    if rel < 0 or rel + tag_size > len(payload):
                        raise ValueError(
                            f"Tag data out of packed bounds (rel={rel}, size={tag_size}, packed={len(payload)})"
                        )
                    value = (
                        extract_bit_from_byte(payload[rel], tag.bit_offset)
                        if tag.data_type == DataType.BIT
                        and packed_tag.data_type == DataType.BYTE
                        else parse_tag_value(tag, payload[rel : rel + tag_size])
                    )
                    results.append(
                        (idx, ReadResult(tag=tag, success=True, value=value))
                    )
                except Exception as exc:
                    results.append(
                        (
                            idx,
                            ReadResult(
                                tag=tag,
                                success=False,
                                error=f"Failed to parse value: {exc}",
                            ),
                        )
                    )
            offset += size + (size & 1)
        except Exception as exc:
            for idx, tag in original_tags:
                results.append(
                    (
                        idx,
                        ReadResult(
                            tag=tag,
                            success=False,
                            error=f"Failed to parse response: {exc}",
                        ),
                    )
                )
    results.sort(key=lambda item: item[0])
    return results
