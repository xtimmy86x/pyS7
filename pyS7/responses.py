import struct
from typing import Any, Protocol, runtime_checkable

from .constants import DataType, ReturnCode
from .errors import ReadResponseError, WriteResponseError
from .item import Item
from .requests import ItemsMap


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

    def parse(self) -> tuple[int, int, int]:
        max_jobs_calling, max_jobs_called, pdu_size = struct.unpack_from(
            ">HHH", self.response, offset=21
        )
        return (max_jobs_calling, max_jobs_called, pdu_size)


class ReadResponse:
    def __init__(self, response: bytes, items: list[Item]) -> None:
        self.response = response
        self.items = items

    def parse(self) -> list[bool | int | float | str | tuple[bool | int | float, ...]]:
        return parse_read_response(bytes_response=self.response, items=self.items)


class ReadOptimizedResponse:
    def __init__(self, response: bytes, item_map: ItemsMap) -> None:
        self.responses: list[bytes] = [response]
        self.items_map = [item_map]

        self.n_messages = 1

    def __iadd__(self, other):  # type: ignore
        self.responses += other.responses
        self.items_map += other.items_map

        self.n_messages += 1

        return self

    def parse(self) -> list[bool | int | float | str | tuple[bool | int | float, ...]]:
        return parse_optimized_read_response(
            bytes_responses=self.responses, items_map=self.items_map
        )


class WriteResponse:
    def __init__(self, response: bytes, items: list[Item]) -> None:
        self.response: bytes = response
        self.items: list[Item] = items

    def parse(self) -> None:
        parse_write_response(bytes_response=self.response, items=self.items)


def parse_read_response(
    bytes_response: bytes, items: list[Item]
) -> list[bool | int | float | str | tuple[bool | int | float, ...]]:
    parsed_data: list[tuple[bool | int | float, ...]] = []
    offset = 21  # Response offset where data starts

    for i, item in enumerate(items):
        return_code = struct.unpack_from(">B", bytes_response, offset)[0]

        if ReturnCode(return_code) == ReturnCode.SUCCESS:
            offset += 4

            if item.data_type == DataType.BIT:
                data: Any = bool(bytes_response[offset])
                offset += item.size()
                # Skip fill byte
                offset += 0 if i == len(items) - 1 else 1

            elif item.data_type == DataType.BYTE:
                data = struct.unpack_from(
                    f">{item.length * 'B'}", bytes_response, offset
                )
                offset += item.size()
                # Skip fill byte
                offset += 0 if i == len(items) - 1 else 1

            elif item.data_type == DataType.CHAR:
                data = bytes_response[offset : offset + item.length].decode()
                offset += item.size()
                # Skip byte if char length is odd
                offset += 0 if item.length % 2 == 0 else 1

            elif item.data_type == DataType.INT:
                data = struct.unpack_from(
                    f">{item.length * 'h'}", bytes_response, offset
                )
                offset += item.size()

            elif item.data_type == DataType.WORD:
                data = struct.unpack_from(
                    f">{item.length * 'H'}", bytes_response, offset
                )
                offset += item.size()

            elif item.data_type == DataType.DWORD:
                data = struct.unpack_from(
                    f">{item.length * 'I'}", bytes_response, offset
                )
                offset += item.size()

            elif item.data_type == DataType.DINT:
                data = struct.unpack_from(
                    f">{item.length * 'l'}", bytes_response, offset
                )
                offset += item.size()

            elif item.data_type == DataType.REAL:
                data = struct.unpack_from(
                    f">{item.length * 'f'}", bytes_response, offset
                )
                offset += item.size()

            else:
                raise ValueError(f"DataType: {item.data_type} not supported")

            parsed_data.append(data)

        else:
            raise ReadResponseError(f"{item}: {ReturnCode(return_code).name}")

    processed_data: list[bool | int | float | str | tuple[bool | int | float, ...]] = [
        data[0] if isinstance(data, tuple) and len(data) == 1 else data
        for data in parsed_data
    ]

    return processed_data


def parse_optimized_read_response(
    bytes_responses: list[bytes], items_map: list[ItemsMap]
) -> list[bool | int | float | str | tuple[bool | int | float, ...]]:
    parsed_data: list[tuple[int, str | tuple[bool | int | float, ...]]] = []

    for i, bytes_response in enumerate(bytes_responses):
        offset: int = 21  # Response offset where data starts

        for packed_item in items_map[i].keys():
            return_code = struct.unpack_from(">B", bytes_response, offset)[0]

            if ReturnCode(return_code) == ReturnCode.SUCCESS:
                offset += 4

                items: list[tuple[int, Item]] = items_map[i][packed_item]
                for idx, item in items:
                    if item.data_type == DataType.BIT:
                        if packed_item.data_type != DataType.BIT:
                            data: Any = bool(
                                (bytes_response[offset] >> 7 - item.bit_offset) & 0b1
                            )
                        else:
                            data = bool(bytes_response)

                    elif item.data_type == DataType.BYTE:
                        data = struct.unpack_from(
                            f">{(item.start - packed_item.start) * 'x'}{item.length * 'B'}",
                            bytes_response,
                            offset,
                        )

                    elif item.data_type == DataType.CHAR:
                        str_start = offset + (item.start - packed_item.start)
                        str_end = (
                            offset + (item.start - packed_item.start) + item.length
                        )
                        data = bytes_response[str_start:str_end].decode(
                            encoding="ascii"
                        )

                    elif item.data_type == DataType.INT:
                        data = struct.unpack_from(
                            f">{(item.start - packed_item.start) * 'x'}{item.length * 'h'}",
                            bytes_response,
                            offset,
                        )

                    elif item.data_type == DataType.WORD:
                        data = struct.unpack_from(
                            f">{(item.start - packed_item.start) * 'x'}{item.length * 'H'}",
                            bytes_response,
                            offset,
                        )

                    elif item.data_type == DataType.DWORD:
                        data = struct.unpack_from(
                            f">{(item.start - packed_item.start) * 'x'}{item.length * 'I'}",
                            bytes_response,
                            offset,
                        )

                    elif item.data_type == DataType.DINT:
                        data = struct.unpack_from(
                            f">{(item.start - packed_item.start) * 'x'}{item.length * 'l'}",
                            bytes_response,
                            offset,
                        )

                    elif item.data_type == DataType.REAL:
                        data = struct.unpack_from(
                            f">{(item.start - packed_item.start) * 'x'}{item.length * 'f'}",
                            bytes_response,
                            offset,
                        )

                    else:
                        raise ValueError(f"DataType: {item.data_type} not supported")

                    parsed_data.append((idx, data))

                offset += packed_item.length
                offset += 1 if packed_item.length % 2 != 0 else 0

            else:
                raise ReadResponseError(
                    f"{packed_item}: {ReturnCode(return_code).name}"
                )

    parsed_data.sort(key=lambda elem: elem[0])

    processed_data: list[bool | int | float | str | tuple[bool | int | float, ...]] = [
        data[0] if isinstance(data, tuple) and len(data) == 1 else data
        for (_, data) in parsed_data
    ]

    return processed_data


def parse_write_response(bytes_response: bytes, items: list[Item]) -> None:
    offset = 21  # Response offset where data starts

    for item in items:
        return_code = struct.unpack_from(">B", bytes_response, offset)[0]

        if ReturnCode(return_code) == ReturnCode.SUCCESS:
            offset += 1

        else:
            raise WriteResponseError(
                f"Impossible to write item {item} - {ReturnCode(return_code).name} "
            )
