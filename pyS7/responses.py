import struct
from typing import Any, List, Protocol, Tuple, Union, runtime_checkable

from .constants import READ_RES_OVERHEAD, WRITE_RES_OVERHEAD, DataType, ReturnCode
from .errors import S7ReadResponseError, S7WriteResponseError
from .requests import TagsMap, Value
from .tag import S7Tag


@runtime_checkable
class Response(Protocol):
    def parse(self) -> Any:
        ...


class ConnectionResponse:
    def __init__(self, response: bytes) -> None:
        self.response = response

    def parse(self) -> Any:
        ...


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


def parse_read_response(bytes_response: bytes, tags: List[S7Tag]) -> List[Value]:
    parsed_data: List[Tuple[Union[bool, int, float], ...]] = []
    offset = READ_RES_OVERHEAD  # Response offset where data starts

    for i, tag in enumerate(tags):
        return_code = struct.unpack_from(">B", bytes_response, offset)[0]

        if ReturnCode(return_code) == ReturnCode.SUCCESS:
            offset += 4

            if tag.data_type == DataType.BIT:
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

            else:
                raise ValueError(f"DataType: {tag.data_type} not supported")

            parsed_data.append(data)

        else:
            raise S7ReadResponseError(f"{tag}: {ReturnCode(return_code).name}")

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
    ReturnCodeSuccess = ReturnCode.SUCCESS

    # Map DataType -> struct format char (always big-endian with '>')
    fmt_map = {
        DataType.BYTE: "B",
        DataType.INT: "h",
        DataType.WORD: "H",
        DataType.DWORD: "I",
        DataType.DINT: "l",
        DataType.REAL: "f",
    }

    for i, bytes_response in enumerate(bytes_responses):
        mv = memoryview(bytes_response)  # zero-copy access to bytes
        offset = READ_RES_OVERHEAD

        # Iterate over packed tags inside this response
        for packed_tag, tags in tags_map[i].items():
            # 1 byte return code (just read directly from memoryview)
            return_code = mv[offset]
            if ReturnCode(return_code) != ReturnCodeSuccess:
                raise S7ReadResponseError(f"{packed_tag}: {ReturnCode(return_code).name}")

            # Response header is 4 bytes (status + 3 length bytes)
            offset += 4
            base_off = offset  # start of actual data

            # Iterate through the unpacked tags inside this packed block
            for idx, tag in tags:
                rel = tag.start - packed_tag.start
                abs_off = base_off + rel
                dt = tag.data_type

                if dt == DataType.BIT:
                    data_byte = mv[abs_off]
                    value: Value = bool((data_byte >> tag.bit_offset) & 0b1)

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

        if ReturnCode(return_code) == ReturnCode.SUCCESS:
            offset += 1

        else:
            raise S7WriteResponseError(
                f"Impossible to write tag {tag} - {ReturnCode(return_code).name} "
            )
