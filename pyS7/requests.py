import struct
from typing import Dict, List, Protocol, Sequence, Tuple, Union, runtime_checkable

from pyS7.errors import S7AddressError

from .constants import (
    MAX_READ_TAGS,
    MAX_WRITE_TAGS,
    READ_REQ_OVERHEAD,
    READ_REQ_PARAM_SIZE_TAG,
    READ_RES_OVERHEAD,
    READ_RES_PARAM_SIZE_TAG,
    WRITE_REQ_OVERHEAD,
    WRITE_REQ_PARAM_SIZE_TAG,
    WRITE_RES_OVERHEAD,
    ConnectionType,
    DataType,
    DataTypeData,
    DataTypeSize,
    Function,
)
from .tag import S7Tag

TagsMap = Dict[S7Tag, List[Tuple[int, S7Tag]]]
Value = Union[bool, int, float, str, Tuple[Union[bool, int, float], ...]]


@runtime_checkable
class Request(Protocol):
    request: bytearray

    def serialize(self) -> bytes:
        return bytes(self.request)


class ConnectionRequest(Request):
    def __init__(self, rack: int, slot: int, connection_type: ConnectionType) -> None:
        self.request = self.__prepare_packet(
            rack=rack, slot=slot, connection_type=connection_type
        )

    def __prepare_packet(
        self, rack: int, slot: int, connection_type: ConnectionType
    ) -> bytearray:
        packet = bytearray()

        packet.extend(b"\x03")
        packet.extend(b"\x00")
        packet.extend(b"\x00")
        packet.extend(b"\x16")

        packet.extend(b"\x11")
        packet.extend(b"\xe0")
        packet.extend(b"\x00")

        packet.extend(b"\x00")
        packet.extend(b"\x00")
        packet.extend(b"\x02")
        packet.extend(b"\x00")
        packet.extend(b"\xc0")
        packet.extend(b"\x01")
        packet.extend(b"\x0a")
        packet.extend(b"\xc1")
        packet.extend(b"\x02")
        packet.extend(b"\x01")
        packet.extend(b"\x00")
        packet.extend(b"\xc2")
        packet.extend(b"\x02")
        packet.extend(b"\x01")
        packet.extend(b"\x02")

        # Connection type
        packet[20] = connection_type.value

        # Rack and Slot
        packet[21] = rack * 32 + slot

        return packet


class PDUNegotiationRequest(Request):
    """Request for negotiating the PDU size with the S7 device."""

    def __init__(self, max_pdu: int) -> None:
        self.request = self.__prepare_packet(max_pdu=max_pdu)

    def __prepare_packet(self, max_pdu: int) -> bytearray:
        packet = bytearray()

        # TPKT
        packet.extend(b"\x03")
        packet.extend(b"\x00")
        packet.extend(b"\x00\x19")

        # COTP (see RFC 2126)
        packet.extend(b"\x02")
        packet.extend(b"\xf0")
        packet.extend(b"\x80")

        # S7: HEADER
        packet.extend(b"\x32")  # S7 Protocol Id (0x32)
        packet.extend(b"\x01")
        packet.extend(b"\x00\x00")  # Redundancy Identification (Reserved)
        packet.extend(b"\x00\x00")  # Protocol Data Unit Reference
        packet.extend(b"\x00\x08")  # Parameter length
        packet.extend(b"\x00\x00")  # Data length

        # S7: PARAMETER
        packet.extend(b"\xf0")
        packet.extend(b"\x00")
        packet.extend(b"\x00")
        packet.extend(b"\x08")
        packet.extend(b"\x00")
        packet.extend(b"\x08")
        packet.extend(max_pdu.to_bytes(2, byteorder="big"))

        return packet


class ReadRequest(Request):
    """Request for reading data from an S7 device."""

    def __init__(self, tags: Sequence[S7Tag]) -> None:
        self.tags = tags
        self.request = self.__prepare_packet(tags=tags)

    def __prepare_packet(self, tags: Sequence[S7Tag]) -> bytearray:
        packet = bytearray()

        # TPKT
        packet.extend(b"\x03")  # TPKT (version)
        packet.extend(b"\x00")  # Reserved (0x00)
        packet.extend(b"\x00\x1f")  # Length (will be filled later)

        # COTP (see RFC 2126)
        packet.extend(b"\x02")
        packet.extend(b"\xf0")
        packet.extend(b"\x80")

        # S7: HEADER
        packet.extend(b"\x32")  # S7 Protocol Id (0x32)
        packet.extend(b"\x01")  # Job (1)
        packet.extend(b"\x00\x00")  # Redundancy Identification (Reserved)
        packet.extend(b"\x00\x00")  # Protocol Data Unit Reference
        packet.extend(b"\x00\x0e")  # Parameter length
        packet.extend(b"\x00\x00")  # Data length

        # S7: PARAMETER
        packet.extend(b"\x04")  # Function 4 Read Var
        packet.extend(b"\x01")  # tag count

        # S7Tag specification
        for tag in tags:
            packet.extend(b"\x12")  # Variable specification
            packet.extend(b"\x0a")  # Length of following address specification
            packet.extend(b"\x10")  # Syntax ID: S7ANY (0x10)
            packet.extend(
                tag.data_type.value.to_bytes(1, byteorder="big")
            )  # Transport size
            packet.extend(tag.length.to_bytes(2, byteorder="big"))  # Length
            packet.extend(tag.db_number.to_bytes(2, byteorder="big"))  # DB Number
            packet.extend(
                tag.memory_area.value.to_bytes(1, byteorder="big")
            )  # Area Code (0x84 for DB)
            if tag.data_type == DataType.BIT:
                # Address (start * 8 + bit offset)
                packet.extend(
                    (tag.start * 8 + 7 - tag.bit_offset).to_bytes(3, byteorder="big")
                )
            else:
                packet.extend(
                    (tag.start * 8 + tag.bit_offset).to_bytes(3, byteorder="big")
                )

        # Update parameter length
        packet[13:15] = (len(packet) - 17).to_bytes(2, byteorder="big")

        # Update tag count
        packet[18] = len(tags)

        # Update length
        packet[2:4] = len(packet).to_bytes(2, byteorder="big")

        return packet


class WriteRequest(Request):
    """Request for writing data to an S7 device."""

    def __init__(self, tags: Sequence[S7Tag], values: Sequence[Value]) -> None:
        self.tags = tags
        self.values = values

        self.request = self.__prepare_packet(tags=tags, values=values)

    def __prepare_packet(
        self, tags: Sequence[S7Tag], values: Sequence[Value]
    ) -> bytearray:
        packet = bytearray()

        # TPKT
        packet.extend(b"\x03")  # TPKT (version)
        packet.extend(b"\x00")  # Reserved (0x00)
        packet.extend(b"\x00\x1f")  # Length (will be filled later)

        # COTP (see RFC 2126)
        packet.extend(b"\x02")
        packet.extend(b"\xf0")
        packet.extend(b"\x80")

        # S7: HEADER
        packet.extend(b"\x32")  # S7 Protocol Id (0x32)
        packet.extend(b"\x01")  # Job (1)
        packet.extend(b"\x00\x00")  # Redundancy Identification (Reserved)
        packet.extend(b"\x00\x00")  # Protocol Data Unit Reference
        packet.extend(b"\x00\x0e")  # Parameter length
        packet.extend(b"\x00\x00")  # Data length

        tpkt_cotp_header_length = len(packet)  # 17

        # S7: PARAMETER
        packet.extend(
            Function.WRITE_VAR.value.to_bytes(1, byteorder="big")
        )  # Function Write Var
        packet.extend(b"\x01")  # tag count

        # S7Tag specification
        for tag in tags:
            packet.extend(b"\x12")  # Variable specification
            packet.extend(b"\x0a")  # Length of following address specification
            packet.extend(b"\x10")  # Syntax ID: S7ANY (0x10)

            if tag.data_type == DataType.BIT:
                packet.extend(
                    DataType.BIT.value.to_bytes(1, byteorder="big")
                )  # Transport size
            else:
                # Transport size, write everything as bytes
                packet.extend(DataType.BYTE.value.to_bytes(1, byteorder="big"))

            # Length (tag length * size of data type)
            packet.extend(
                (tag.length * DataTypeSize[tag.data_type]).to_bytes(2, byteorder="big")
            )
            packet.extend(tag.db_number.to_bytes(2, byteorder="big"))  # DB Number
            packet.extend(
                tag.memory_area.value.to_bytes(1, byteorder="big")
            )  # Area Code (0x84 for DB)

            if tag.data_type == DataType.BIT:
                # Address (start * 8 + bit offset)
                packet.extend(
                    (tag.start * 8 + 7 - tag.bit_offset).to_bytes(3, byteorder="big")
                )
            else:
                packet.extend(
                    (tag.start * 8 + tag.bit_offset).to_bytes(3, byteorder="big")
                )

        parameter_length = len(packet) - tpkt_cotp_header_length

        # S7 : DATA
        for i, tag in enumerate(tags):
            packet.extend(b"\x00")  # Reserved (0x00)

            data = values[i]

            if tag.data_type == DataType.BIT:
                transport_size = DataTypeData.BIT
                new_length = tag.length * DataTypeSize[tag.data_type]
                packed_data = struct.pack(">?", data)

            elif tag.data_type == DataType.BYTE:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'B'}", *data)
                else:
                    packed_data = struct.pack(">B", data)

            elif tag.data_type == DataType.CHAR:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                assert isinstance(data, str)
                packed_data = data.encode(encoding="ascii")

            elif tag.data_type == DataType.INT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'h'}", *data)
                else:
                    packed_data = struct.pack(">h", data)

            elif tag.data_type == DataType.WORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'H'}", *data)
                else:
                    packed_data = struct.pack(">H", data)

            elif tag.data_type == DataType.DWORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'I'}", *data)
                else:
                    packed_data = struct.pack(">I", data)

            elif tag.data_type == DataType.DINT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'l'}", *data)
                else:
                    packed_data = struct.pack(">l", data)

            elif tag.data_type == DataType.REAL:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'f'}", *data)
                else:
                    packed_data = struct.pack(">f", data)
            else:
                assert False, "Unreachable"

            # Data transport size - This is not the DataType
            packet.extend(transport_size.value.to_bytes(1, byteorder="big"))
            packet.extend(new_length.to_bytes(2, byteorder="big"))
            packet.extend(packed_data)

            data_tag_length = 1 + 1 + 2 + tag.length * DataTypeSize[tag.data_type]

            if tag.data_type == DataType.BIT and i < len(tags) - 1:
                packet.extend(b"\x00")

            if len(packet) % 2 == 0 and i < len(tags) - 1:
                data_tag_length += 1
                packet.extend(b"\x00")

        data_length = len(packet) - parameter_length - tpkt_cotp_header_length

        # Update parameter length
        packet[13:15] = (parameter_length).to_bytes(2, byteorder="big")

        # Update data length
        packet[15:17] = (data_length).to_bytes(2, byteorder="big")

        # Update tag count
        packet[18] = len(tags)

        # Update packet length
        packet[2:4] = len(packet).to_bytes(2, byteorder="big")

        return packet

def prepare_requests(tags: List[S7Tag], max_pdu: int) -> List[List[S7Tag]]:
    requests: List[List[S7Tag]] = [[]]

    cumulated_request_size = READ_REQ_OVERHEAD
    cumulated_response_size = READ_RES_OVERHEAD

    for tag in tags:
        tag_request_size = READ_REQ_PARAM_SIZE_TAG
        tag_response_size = READ_RES_PARAM_SIZE_TAG + tag.size()

        if (
            READ_REQ_OVERHEAD + tag_request_size >= max_pdu
            or READ_RES_OVERHEAD + tag_response_size > max_pdu
        ):
            # TODO: Improve error message by adding current tag size
            raise S7AddressError(
                f"{tag} too big -> it cannot fit the size of the negotiated PDU ({max_pdu})"
            )

        elif (
            cumulated_request_size + tag_request_size < max_pdu
            and cumulated_response_size + tag_response_size < max_pdu
            and len(requests[-1]) < MAX_READ_TAGS
        ):
            requests[-1].append(tag)

            cumulated_request_size += READ_REQ_PARAM_SIZE_TAG
            cumulated_response_size += READ_RES_PARAM_SIZE_TAG + tag.size()

        else:
            requests.append([tag])
            cumulated_request_size = READ_REQ_OVERHEAD + READ_REQ_PARAM_SIZE_TAG
            cumulated_response_size = (
                READ_RES_OVERHEAD + READ_RES_PARAM_SIZE_TAG + tag.size()
            )

    return requests


def prepare_optimized_requests(
    tags: List[S7Tag], max_pdu: int
) -> Tuple[List[List[S7Tag]], TagsMap]:
    requests: List[List[S7Tag]] = [[]]
    groups: TagsMap = {}

    cumulated_request_size = READ_REQ_OVERHEAD
    cumulated_response_size = READ_RES_OVERHEAD

    sorted_tags = sorted(
        enumerate(tags),
        key=lambda elem: (elem[1].memory_area.value, elem[1].db_number, elem[1].start),
    )

    for i, (idx, tag) in enumerate(sorted_tags):
        tag_request_size = READ_REQ_PARAM_SIZE_TAG
        tag_response_size = READ_RES_PARAM_SIZE_TAG + tag.size()

        # Handle too big tags
        if (
            READ_REQ_OVERHEAD + tag_request_size >= max_pdu
            or READ_RES_OVERHEAD + tag_response_size > max_pdu
        ):
            # TODO: Improve error message by adding current tag size
            raise S7AddressError(
                f"{tag} too big -> it cannot fit the size of the negotiated PDU ({max_pdu})"
            )

        if i == 0:
            requests[-1].append(tag)
            groups[tag] = [(idx, tag)]

            cumulated_request_size += tag_request_size
            cumulated_response_size += tag_response_size
        else:
            if (
                cumulated_request_size + tag_request_size < max_pdu
                and cumulated_response_size + tag_response_size < max_pdu
                and len(requests[-1]) < MAX_READ_TAGS
            ):
                previous_tag = requests[-1][-1]

                if (
                    cumulated_request_size + tag_response_size <= max_pdu
                    and cumulated_response_size + tag_response_size <= max_pdu
                    and previous_tag.memory_area == tag.memory_area
                    and previous_tag.db_number == tag.db_number
                    and tag.start - (previous_tag.start + previous_tag.size())
                    < READ_REQ_PARAM_SIZE_TAG
                ):
                    new_start = previous_tag.start
                    new_length = (
                        max(
                            previous_tag.start + previous_tag.size(),
                            tag.start + tag.size(),
                        )
                        - previous_tag.start
                    )

                    new_tag = S7Tag(
                        memory_area=previous_tag.memory_area,
                        db_number=previous_tag.db_number,
                        data_type=DataType.BYTE,
                        start=new_start,
                        bit_offset=0,
                        length=new_length,
                    )

                    tracked_tags = groups.pop(previous_tag)
                    # Update tags_map to point to new tag
                    groups[new_tag] = tracked_tags + [(idx, tag)]
                    requests[-1][-1] = new_tag

                    cumulated_request_size += 0
                    cumulated_response_size += new_tag.size() - previous_tag.size()

                else:
                    requests[-1].append(tag)
                    groups[tag] = [(idx, tag)]

                    cumulated_request_size += tag_request_size
                    cumulated_response_size += tag_response_size

            else:
                requests.append([tag])
                groups[tag] = [(idx, tag)]

                cumulated_request_size = READ_REQ_OVERHEAD + tag_request_size
                cumulated_response_size = READ_RES_OVERHEAD + tag_response_size

    return requests, groups


def prepare_write_requests_and_values(
    tags: Sequence[S7Tag], values: Sequence[Value], max_pdu: int
) -> Tuple[List[List[S7Tag]], List[List[Value]]]:
    requests: List[List[S7Tag]] = [[]]
    requests_values: List[List[Value]] = [[]]

    request_size = WRITE_REQ_OVERHEAD
    response_size = WRITE_RES_OVERHEAD

    for i, tag in enumerate(tags):
        if (
            WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag.size() >= max_pdu
            or WRITE_RES_OVERHEAD + tag.size() + 1 >= max_pdu
        ):
            raise S7AddressError(
                f"{tag} too big -> it cannot fit the size of the negotiated PDU ({max_pdu})"
            )

        elif (
            request_size + WRITE_REQ_PARAM_SIZE_TAG + 4 + tag.size() + tag.length % 2
            < max_pdu
            and response_size + 1 < max_pdu
            and len(requests[-1]) < MAX_WRITE_TAGS
        ):
            requests[-1].append(tag)
            requests_values[-1].append(values[i])

            request_size += WRITE_REQ_PARAM_SIZE_TAG + 4 + tag.size() + tag.length % 2
            response_size += 1

        else:
            requests.append([tag])
            requests_values.append([values[i]])

            request_size = (
                WRITE_REQ_OVERHEAD
                + WRITE_REQ_PARAM_SIZE_TAG
                + 4
                + tag.size()
                + tag.length % 2
            )
            response_size = WRITE_RES_OVERHEAD + 1

    return requests, requests_values
