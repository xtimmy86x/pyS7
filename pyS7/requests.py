import struct
from typing import Protocol, Sequence, runtime_checkable

from .constants import (
    COTP_SIZE,
    MAX_READ_ITEMS,
    MAX_WRITE_ITEMS,
    READ_REQ_HEADER_SIZE,
    READ_REQ_PARAM_SIZE_ITEM,
    READ_REQ_PARAM_SIZE_NO_ITEMS,
    TPKT_SIZE,
    WRITE_REQ_HEADER_SIZE,
    WRITE_REQ_PARAM_SIZE_ITEM,
    WRITE_REQ_PARAM_SIZE_NO_ITEMS,
    WRITE_RES_HEADER_SIZE,
    WRITE_RES_PARAM_SIZE,
    DataType,
    DataTypeData,
    DataTypeSize,
    Function,
)
from .item import Item

Value = bool | int | float | str | tuple[bool | int | float, ...]

@runtime_checkable
class Request(Protocol):
    request: bytearray

    def serialize(self) -> bytes:
        return bytes(self.request)


class ConnectionRequest(Request):
    def __init__(self, rack: int, slot: int) -> None:
        self.request = self.__prepare_packet(rack=rack, slot=slot)

    def __prepare_packet(self, rack: int, slot: int) -> bytearray:

        packet = bytearray()

        packet.extend(b'\x03')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x16')
        packet.extend(b'\x11')
        packet.extend(b'\xe0')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x02')
        packet.extend(b'\x00')
        packet.extend(b'\xc0')
        packet.extend(b'\x01')
        packet.extend(b'\x0a')
        packet.extend(b'\xc1')
        packet.extend(b'\x02')
        packet.extend(b'\x01')
        packet.extend(b'\x00')
        packet.extend(b'\xc2')
        packet.extend(b'\x02')
        packet.extend(b'\x01')
        packet.extend(b'\x02')

        # Rack and Slot
        packet[21] = rack * 32 + slot

        return packet


class PDUNegotiationRequest(Request):
    def __init__(self, max_pdu: int) -> None:
        self.request = self.__prepare_packet(max_pdu=max_pdu)

    def __prepare_packet(self, max_pdu: int) -> bytearray:

        packet = bytearray()

        packet.extend(b'\x03')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x19')

        packet.extend(b'\x02')
        packet.extend(b'\xf0')
        packet.extend(b'\x80')

        packet.extend(b'\x32')
        packet.extend(b'\x01')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x08')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\xf0')
        packet.extend(b'\x00')
        packet.extend(b'\x00')
        packet.extend(b'\x08')
        packet.extend(b'\x00')
        packet.extend(b'\x08')
        packet.extend(b'\x03')
        packet.extend(b'\xc0')

        packet[23:25] = max_pdu.to_bytes(2, byteorder="big")

        return packet


ItemsMap = dict[Item, list[tuple[int, Item]]]


def group_items(items: list[Item], pdu_size: int) -> ItemsMap:

    sorted_items = sorted(enumerate(items), key=lambda elem: (
        elem[1].memory_area.value, elem[1].db_number, elem[1].start))

    groups = {}

    for i, (idx, item) in enumerate(sorted_items):

        if i == 0:
            groups[item] = [(idx, item)]
            previous_item = item
        else:
            if previous_item.memory_area == item.memory_area and \
                    previous_item.db_number == item.db_number and \
                    item.start - (previous_item.start + previous_item.size()) < READ_REQ_PARAM_SIZE_ITEM and \
                    item.size() + READ_REQ_HEADER_SIZE + READ_REQ_PARAM_SIZE_NO_ITEMS + READ_REQ_PARAM_SIZE_ITEM < pdu_size:

                new_start = previous_item.start
                new_length = max(previous_item.start + previous_item.size(),
                                 item.start + item.size()) - previous_item.start

                new_item = Item(memory_area=previous_item.memory_area,
                                db_number=previous_item.db_number,
                                data_type=DataType.BYTE,
                                start=new_start,
                                bit_offset=0,
                                length=new_length)

                tracked_items = groups.pop(previous_item)
                # Update items_map to point to new item
                groups[new_item] = tracked_items + [(idx, item)]
                previous_item = new_item

            else:
                groups[item] = [(idx, item)]
                previous_item = item

    return groups


def ungroup(items_map: ItemsMap) -> list[Item]:

    original_items = []

    for original_items in items_map.values():
        original_items.extend(original_items)

    original_items.sort(key=lambda elem: elem[0])
    return [item for (_, item) in original_items]


def prepare_requests(items: list[Item], max_pdu: int) -> list[list[Item]]:
    requests: list[list[Item]] = [[]]

    READ_REQ_OVERHEAD = TPKT_SIZE + COTP_SIZE + READ_REQ_HEADER_SIZE + \
        READ_REQ_PARAM_SIZE_NO_ITEMS  # 3 + 4 + 10 + 2
    READ_RES_OVERHEAD = 21  # it must be replaced with constant 4 + 3 + 12 + 2

    request_size = READ_REQ_OVERHEAD
    response_size = READ_RES_OVERHEAD

    for item in items:
        if READ_REQ_OVERHEAD + READ_REQ_PARAM_SIZE_ITEM + item.size() >= max_pdu or READ_RES_OVERHEAD + item.size() + 5 > max_pdu:
            raise Exception(
                f"{item} too big -> it cannot fit the size of the negotiated PDU ({max_pdu})")

        elif request_size + READ_REQ_PARAM_SIZE_ITEM < max_pdu and response_size + item.size() + 5 < max_pdu and len(requests[-1]) < MAX_READ_ITEMS:
            requests[-1].append(item)

            request_size += READ_REQ_PARAM_SIZE_ITEM
            response_size += item.size() + 5

        else:
            requests.append([item])
            request_size = READ_REQ_OVERHEAD + READ_REQ_PARAM_SIZE_ITEM
            response_size = READ_RES_OVERHEAD + item.size() + 5

    return requests

def prepare_write_requests_and_values(items: Sequence[Item], values: Sequence[Value], max_pdu: int) -> tuple[list[list[Item]], list[list[Value]]]:
    requests: list[list[Item]] = [[]]
    requests_values: list[list[Value]] = [[]]

    WRITE_REQ_OVERHEAD = TPKT_SIZE + COTP_SIZE + WRITE_REQ_HEADER_SIZE + \
        WRITE_REQ_PARAM_SIZE_NO_ITEMS  # 3 + 4 + 10 + 2
    WRITE_RES_OVERHEAD = TPKT_SIZE + COTP_SIZE + \
        WRITE_RES_HEADER_SIZE + WRITE_RES_PARAM_SIZE  # 3 + 4 + 12 + 2

    request_size = WRITE_REQ_OVERHEAD
    response_size = WRITE_RES_OVERHEAD

    for i, item in enumerate(items):

        if WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_ITEM + item.size() >= max_pdu or WRITE_RES_OVERHEAD + item.size() + 1 >= max_pdu:
            raise Exception(
                f"{item} too big -> it cannot fit the size of the negotiated PDU ({max_pdu})")

        elif request_size + WRITE_REQ_PARAM_SIZE_ITEM + 4 + item.size() + item.length % 2 < max_pdu and response_size + 1 < max_pdu and len(requests[-1]) < MAX_WRITE_ITEMS:
            requests[-1].append(item)
            requests_values[-1].append(values[i])

            request_size += WRITE_REQ_PARAM_SIZE_ITEM + 4 + item.size() + item.length % 2
            response_size += 1

        else:
            requests.append([item])
            requests_values.append([values[i]])

            request_size = WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_ITEM + 4 + item.size() + \
                item.length % 2
            response_size = WRITE_RES_OVERHEAD + 1

    return requests, requests_values


class ReadRequest(Request):

    def __init__(self, items: Sequence[Item]) -> None:

        self.items = items
        self.request = self.__prepare_packet(items=items)

    def __prepare_packet(self, items: Sequence[Item]) -> bytearray:

        packet = bytearray()

        # TPKT
        packet.extend(b'\x03')  # TPKT (version)
        packet.extend(b'\x00')  # Reserved (0x00)
        packet.extend(b'\x00\x1f')  # Length (will be filled later)

        # COTP (see RFC 2126)
        packet.extend(b'\x02')
        packet.extend(b'\xf0')
        packet.extend(b'\x80')

        # S7: HEADER
        packet.extend(b'\x32')  # S7 Protocol Id (0x32)
        packet.extend(b'\x01')  # Job (1)
        packet.extend(b'\x00\x00')  # Redundancy Identification (Reserved)
        packet.extend(b'\x00\x00')  # Protocol Data Unit Reference
        packet.extend(b'\x00\x0e')  # Parameter length
        packet.extend(b'\x00\x00')  # Data length

        # S7: PARAMETER
        packet.extend(b'\x04')  # Function 4 Read Var
        packet.extend(b'\x01')  # Item count

        # Item specification
        for item in items:
            packet.extend(b'\x12')  # Variable specification
            packet.extend(b'\x0a')  # Length of following address specification
            packet.extend(b'\x10')  # Syntax ID: S7ANY (0x10)
            packet.extend(item.data_type.value.to_bytes(
                1, byteorder='big'))  # Transport size
            packet.extend(item.length.to_bytes(2, byteorder="big"))  # Length
            packet.extend(item.db_number.to_bytes(
                2, byteorder='big'))  # DB Number
            packet.extend(item.memory_area.value.to_bytes(
                1, byteorder='big'))  # Area Code (0x84 for DB)
            if item.data_type == DataType.BIT:
                # Address (start * 8 + bit offset)
                packet.extend(
                    (item.start * 8 + 7 - item.bit_offset).to_bytes(3, byteorder="big"))
            else:
                packet.extend(
                    (item.start * 8 + item.bit_offset).to_bytes(3, byteorder="big"))

        # Update parameter length
        packet[13:15] = (len(packet) - 17).to_bytes(2, byteorder='big')

        # Update item count
        packet[18] = len(items)

        # Update length
        packet[2:4] = len(packet).to_bytes(2, byteorder='big')

        return packet


class WriteRequest(Request):

    def __init__(self, items: Sequence[Item], values: Sequence[Value]) -> None:

        self.items = items
        self.values = values

        self.request = self.__prepare_packet(items=items, values=values)

    def __prepare_packet(self, items: Sequence[Item], values: Sequence[Value]) -> bytearray:
        packet = bytearray()

        # TPKT
        packet.extend(b'\x03')  # TPKT (version)
        packet.extend(b'\x00')  # Reserved (0x00)
        packet.extend(b'\x00\x1f')  # Length (will be filled later)

        # COTP (see RFC 2126)
        packet.extend(b'\x02')
        packet.extend(b'\xf0')
        packet.extend(b'\x80')

        # S7: HEADER
        packet.extend(b'\x32')  # S7 Protocol Id (0x32)
        packet.extend(b'\x01')  # Job (1)
        packet.extend(b'\x00\x00')  # Redundancy Identification (Reserved)
        packet.extend(b'\x00\x00')  # Protocol Data Unit Reference
        packet.extend(b'\x00\x0e')  # Parameter length
        packet.extend(b'\x00\x00')  # Data length

        tpkt_cotp_header_length = len(packet)  # 17

        # S7: PARAMETER
        packet.extend(Function.WRITE_VAR.value.to_bytes(
            1, byteorder="big"))  # Function Write Var
        packet.extend(b'\x01')  # Item count

        # Item specification
        for item in items:
            packet.extend(b'\x12')  # Variable specification
            packet.extend(b'\x0a')  # Length of following address specification
            packet.extend(b'\x10')  # Syntax ID: S7ANY (0x10)

            if item.data_type == DataType.BIT:
                packet.extend(DataType.BIT.value.to_bytes(
                    1, byteorder='big'))  # Transport size
            else:
                # Transport size, write everything as bytes
                packet.extend(DataType.BYTE.value.to_bytes(1, byteorder='big'))

            # Length (item length * size of data type)
            packet.extend(
                (item.length * DataTypeSize[item.data_type]).to_bytes(2, byteorder="big"))
            packet.extend(item.db_number.to_bytes(
                2, byteorder='big'))  # DB Number
            packet.extend(item.memory_area.value.to_bytes(
                1, byteorder='big'))  # Area Code (0x84 for DB)

            if item.data_type == DataType.BIT:
                # Address (start * 8 + bit offset)
                packet.extend(
                    (item.start * 8 + 7 - item.bit_offset).to_bytes(3, byteorder="big"))
            else:
                packet.extend(
                    (item.start * 8 + item.bit_offset).to_bytes(3, byteorder="big"))

        parameter_length = len(packet) - tpkt_cotp_header_length

        # S7 : DATA
        for i, item in enumerate(items):

            packet.extend(b'\x00')  # Reserved (0x00)

            data = values[i]

            if item.data_type == DataType.BIT:
                transport_size = DataTypeData.BIT
                new_length = item.length * DataTypeSize[item.data_type]
                packed_data = struct.pack(">?", data)

            elif item.data_type == DataType.BYTE:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = item.length * DataTypeSize[item.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{item.length * 'B'}", *data)
                else:
                    packed_data = struct.pack(">B", data)

            elif item.data_type == DataType.CHAR:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = item.length * DataTypeSize[item.data_type] * 8
                assert isinstance(data, str)
                packed_data = data.encode(encoding="ascii")

            elif item.data_type == DataType.INT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = item.length * DataTypeSize[item.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{item.length * 'h'}", *data)
                else:
                    packed_data = struct.pack(">h", data)

            elif item.data_type == DataType.WORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = item.length * DataTypeSize[item.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{item.length * 'H'}", *data)
                else:
                    packed_data = struct.pack(">H", data)

            elif item.data_type == DataType.DWORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = item.length * DataTypeSize[item.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{item.length * 'I'}", *data)
                else:
                    packed_data = struct.pack(">I", data)

            elif item.data_type == DataType.DINT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = item.length * DataTypeSize[item.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{item.length * 'l'}", *data)
                else:
                    packed_data = struct.pack(">l", data)

            elif item.data_type == DataType.REAL:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = item.length * DataTypeSize[item.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{item.length * 'f'}", *data)
                else:
                    packed_data = struct.pack(">f", data)

            else:
                # We should never enter here
                raise ValueError("")

            # Data transport size - This is not the DataType
            packet.extend(transport_size.value.to_bytes(1, byteorder="big"))
            packet.extend(new_length.to_bytes(2, byteorder="big"))
            packet.extend(packed_data)

            data_item_length = 1 + 1 + 2 + \
                item.length * DataTypeSize[item.data_type]

            if item.data_type == DataType.BIT and i < len(items) - 1:
                packet.extend(b"\x00")

            if len(packet) % 2 == 0 and i < len(items) - 1:
                data_item_length += 1
                packet.extend(b"\x00")

        data_length = len(packet) - parameter_length - tpkt_cotp_header_length

        # Update parameter length
        packet[13:15] = (parameter_length).to_bytes(2, byteorder='big')

        # Update data length
        packet[15:17] = (data_length).to_bytes(2, byteorder="big")

        # Update item count
        packet[18] = len(items)

        # Update packet length
        packet[2:4] = len(packet).to_bytes(2, byteorder='big')

        return packet
