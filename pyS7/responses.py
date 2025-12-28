import struct
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

from .constants import READ_RES_OVERHEAD, WRITE_RES_OVERHEAD, DataType, ReturnCode
from .errors import S7ReadResponseError, S7WriteResponseError
from .requests import TagsMap, Value
from .tag import S7Tag

COTP_CONNECTION_CONFIRM = 0xD0

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

        version, reserved, tpkt_length = struct.unpack_from(">BBH", self.response, offset=0
        )
        if version != 0x03:
            raise ValueError("Unsupported TPKT version in connection response")

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

        is_success = pdu_type == COTP_CONNECTION_CONFIRM

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

    def __iadd__(self, other):  # type: ignore
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
    try:
        return ReturnCode(return_code).name
    except ValueError:
        return f"UNKNOWN_RETURN_CODE_0x{return_code:02X}"
    

def parse_read_response(bytes_response: bytes, tags: List[S7Tag]) -> List[Value]:
    parsed_data: List[Tuple[Union[bool, int, float], ...]] = []
    offset = READ_RES_OVERHEAD  # Response offset where data starts

    for i, tag in enumerate(tags):
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
            # 1 byte return code (just read directly from memoryview)
            return_code = mv[offset]
            if return_code != ReturnCodeSuccess:
                raise S7ReadResponseError(
                    f"{packed_tag}: {_return_code_name(return_code)}"
                )

            # Response header is 4 bytes (status + 3 length bytes)
            offset += 4
            base_off = offset  # start of actual data

            # Iterate through the unpacked tags inside this packed block
            for idx, tag in tags:
                rel = tag.start - packed_tag.start
                abs_off = base_off + rel
                dt = tag.data_type

                if dt == DataType.BIT:
                    # Check if this is a packed BIT tag (when the packed_tag is a BYTE)
                    # or an individual BIT tag (when the packed_tag is also a BIT)
                    if packed_tag.data_type == DataType.BYTE:
                        # This BIT tag was packed into a BYTE read - extract specific bit
                        data_byte = mv[abs_off]
                        from . import extract_bit_from_byte
                        value: Value = extract_bit_from_byte(data_byte, tag.bit_offset)
                    else:
                        # This is an individual BIT tag - PLC returns bit value directly
                        # Process the same as non-optimized reads
                        data_byte = mv[abs_off]
                        value: Value = bool(data_byte)

                elif dt == DataType.CHAR:
                    # Slice without copy until decoding
                    str_end = abs_off + tag.length
                    value = mv[abs_off:str_end].tobytes().decode("ascii")

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
            offset += packed_tag.length + (packed_tag.length & 1)

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
        # To read bit 2 from DB1.DBB0 when individual bit reads fail:
        # 1. Read the byte: client.read(["DB1,B0"])  # Returns [byte_value]
        # 2. Extract the bit: extract_bit_from_byte(byte_value, 2)
    """
    if not 0 <= bit_offset <= 7:
        raise ValueError("bit_offset must be between 0 and 7")
    if not 0 <= byte_value <= 255:
        raise ValueError("byte_value must be between 0 and 255")
    
    return bool((byte_value >> bit_offset) & 1)
