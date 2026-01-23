import struct
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

# Forward declaration for extract_bit_from_byte (defined later in this file)
# This allows us to reference it in type hints and avoid circular imports
from .constants import (
    COTP_PDU_TYPE_CC,
    READ_RES_OVERHEAD,
    S7_DATA_LENGTH_OFFSET,
    S7_HEADER_OFFSET,
    S7_MESSAGE_TYPE_OFFSET,
    S7_PARAM_LENGTH_OFFSET,
    S7_PROTOCOL_ID,
    S7_PROTOCOL_ID_OFFSET,
    SZL_RETURN_CODE_SUCCESS,
    TPKT_VERSION,
    WRITE_RES_OVERHEAD,
    DataType,
    MessageType,
    ReturnCode,
)
from .errors import S7ReadResponseError, S7WriteResponseError
from .requests import TagsMap, Value
from .tag import S7Tag


def _parse_string(bytes_data: Union[bytes, memoryview], offset: int, tag_length: int) -> str:
    """
    Parse S7 STRING data from bytes.

    S7 STRING structure: [max_length byte][current_length byte][string data...]
    Standard S7 STRING has max_length = 254 (0xFE).

    Args:
        bytes_data: The raw bytes or memoryview containing the STRING
        offset: The offset where the STRING data starts
        tag_length: The tag length for fallback parsing

    Returns:
        The decoded ASCII string
    """
    max_length = bytes_data[offset]
    current_length = bytes_data[offset + 1]

    # Validate header: max_length should be <= 254 and current_length <= max_length
    if max_length <= 254 and 0 <= current_length <= max_length:
        string_start = offset + 2
        string_end = string_start + current_length
        if isinstance(bytes_data, memoryview):
            return bytes_data[string_start:string_end].tobytes().decode("ascii")
        else:
            return bytes_data[string_start:string_end].decode("ascii")
    else:
        # Fallback: treat as raw character data without header
        string_end = offset + tag_length
        if isinstance(bytes_data, memoryview):
            return bytes_data[offset:string_end].tobytes().decode("ascii").rstrip("\x00")
        else:
            return bytes_data[offset:string_end].decode("ascii").rstrip("\x00")


def _parse_wstring(bytes_data: Union[bytes, memoryview], offset: int, tag_length: int) -> str:
    """
    Parse S7 WSTRING data from bytes.

    S7 WSTRING structure: [2 bytes max_length][2 bytes current_length][UTF-16 string data...]
    WSTRING uses 2-byte headers (unlike STRING which uses 1-byte headers).
    Note: current_length is the character count, but emojis use surrogate pairs (2 code units).

    Args:
        bytes_data: The raw bytes or memoryview containing the WSTRING
        offset: The offset where the WSTRING data starts
        tag_length: The tag length for fallback parsing

    Returns:
        The decoded UTF-16 string
    """
    if isinstance(bytes_data, memoryview):
        max_length = struct.unpack_from(">H", bytes_data, offset)[0]
        current_length = struct.unpack_from(">H", bytes_data, offset + 2)[0]
    else:
        max_length = struct.unpack_from(">H", bytes_data, offset)[0]
        current_length = struct.unpack_from(">H", bytes_data, offset + 2)[0]

    # Validate header: max_length should be reasonable and current_length <= max_length
    if max_length <= 16383 and 0 <= current_length <= max_length:
        string_start = offset + 4
        # Read the full string data area (max_length * 2 bytes)
        if isinstance(bytes_data, memoryview):
            string_bytes = bytes_data[string_start:string_start + (max_length * 2)].tobytes()
        else:
            string_bytes = bytes_data[string_start:string_start + (max_length * 2)]
        # Decode and find the actual string (stop at null terminator)
        decoded_full = string_bytes.decode("utf-16-be")
        # Find null terminator or use current_length as hint
        null_pos = decoded_full.find('\x00')
        return decoded_full[:null_pos] if null_pos >= 0 else decoded_full[:current_length]
    else:
        # Fallback: treat as raw UTF-16 data without header
        string_end = offset + (tag_length * 2)
        if isinstance(bytes_data, memoryview):
            return bytes_data[offset:string_end].tobytes().decode("utf-16-be").rstrip("\x00")
        else:
            return bytes_data[offset:string_end].decode("utf-16-be").rstrip("\x00")

COTP_DISCONNECT_REASONS: Dict[int, str] = {
    0x00: "Reason not specified",
    0x01: "Congestion at the destination transport endpoint",
    0x02: "Session entity congestion",
    0x03: "Address unknown",
    0x05: "Connection refused by remote transport endpoint",
    0x06: "Connection rejected due to remote transport endpoint being unavailable",
    0x07: "Connection rejected due to protocol error",
    0x09: "User initiated disconnect",
    0x0A: "Protocol error detected by the peer",
    0x0B: "Duplicate source reference",
}


@runtime_checkable
class Response(Protocol):
    def parse(self) -> Any:
        ...


class ConnectionResponse:
    def __init__(self, response: bytes) -> None:
        self.response = response

    def parse(self) -> Dict[str, Any]:
        if len(self.response) < 11:
            raise ValueError("Connection response too short")

        version, reserved, tpkt_length = struct.unpack_from(">BBH", self.response, offset=0)
        if version != TPKT_VERSION:
            raise ValueError(f"Unsupported TPKT version in connection response: expected {TPKT_VERSION}, got {version}")

        if tpkt_length != len(self.response):
            raise ValueError("TPKT length mismatch in connection response")

        cotp_length = self.response[4]
        if cotp_length != len(self.response) - 5:
            raise ValueError("COTP length mismatch in connection response")

        pdu_type = self.response[5]
        destination_reference = struct.unpack_from(">H", self.response, offset=6)[0]
        source_reference = struct.unpack_from(">H", self.response, offset=8)[0]

        header_field = self.response[10]

        parameters: List[Dict[str, Any]] = []
        offset = 11
        while offset + 1 < len(self.response):
            parameter_code = self.response[offset]
            parameter_length = self.response[offset + 1]
            value_start = offset + 2
            value_end = value_start + parameter_length

            if value_end > len(self.response):
                raise ValueError("Malformed COTP parameter in connection response")

            parameter_value = self.response[value_start:value_end]
            parameters.append(
                {
                    "code": parameter_code,
                    "length": parameter_length,
                    "value": parameter_value,
                }
            )

            offset = value_end

        is_success = pdu_type == COTP_PDU_TYPE_CC

        class_options: Optional[int] = None
        reason: Optional[int] = None
        reason_description: Optional[str] = None

        if is_success:
            class_options = header_field
        else:
            reason = header_field
            reason_description = COTP_DISCONNECT_REASONS.get(reason)

        cotp_info: Dict[str, Any] = {
            "length": cotp_length,
            "pdu_type": pdu_type,
            "destination_reference": destination_reference,
            "source_reference": source_reference,
            "parameters": parameters,
        }

        if class_options is not None:
            cotp_info["class_options"] = class_options

        if reason is not None:
            cotp_info["reason"] = reason
            if reason_description:
                cotp_info["reason_description"] = reason_description

        return {
            "tpkt": {
                "version": version,
                "reserved": reserved,
                "length": tpkt_length,
            },
            "cotp": cotp_info,
            "success": is_success,
        }


class PDUNegotiationResponse:
    def __init__(self, response: bytes) -> None:
        self.response = response

    def parse(self) -> Tuple[int, int, int]:
        max_jobs_calling, max_jobs_called, pdu_size = struct.unpack_from(
            ">HHH", self.response, offset=21
        )
        return (max_jobs_calling, max_jobs_called, pdu_size)


class ReadResponse:
    def __init__(self, response: bytes, tags: List[S7Tag]) -> None:
        self.response = response
        self.tags = tags

    def parse(self) -> List[Value]:
        return parse_read_response(bytes_response=self.response, tags=self.tags)


class ReadOptimizedResponse:
    def __init__(self, response: bytes, tag_map: TagsMap) -> None:
        self.responses: List[bytes] = [response]
        self.tags_map = [tag_map]

        self.n_messages = 1

    def __iadd__(self, other: "ReadOptimizedResponse") -> "ReadOptimizedResponse":
        self.responses += other.responses
        self.tags_map += other.tags_map

        self.n_messages += 1

        return self

    def parse(self) -> List[Value]:
        return parse_optimized_read_response(
            bytes_responses=self.responses, tags_map=self.tags_map
        )


class WriteResponse:
    def __init__(self, response: bytes, tags: List[S7Tag]) -> None:
        self.response: bytes = response
        self.tags: List[S7Tag] = tags

    def parse(self) -> None:
        parse_write_response(bytes_response=self.response, tags=self.tags)


def _return_code_name(return_code: int) -> str:
    """Convert return code to human-readable name.
    
    Args:
        return_code: Numeric return code from PLC response
        
    Returns:
        Enum name if recognized, otherwise formatted hex string
    """
    try:
        return ReturnCode(return_code).name
    except ValueError:
        return f"UNKNOWN_RETURN_CODE_0x{return_code:02X}"


def parse_read_response(bytes_response: bytes, tags: List[S7Tag]) -> List[Value]:
    parsed_data: List[Tuple[Union[bool, int, float], ...]] = []
    offset = READ_RES_OVERHEAD  # Response offset where data starts

    for i, tag in enumerate(tags):
        # Check if we have enough data for the return code
        if offset >= len(bytes_response):
            raise S7ReadResponseError(
                f"{tag}: response too short (got {len(bytes_response)} bytes, "
                f"expected at least {offset + 1} bytes for return code)"
            )

        return_code = struct.unpack_from(">B", bytes_response, offset)[0]

        if return_code == ReturnCode.SUCCESS.value:
            offset += 4

            if tag.data_type == DataType.BIT:
                # For non-optimized BIT reads, PLC returns the bit value directly (0 or 1)
                data: Any = bool(bytes_response[offset])
                offset += tag.size()
                # Skip fill byte
                offset += 0 if i == len(tags) - 1 else 1

            elif tag.data_type == DataType.BYTE:
                data = struct.unpack_from(
                    f">{tag.length * 'B'}", bytes_response, offset
                )
                offset += tag.size()
                # Skip fill byte
                offset += 0 if i == len(tags) - 1 else 1

            elif tag.data_type == DataType.CHAR:
                data = bytes_response[offset : offset + tag.length].decode()
                offset += tag.size()
                # Skip byte if char length is odd
                offset += 0 if tag.length % 2 == 0 else 1

            elif tag.data_type == DataType.STRING:
                data = _parse_string(bytes_response, offset, tag.length)
                offset += tag.size()
                offset += 0 if tag.size() % 2 == 0 else 1

            elif tag.data_type == DataType.WSTRING:
                data = _parse_wstring(bytes_response, offset, tag.length)
                offset += tag.size()
                offset += 0 if tag.size() % 2 == 0 else 1

            elif tag.data_type == DataType.INT:
                data = struct.unpack_from(
                    f">{tag.length * 'h'}", bytes_response, offset
                )
                offset += tag.size()

            elif tag.data_type == DataType.WORD:
                data = struct.unpack_from(
                    f">{tag.length * 'H'}", bytes_response, offset
                )
                offset += tag.size()

            elif tag.data_type == DataType.DWORD:
                data = struct.unpack_from(
                    f">{tag.length * 'I'}", bytes_response, offset
                )
                offset += tag.size()

            elif tag.data_type == DataType.DINT:
                data = struct.unpack_from(
                    f">{tag.length * 'l'}", bytes_response, offset
                )
                offset += tag.size()

            elif tag.data_type == DataType.REAL:
                data = struct.unpack_from(
                    f">{tag.length * 'f'}", bytes_response, offset
                )
                offset += tag.size()

            elif tag.data_type == DataType.LREAL:
                data = struct.unpack_from(
                    f">{tag.length * 'd'}", bytes_response, offset
                )
                offset += tag.size()

            else:
                raise ValueError(f"DataType: {tag.data_type} not supported")

            parsed_data.append(data)

        else:
            # Special handling for BIT data type with INVALID_DATA_SIZE error
            if (tag.data_type == DataType.BIT and
                return_code == ReturnCode.INVALID_DATA_SIZE.value):
                raise S7ReadResponseError(
                    f"{tag}: {_return_code_name(return_code)}. "
                    f"Some S7 PLCs do not support reading individual bits. "
                    f"Workaround: Read the entire byte using 'DB{tag.db_number},B{tag.start}' "
                    f"and extract bit {tag.bit_offset} using extract_bit_from_byte() function "
                    f"from pyS7.responses, or use optimized read operations."
                )
            else:
                raise S7ReadResponseError(f"{tag}: {_return_code_name(return_code)}")

    processed_data: List[Value] = [
        data[0] if isinstance(data, tuple) and len(data) == 1 else data
        for data in parsed_data
    ]

    return processed_data


def parse_optimized_read_response(
    bytes_responses: List[bytes], tags_map: List[TagsMap]
) -> List[Value]:
    parsed_data: List[Tuple[int, Value]] = []

    unpack_from = struct.unpack_from  # micro-binding for performance
    ReturnCodeSuccess = ReturnCode.SUCCESS.value

    # Map DataType -> struct format char (always big-endian with '>')
    fmt_map = {
        DataType.BYTE: "B",
        DataType.INT: "h",
        DataType.WORD: "H",
        DataType.DWORD: "I",
        DataType.DINT: "l",
        DataType.REAL: "f",
        DataType.LREAL: "d",
    }

    for i, bytes_response in enumerate(bytes_responses):
        mv = memoryview(bytes_response)  # zero-copy access to bytes
        offset = READ_RES_OVERHEAD

        # Iterate over packed tags inside this response
        for packed_tag, tags in tags_map[i].items():
            if offset >= len(mv):
                raise S7ReadResponseError(
                    f"{packed_tag}: response too short (got {len(mv)} bytes, "
                    f"expected at least {offset + 1} bytes for return code). "
                )
            # 1 byte return code (just read directly from memoryview)
            return_code = mv[offset]
            if return_code != ReturnCodeSuccess:
                raise S7ReadResponseError(
                    f"{packed_tag}: {_return_code_name(return_code)}"
                )

            # Response header is 4 bytes (status + 3 length bytes)
            if offset + 4 > len(mv):
                raise S7ReadResponseError(
                    f"{packed_tag}: response too short while reading header"
                )
            offset += 4
            base_off = offset  # start of actual data
            packed_size = packed_tag.size()
            if base_off + packed_size > len(mv):
                raise S7ReadResponseError(
                    f"{packed_tag}: response too short for packed data"
                )

            # Iterate through the unpacked tags inside this packed block
            for idx, tag in tags:
                rel = tag.start - packed_tag.start
                abs_off = base_off + rel
                dt = tag.data_type
                if abs_off + tag.size() > len(mv):
                    raise S7ReadResponseError(
                        f"{tag}: response too short for tag data"
                    )

                if dt == DataType.BIT:
                    # Check if this is a packed BIT tag (when the packed_tag is a BYTE)
                    # or an individual BIT tag (when the packed_tag is also a BIT)
                    if packed_tag.data_type == DataType.BYTE:
                        # This BIT tag was packed into a BYTE read - extract specific bit
                        data_byte = mv[abs_off]
                        value: Value = extract_bit_from_byte(data_byte, tag.bit_offset)
                    else:
                        # This is an individual BIT tag - PLC returns bit value directly
                        # Process the same as non-optimized reads
                        data_byte = mv[abs_off]
                        value = bool(data_byte)

                elif dt == DataType.CHAR:
                    # Slice without copy until decoding
                    str_end = abs_off + tag.length
                    value = mv[abs_off:str_end].tobytes().decode("ascii")

                elif dt == DataType.STRING:
                    value = _parse_string(mv, abs_off, tag.length)

                elif dt == DataType.WSTRING:
                    value = _parse_wstring(mv, abs_off, tag.length)

                else:
                    # Numeric scalar/array types
                    fmt_char = fmt_map.get(dt)
                    if fmt_char is None:
                        raise ValueError(f"DataType: {dt} not supported")

                    if tag.length > 1:
                        fmt = f">{tag.length}{fmt_char}"
                        value = unpack_from(fmt, mv, abs_off)
                    else:
                        fmt = f">{fmt_char}"
                        value = unpack_from(fmt, mv, abs_off)[0]

                parsed_data.append((idx, value))

            # Advance to the end of this packed block, align to 2 bytes
            # packed_size = packed_tag.size()
            offset += packed_size + (packed_size & 1)

    # Sort values by original tag index and return only the values
    parsed_data.sort(key=lambda t: t[0])
    return [v for _, v in parsed_data]


def parse_write_response(bytes_response: bytes, tags: List[S7Tag]) -> None:
    offset = WRITE_RES_OVERHEAD  # Response offset where data starts

    for tag in tags:
        return_code = struct.unpack_from(">B", bytes_response, offset)[0]

        if return_code == ReturnCode.SUCCESS.value:
            offset += 1

        else:
            raise S7WriteResponseError(
                f"Impossible to write tag {tag} - {_return_code_name(return_code)} "
            )


def extract_bit_from_byte(byte_value: int, bit_offset: int) -> bool:
    """
    Extract a specific bit from a byte value.

    Args:
        byte_value: The byte value (0-255) to extract the bit from
        bit_offset: The bit position (0-7, where 0 is the least significant bit)

    Returns:
        bool: True if the bit is set, False otherwise

    Example:
        # To read bit 2 from DB1,B0 when individual bit reads fail:
        # 1. Read the byte: client.read(["DB1,B0"])  # Returns [byte_value]
        # 2. Extract the bit: extract_bit_from_byte(byte_value, 2)
    """
    if not 0 <= bit_offset <= 7:
        raise ValueError("bit_offset must be between 0 and 7")
    if not 0 <= byte_value <= 255:
        raise ValueError("byte_value must be between 0 and 255")

    return bool((byte_value >> bit_offset) & 1)


class SZLResponse:
    """Response parser for System Status List (SZL) data from an S7 device."""

    def __init__(self, response: bytes) -> None:
        self.response = response

    def parse(self) -> Dict[str, Any]:
        """
        Parse the SZL response and extract the data.

        Returns:
            Dict containing the parsed SZL data with keys:
                - szl_id: The SZL ID that was read
                - szl_index: The SZL index
                - length_dr: Length of data record
                - n_dr: Number of data records
                - data: Raw data bytes
        """
        if len(self.response) < 25:
            raise ValueError(f"SZL response too short: {len(self.response)} bytes")

        # Parse TPKT header
        tpkt_version = self.response[0]
        if tpkt_version != 0x03:
            raise ValueError(f"Invalid TPKT version: {tpkt_version}")

        tpkt_length = struct.unpack_from(">H", self.response, 2)[0]
        if tpkt_length != len(self.response):
            raise ValueError(f"TPKT length mismatch: expected {tpkt_length}, got {len(self.response)}")

        # Skip COTP (3 bytes at offset 4)
        # S7 header starts at offset 7
        offset = S7_HEADER_OFFSET

        protocol_id = self.response[offset + S7_PROTOCOL_ID_OFFSET]
        if protocol_id != S7_PROTOCOL_ID:
            raise ValueError(f"Invalid S7 protocol ID: {protocol_id:#x}")

        message_type = self.response[offset + S7_MESSAGE_TYPE_OFFSET]
        if message_type != MessageType.USERDATA.value:
            raise ValueError(f"Expected USERDATA message type, got {message_type:#x}")

        param_length = struct.unpack_from(">H", self.response, offset + S7_PARAM_LENGTH_OFFSET)[0]
        data_length = struct.unpack_from(">H", self.response, offset + S7_DATA_LENGTH_OFFSET)[0]

        # Parameter section starts after S7 header (10 bytes)
        param_offset = offset + 10

        # Data section starts after parameter
        data_offset = param_offset + param_length

        if data_offset + data_length > len(self.response):
            raise ValueError("Invalid SZL response: data extends beyond packet")

        # Parse data section
        return_code = self.response[data_offset]
        if return_code != SZL_RETURN_CODE_SUCCESS:
            raise ValueError(f"SZL request failed with return code: {return_code:#x}")

        # SZL data structure
        szl_id = struct.unpack_from(">H", self.response, data_offset + 4)[0]
        szl_index = struct.unpack_from(">H", self.response, data_offset + 6)[0]
        length_dr = struct.unpack_from(">H", self.response, data_offset + 8)[0]  # Length of one data record
        n_dr = struct.unpack_from(">H", self.response, data_offset + 10)[0]  # Number of data records

        # Extract the actual data records
        data_start = data_offset + 12
        data_end = data_start + (length_dr * n_dr)

        if data_end > len(self.response):
            raise ValueError("Invalid SZL response: data records extend beyond packet")

        data_bytes = self.response[data_start:data_end]

        return {
            "szl_id": szl_id,
            "szl_index": szl_index,
            "length_dr": length_dr,
            "n_dr": n_dr,
            "data": data_bytes,
        }

    def parse_cpu_status(self) -> str:
        """
        Parse the CPU status from SZL ID 0x0424 response.

        Returns:
            str: CPU status ("RUN", "STOP", or other status string)
        """
        szl_data = self.parse()

        if szl_data["szl_id"] != 0x0424:
            raise ValueError(f"Invalid SZL ID for CPU status: {szl_data['szl_id']:#x}, expected 0x0424")

        data = szl_data["data"]

        if len(data) < 5:
            raise ValueError("Insufficient data for CPU status")

        # For SZL 0x0424 (W#16#xy424), the status information is structured as:
        # Byte 0: Reserved (0x02 typically)
        # Byte 1: Status bits (0x51 typically for both RUN and STOP)
        # Byte 2: Event bits (0xFF typically)
        # Byte 3: CPU operating mode
        #   - 0x08: RUN mode
        #   - 0x03: STOP mode
        #   - Other values may indicate different states
        # Byte 4+: Other diagnostic info
        status_byte = data[3]

        # Check the operating mode byte
        if status_byte == 0x08:
            return "RUN"
        elif status_byte == 0x03:
            return "STOP"
        else:
            # Return descriptive status for other values
            return f"UNKNOWN (0x{status_byte:02X})"

    def parse_cpu_info(self) -> Dict[str, Any]:
        """
        Parse CPU information from SZL ID 0x0011 response (Module Identification).

        Returns:
            Dict containing CPU information with keys:
                - module_type_name: String name of the CPU module (order number)
                - hardware_version: Hardware version
                - firmware_version: Firmware version (may be "N/A" if not in this SZL)
                - modules: List of all module records found

        Note:
            Some PLCs (e.g., S7-1200) do not expose firmware version in SZL 0x0011.
            The firmware version shown in TIA Portal may come from the project file
            or other SZL IDs that are not universally supported.
        """
        szl_data = self.parse()

        if szl_data["szl_id"] != 0x0011:
            raise ValueError(f"Invalid SZL ID for CPU info: {szl_data['szl_id']:#x}, expected 0x0011")

        data = szl_data["data"]
        length_dr = szl_data["length_dr"]
        n_dr = szl_data["n_dr"]

        if len(data) < length_dr:
            raise ValueError("Insufficient data for CPU info")

        # Parse all module identification records
        # Each record is length_dr bytes (typically 28 bytes)
        # Structure per record:
        # - Index (2 bytes)
        # - Module type name/order number (20 bytes, ASCII)
        # - Reserved (2 bytes)
        # - Hardware version (2 bytes)
        # - Firmware version (2 bytes)

        modules = []
        info: Dict[str, Any] = {}

        for i in range(n_dr):
            offset = i * length_dr
            record_data = data[offset:offset + length_dr]

            if len(record_data) < length_dr:
                break

            module: Dict[str, Any] = {}

            # Index (bytes 0-1)
            index = struct.unpack(">H", record_data[0:2])[0]
            module["index"] = f"0x{index:04X}"

            # Module type name / order number (bytes 2-21, ASCII)
            module_type = record_data[2:22].split(b'\x00', 1)[0].decode('ascii', errors='ignore').strip()
            module["module_type_name"] = module_type

            # Reserved (bytes 22-23)

            # Hardware version (bytes 24-25)
            # Byte 24: Version info (nibbles contain major.minor)
            # Byte 25: Additional version info or decimal part
            if len(record_data) >= 26:
                hw_byte1 = record_data[24]
                hw_byte2 = record_data[25]

                # If byte 24 has version nibbles (non-zero)
                if hw_byte1 > 0:
                    hw_major = (hw_byte1 >> 4) & 0x0F
                    hw_minor = hw_byte1 & 0x0F
                    module["hardware_version"] = f"V{hw_major}.{hw_minor}"
                else:
                    # Byte 25 contains the version
                    module["hardware_version"] = f"V{hw_byte2}"

            # Firmware version (bytes 26-27)
            if len(record_data) >= 28:
                fw_byte1 = record_data[26]
                fw_byte2 = record_data[27]

                # Check if bytes contain actual version data (not spaces 0x20)
                if fw_byte1 == 0x20 or fw_byte1 == 0x00:
                    # No firmware version data in this field
                    module["firmware_version"] = "N/A"
                elif fw_byte2 > 0x0F:
                    # Byte 2 might be BCD or decimal patch version
                    # Format: V major.minor.patch where byte1 has nibbles, byte2 is decimal
                    fw_major = (fw_byte1 >> 4) & 0x0F
                    fw_minor = fw_byte1 & 0x0F
                    module["firmware_version"] = f"V{fw_major}.{fw_minor}.{fw_byte2}"
                else:
                    # Standard nibble format
                    fw_major = (fw_byte1 >> 4) & 0x0F
                    fw_minor = fw_byte1 & 0x0F
                    fw_patch = fw_byte2 & 0x0F
                    module["firmware_version"] = f"V{fw_major}.{fw_minor}.{fw_patch}"

            modules.append(module)

            # Use the first module (index 1) as the main CPU info
            if index == 1 and not info:
                info = module.copy()

        # If we have multiple modules, add them to the info
        if len(modules) > 1:
            info["modules"] = modules
        elif not info and modules:
            info = modules[0].copy()

        return info

