from pyS7.constants import (
    COTP_SIZE,
    MAX_PDU,
    TPKT_SIZE,
    WRITE_REQ_HEADER_SIZE,
    WRITE_REQ_PARAM_SIZE_NO_ITEMS,
    WRITE_RES_HEADER_SIZE,
    WRITE_RES_PARAM_SIZE,
    DataType,
    MemoryArea,
)
from pyS7.item import Item
from pyS7.requests import (
    ConnectionRequest,
    PDUNegotiationRequest,
    ReadRequest,
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
    # assert packet[13:15] == b'\x00\x0e'
    # assert packet[15:17] == b'\x00\x00'
    assert packet[17] == 0x04
    # assert packet[18] == 0x01

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

# TODO
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
    # assert packet[13:15] == b'\x00\x0e'
    # assert packet[15:17] == b'\x00\x00'
    assert packet[17] == 0x05
    # assert packet[18] == 0x01

# TODO: to be finished
def test_write_request() -> None:
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
    ]

    write_request = WriteRequest(items=items, values=values)

    packet = write_request.request

    assert_write_header(packet=packet)

    # TODO
    # assert packet[2:4] == len(packet).to_bytes(2, byteorder='big')
    # assert packet[13:15] == (len(packet) - 17).to_bytes(2, byteorder='big')
    # assert packet[18] == len(items)

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

# TODO
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

        # TODO: We want to assert the bytes length is < max_pdu
        TPKT_SIZE + COTP_SIZE + WRITE_REQ_HEADER_SIZE + \
            WRITE_REQ_PARAM_SIZE_NO_ITEMS  # 3 + 4 + 10 + 2
        TPKT_SIZE + COTP_SIZE + \
            WRITE_RES_HEADER_SIZE + WRITE_RES_PARAM_SIZE  # 3 + 4 + 12 + 2


        # assert WRITE_REQ_OVERHEAD + sum([elem.size() + for elem in requests[i]]) == None

    for i in range(len(requests_values)):
        assert expected_value_requests[i] == requests_values[i]
