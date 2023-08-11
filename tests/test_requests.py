import struct

import pytest

from pyS7.constants import (
    COTP_SIZE,
    MAX_PDU,
    TPKT_SIZE,
    WRITE_REQ_HEADER_SIZE,
    WRITE_REQ_PARAM_SIZE_ITEM,
    WRITE_REQ_PARAM_SIZE_NO_ITEMS,
    WRITE_RES_HEADER_SIZE,
    WRITE_RES_PARAM_SIZE,
    DataType,
    DataTypeData,
    DataTypeSize,
    MemoryArea,
)
from pyS7.errors import AddressError
from pyS7.item import Item
from pyS7.requests import (
    ConnectionRequest,
    PDUNegotiationRequest,
    ReadRequest,
    Value,
    WriteRequest,
    group_items,
    prepare_requests,
    prepare_write_requests_and_values,
)


def test_connection_request() -> None:
    rack = 0
    slot = 2
    connection_request = ConnectionRequest(rack=rack, slot=slot)

    expected_packet = bytearray([
        0x03, 0x00, 0x00, 0x16, 0x11, 0xe0, 0x00, 0x00, 0x00, 0x02,
        0x00, 0xc0, 0x01, 0x0a, 0xc1, 0x02, 0x01, 0x00, 0xc2, 0x02,
        0x01
    ])
    expected_packet.append(rack * 32 + slot)
    assert connection_request.request == expected_packet
    assert connection_request.serialize() == bytes(expected_packet)


def test_pdu_negotiation_request() -> None:
    pdu_negotiation_request = PDUNegotiationRequest(max_pdu=MAX_PDU)

    expected_packet = bytearray([
        0x03, 0x00, 0x00, 0x19, 0x02, 0xf0, 0x80, 0x32, 0x01, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0xf0, 0x00, 0x00,
        0x08, 0x00, 0x08, 0x03, 0xc0
    ])
    expected_packet[23:25] = MAX_PDU.to_bytes(2, byteorder="big")
    assert pdu_negotiation_request.request == expected_packet
    assert pdu_negotiation_request.serialize() == bytes(expected_packet)


def assert_read_header(packet: bytearray) -> None:
    assert packet[0] == 0x03
    assert packet[1] == 0x00
    assert packet[4] == 0x02
    assert packet[5] == 0xf0
    assert packet[6] == 0x80
    assert packet[7] == 0x32
    assert packet[8] == 0x01
    assert packet[9:11] == b'\x00\x00'
    assert packet[11:13] == b'\x00\x00'
    # packet[13:15] checked later
    # packet[15:17] checked later
    assert packet[17] == 0x04
    # packet[18] checked later

def assert_read_item(packet: bytearray, offset: int, item: Item) -> None:
    assert packet[offset] == 0x12
    assert packet[offset + 1] == 0x0a
    assert packet[offset + 2] == 0x10
    assert packet[offset + 3] == item.data_type.value.to_bytes(1, byteorder='big')[0]
    assert packet[offset + 4: offset + 6] == item.length.to_bytes(2, byteorder='big')
    assert packet[offset + 6: offset + 8] == item.db_number.to_bytes(2, byteorder='big')
    assert packet[offset + 8] == item.memory_area.value
    if item.data_type == DataType.BIT:
        assert packet[offset + 9: offset + 12] == (item.start * 8 + 7 - item.bit_offset).to_bytes(3, byteorder='big')
    else:
        assert packet[offset + 9: offset + 12] == (item.start * 8 + item.bit_offset).to_bytes(3, byteorder='big')

def test_read_request():
    items = [
        Item(MemoryArea.DB, 1, DataType.BIT, 0, 6, 1),
        Item(MemoryArea.DB, 1, DataType.INT, 30, 0, 1),
        Item(MemoryArea.DB, 1, DataType.INT, 32, 0, 1),
        Item(MemoryArea.DB, 1, DataType.INT, 34, 0, 1),
        Item(MemoryArea.DB, 1, DataType.INT, 36, 0, 1),
        Item(MemoryArea.DB, 1, DataType.INT, 38, 0, 1),
        Item(MemoryArea.DB, 1, DataType.REAL, 64, 0, 1),
        Item(MemoryArea.DB, 1, DataType.REAL, 68, 0, 1),
        Item(MemoryArea.DB, 1, DataType.REAL, 72, 0, 4),
        Item(MemoryArea.DB, 1, DataType.CHAR, 102, 0, 37),
    ]

    read_request = ReadRequest(items=items)

    packet = read_request.request

    assert_read_header(packet)

    assert packet[2:4] == len(packet).to_bytes(2, byteorder='big')
    assert packet[13:15] == (len(packet) - 17).to_bytes(2, byteorder='big')
    assert packet[18] == len(items)

    # Validate items
    offset = 19
    for item in items:
        assert_read_item(packet, offset, item)
        offset += 12

def assert_write_header(packet: bytearray) -> None:
    assert packet[0] == 0x03
    assert packet[1] == 0x00
    assert packet[4] == 0x02
    assert packet[5] == 0xf0
    assert packet[6] == 0x80
    assert packet[7] == 0x32
    assert packet[8] == 0x01
    assert packet[9:11] == b'\x00\x00'
    assert packet[11:13] == b'\x00\x00'
    # packet[13:15] checked later
    # packet[15:17] checked later
    assert packet[17] == 0x05
    # packet[18] checked later

def assert_write_item(packet: bytearray, offset: int, item: Item) -> None:
    assert packet[offset] == 0x12
    assert packet[offset + 1] == 0x0a
    assert packet[offset + 2] == 0x10
    if item.data_type == DataType.BIT:
        assert packet[offset + 3] == DataType.BIT.value.to_bytes(1, byteorder='big')[0]
    else:
        assert packet[offset + 3] == DataType.BYTE.value.to_bytes(1, byteorder='big')[0]
    assert packet[offset + 4: offset + 6] == item.size().to_bytes(2, byteorder="big")
    assert packet[offset + 6: offset + 8] == item.db_number.to_bytes(2, byteorder="big")
    assert packet[offset + 8] == item.memory_area.value.to_bytes(1, byteorder='big')[0]
    if item.data_type == DataType.BIT:
        assert packet[offset + 9: offset + 12] == (item.start * 8 + 7 - item.bit_offset).to_bytes(3, byteorder='big')
    else:
        assert packet[offset + 9: offset + 12] == (item.start * 8 + item.bit_offset).to_bytes(3, byteorder='big')

# TODO
def assert_write_data(packet: bytearray, offset: int, item: Item, value: Value) -> None:
    # assert packet[offset-2:offset+10] == 1
    assert packet[offset] == 0x00
    if item.data_type == DataType.BIT:
        assert packet[offset + 1] == DataTypeData.BIT.value
        assert packet[offset + 2: offset + 4] == (item.length * DataTypeSize[item.data_type]).to_bytes(2, byteorder="big")
    else:
        assert packet[offset + 1] == DataTypeData.BYTE_WORD_DWORD.value
        assert packet[offset + 2: offset + 4] == (item.length * DataTypeSize[item.data_type] * 8).to_bytes(2, byteorder="big")

    struct_fmts = {
        DataType.BIT:   "?",
        DataType.BYTE:  "B",
        DataType.INT:   "h",
        DataType.WORD:  "H",
        DataType.DWORD: "I",
        DataType.DINT:  "l",
        DataType.REAL:  "f",
    }

    if item.data_type in struct_fmts.keys():
        if isinstance(value, tuple):
            assert packet[offset + 4 : offset + 4 + item.size()] == struct.pack(f">{item.length*struct_fmts[item.data_type]}", *value)
        else:
            assert packet[offset + 4 : offset + 4 + item.size()] == struct.pack(f">{struct_fmts[item.data_type]}", value)

# TODO: to be finished
def test_write_request() -> None:
    items: list[Item] = [
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=2, bit_offset=5, length=1),
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=1, bit_offset=7, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=2, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=3, length=1),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=4, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=3),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.WORD, start=12, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.WORD, start=14, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.DWORD, start=18, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.DWORD, start=22, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.DINT, start=30, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.DINT, start=34, bit_offset=0, length=3),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.OUTPUT, db_number=0, data_type=DataType.CHAR, start=0, bit_offset=0, length=31),
    ]

    # Mock up values
    values = [
        True,
        False,
        True,
        True,
        127,
        (250, 251),
        1,
        2,
        (3, 4, 5),
        10,
        (11, 12),
        8000,
        (8001, 8002),
        16000,
        (16001, 16002, 16003),
        3.14,
        (6.28, 9.42),
        "a"*31
    ]

    write_request = WriteRequest(items=items, values=values)

    packet = write_request.request

    assert_write_header(packet=packet)

    # TODO
    # assert packet[2:4] == len(packet).to_bytes(2, byteorder='big')
    # assert packet[13:15] == (len(packet) - 17).to_bytes(2, byteorder='big')
    # assert packet[18] == len(items)

    # Validate items
    offset = 19
    for item in items:
        assert_write_item(packet, offset, item)
        offset += 12

    # Validate data
    for i, item in enumerate(items):
        assert item == item
        assert_write_data(packet, offset, item, values[i])
        offset += 4 + item.size()

        # Assert for fill byte
        if item.data_type == DataType.BIT and i < len(items) - 1:
            assert packet[offset] == 0
            offset += 1

        # Lenght must be even
        if len(packet[:offset]) % 2 == 0 and i < len(items) - 1:
            # assert packet[offset-10:offset] == 0
            assert packet[offset] == 0
            offset += 1

def test_group_items() -> None:

    # Mock up items for testing
    items: list[Item] = [
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=2, bit_offset=5, length=1),
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=1, bit_offset=7, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=2, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=3, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=4, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=3),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=2),
    ]

    expected_groups: dict[Item, list[Item]] = {
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BYTE, start=1, bit_offset=0, length=2): [
            (1, Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=1, bit_offset=7, length=1)),
            (0, Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=2, bit_offset=5, length=1)),
        ],
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BYTE, start=10, bit_offset=0, length=1): [
            (2, Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=2, length=1)),
            (3, Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=3, length=1)),
        ],
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.BYTE, start=4, bit_offset=0, length=8): [
            (4, Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=4, bit_offset=0, length=1)),
            (5, Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=1)),
            (6, Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=3)),
        ],
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1): [
            (7, Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1)),
        ],
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=1): [
            (8, Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=1)),
        ],
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=6): [
            (10, Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=2)),
            (9, Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=2)),
        ],
    }

    # group_items expect an ordered sequence of Item
    groups = group_items(items=items, pdu_size=240)

    assert expected_groups == groups

def test_prepare_request() -> None:

    # Mock up items for testing
    items: list[Item] = [
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=2, bit_offset=5, length=1),
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=1, bit_offset=7, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=2, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=3, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=4, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=3),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.DB, db_number=3, data_type=DataType.CHAR, start=0, bit_offset=0, length=110),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.CHAR, start=0, bit_offset=0, length=25),
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.REAL, start=20, bit_offset=0, length=10),
    ]

    expected_requests = [
        [
            Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=2, bit_offset=5, length=1),
            Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=1, bit_offset=7, length=1),
            Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=2, length=1),
            Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=3, length=1),
            Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=4, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=3),
            Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=2),
            Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=2),
            Item(memory_area=MemoryArea.DB, db_number=3, data_type=DataType.CHAR, start=0, bit_offset=0, length=110),
        ],
        [
            Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.CHAR, start=0, bit_offset=0, length=25),
            Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.REAL, start=20, bit_offset=0, length=10),
        ]
    ]

    requests = prepare_requests(items=items, max_pdu=240)

    assert len(expected_requests) == len(requests)
    for i in range(len(requests)):
        assert expected_requests[i] == requests[i]

def test_prepare_request_exception() -> None:
    pdu_size = 240
    items = [
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=0, bit_offset=0, length=250),
    ]
    with pytest.raises(AddressError):
        _, _ = prepare_requests(items=items, max_pdu=pdu_size)


def test_prepare_write_request() -> None:

    pdu_size = 240
    # Mock up items for testing
    items: list[Item] = [
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=2, bit_offset=5, length=1),
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=1, bit_offset=7, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=2, length=1),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=3, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=4, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=3),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=1),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=2),
        Item(memory_area=MemoryArea.DB, db_number=3, data_type=DataType.CHAR, start=0, bit_offset=0, length=110),
        Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.CHAR, start=0, bit_offset=0, length=25),
        Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.REAL, start=20, bit_offset=0, length=10),
    ]

    # Mock up values
    values = [
        True,
        False,
        True,
        True,
        1,
        2,
        (3, 4, 5),
        3.14,
        6.28,
        (127, 128),
        (250, 251),
        "a" * 110,
        "b" * 25,
        (1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0)
    ]

    expected_requests = [
        [
            Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=2, bit_offset=5, length=1),
            Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.BIT, start=1, bit_offset=7, length=1),
            Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=2, length=1),
            Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.BIT, start=10, bit_offset=3, length=1),
            Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=4, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.DB, db_number=23, data_type=DataType.INT, start=6, bit_offset=0, length=3),
            Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=40, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=60, bit_offset=0, length=1),
            Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=20, bit_offset=0, length=2),
            Item(memory_area=MemoryArea.INPUT, db_number=0, data_type=DataType.BYTE, start=16, bit_offset=0, length=2),
        ],
        [
            Item(memory_area=MemoryArea.DB, db_number=3, data_type=DataType.CHAR, start=0, bit_offset=0, length=110),
            Item(memory_area=MemoryArea.DB, db_number=2, data_type=DataType.CHAR, start=0, bit_offset=0, length=25),
        ],
        [
            Item(memory_area=MemoryArea.DB, db_number=1, data_type=DataType.REAL, start=20, bit_offset=0, length=10),
        ]
    ]

    expected_value_requests = [
        [
            True,
            False,
            True,
            True,
            1,
            2,
            (3, 4, 5),
            3.14,
            6.28,
            (127, 128),
            (250, 251),
        ],
        [
            "a" * 110,
            "b" * 25,
        ],
        [
            (1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0)
        ]
    ]

    requests, requests_values = prepare_write_requests_and_values(items=items, values=values, max_pdu=pdu_size)

    assert len(expected_requests) == len(requests)
    assert len(expected_value_requests) == len(requests_values)

    for i in range(len(requests)):
        assert expected_requests[i] == requests[i]

        # We want to assert the bytes length is < max_pdu
        WRITE_REQ_OVERHEAD = TPKT_SIZE + COTP_SIZE + WRITE_REQ_HEADER_SIZE + \
            WRITE_REQ_PARAM_SIZE_NO_ITEMS  # 3 + 4 + 10 + 2
        WRITE_RES_OVERHEAD = TPKT_SIZE + COTP_SIZE + \
            WRITE_RES_HEADER_SIZE + WRITE_RES_PARAM_SIZE  # 3 + 4 + 12 + 2

        assert WRITE_REQ_OVERHEAD + sum([WRITE_REQ_PARAM_SIZE_ITEM + 4 + elem.size() + elem.length % 2  for elem in requests[i]]) < pdu_size
        assert WRITE_RES_OVERHEAD + sum([1 for _ in range(len(items))]) < pdu_size

    for i in range(len(requests_values)):
        assert expected_value_requests[i] == requests_values[i]

def test_prepare_write_request_exception() -> None:
    pdu_size = 240
    items = [
        Item(memory_area=MemoryArea.MERKER, db_number=0, data_type=DataType.REAL, start=0, bit_offset=0, length=200),
    ]
    values = [
        tuple([0.1] * 200)
    ]

    with pytest.raises(AddressError):
        _, _ = prepare_write_requests_and_values(items=items, values=values, max_pdu=pdu_size)
