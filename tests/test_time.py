import struct
from datetime import timedelta

import pytest

from pyS7._protocol import parse_tag_value
from pyS7.address_parser import map_address_to_tag
from pyS7.constants import S7ANY_DATA_TYPE, DataType, MemoryArea
from pyS7.errors import S7AddressError, S7ProtocolError
from pyS7.requests import ReadRequest, WriteRequest, prepare_write_requests_and_values
from pyS7.responses import parse_read_response
from pyS7.tag import S7Tag


def time_tag(length: int = 1) -> S7Tag:
    return S7Tag(MemoryArea.DB, 1, DataType.TIME, 100, 0, length)


def read_response(payload: bytes) -> bytes:
    return bytes(21) + b"\xff\x04" + (len(payload) * 8).to_bytes(2, "big") + payload


def test_data_type_values_and_s7any_mapping() -> None:
    assert {item.name: item.value for item in DataType} == {
        "BIT": 1,
        "BYTE": 2,
        "CHAR": 3,
        "WORD": 4,
        "INT": 5,
        "DWORD": 6,
        "DINT": 7,
        "REAL": 8,
        "STRING": 9,
        "WSTRING": 10,
        "USINT": 11,
        "SINT": 12,
        "TIME": 13,
        "LREAL": 31,
    }
    assert S7ANY_DATA_TYPE[DataType.TIME] == 0x07


def test_time_address_and_size() -> None:
    assert map_address_to_tag("db1,time100") == time_tag()
    assert time_tag().size() == 4
    assert time_tag(2).size() == 8
    for address in (
        "DB1,T0",
        "DB1,TIME",
        "DB1,TIME-1",
        "DB1,TIME100.0",
        "DB1,TIME100junk",
        "ITIME100",
        "ETIME100",
        "QTIME100",
        "ATIME100",
        "MTIME100",
    ):
        with pytest.raises(S7AddressError):
            map_address_to_tag(address)


def test_native_read_request_uses_time_element() -> None:
    packet = ReadRequest([time_tag()]).serialize()
    assert b"\x12\x0a\x10\x07\x00\x01\x00\x01\x84\x00\x03\x20" in packet


@pytest.mark.parametrize(
    "value, payload",
    [
        (timedelta(0), b"\0\0\0\0"),
        (timedelta(milliseconds=1), b"\0\0\0\1"),
        (timedelta(milliseconds=-1), b"\xff\xff\xff\xff"),
        (timedelta(seconds=1), b"\0\0\x03\xe8"),
        (timedelta(seconds=-1), b"\xff\xff\xfc\x18"),
        (timedelta(milliseconds=2_147_483_647), b"\x7f\xff\xff\xff"),
        (timedelta(milliseconds=-2_147_483_648), b"\x80\0\0\0"),
    ],
)
def test_time_write_and_read(value: timedelta, payload: bytes) -> None:
    packet = WriteRequest([time_tag()], [value]).serialize()
    assert packet[-4:] == payload
    assert packet[-8:-4] == b"\x00\x04\x00\x20"
    assert parse_read_response(read_response(payload), [time_tag()]) == [value]
    assert parse_tag_value(time_tag(), payload) == value


def test_time_array() -> None:
    values = (timedelta(milliseconds=-1), timedelta(seconds=1))
    payload = struct.pack(">2i", -1, 1000)
    assert WriteRequest([time_tag(2)], [values]).serialize()[-8:] == payload
    assert parse_read_response(read_response(payload), [time_tag(2)]) == [values]
    assert parse_tag_value(time_tag(2), payload) == values


@pytest.mark.parametrize(
    "value, error",
    [
        (timedelta(microseconds=1500), ValueError),
        (timedelta(microseconds=-1500), ValueError),
        (timedelta(milliseconds=2_147_483_648), ValueError),
        (timedelta(milliseconds=-2_147_483_649), ValueError),
        (1000, TypeError),
        (1.0, TypeError),
        ("T#1s", TypeError),
        (None, TypeError),
        (True, TypeError),
    ],
)
def test_invalid_time_write(value: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        prepare_write_requests_and_values([time_tag()], [value], 960)  # type: ignore[list-item]


def test_truncated_time_response_is_protocol_error() -> None:
    with pytest.raises(S7ProtocolError):
        parse_read_response(read_response(b"\0\0\0"), [time_tag()])
