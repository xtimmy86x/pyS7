"""Regress extended S7 STRING/CHAR bytes through the public client APIs."""

import asyncio
import inspect
import struct
from unittest.mock import AsyncMock, Mock

import pytest

from pyS7 import AsyncS7Client, S7Client
from pyS7.constants import (
    READ_RES_OVERHEAD,
    WRITE_REQ_OVERHEAD,
    WRITE_REQ_PARAM_SIZE_TAG,
    WRITE_RES_OVERHEAD,
    ConnectionState,
    DataType,
    MemoryArea,
)
from pyS7.errors import S7AddressError
from pyS7.requests import ReadRequest, WriteRequest
from pyS7.responses import _parse_string
from pyS7.tag import S7Tag


def string_tag(capacity: int = 26, start: int = 0) -> S7Tag:
    return S7Tag(MemoryArea.DB, 1013, DataType.STRING, start, 0, capacity)


class MemoryPLC:
    """Exchange raw read/write payloads, leaving all codecs under test."""

    def __init__(self) -> None:
        self.memory = bytearray(b"\xa5" * 1024)
        self.requests: list[ReadRequest | WriteRequest] = []

    def send(self, request: ReadRequest | WriteRequest) -> bytes:
        self.requests.append(request)
        if isinstance(request, ReadRequest):
            response = bytearray(READ_RES_OVERHEAD)
            for index, tag in enumerate(request.tags):
                payload = self.memory[tag.start : tag.start + tag.size()]
                response.extend(b"\xff\x04" + struct.pack(">H", len(payload) * 8))
                response.extend(payload)
                if index < len(request.tags) - 1 and len(payload) % 2:
                    response.append(0)
            return bytes(response)

        packet = request.serialize()
        offset = WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG * len(request.tags)
        for index, tag in enumerate(request.tags):
            length_bits = struct.unpack_from(">H", packet, offset + 2)[0]
            assert length_bits == tag.size() * 8
            offset += 4
            payload = packet[offset : offset + tag.size()]
            assert len(payload) == tag.size()
            self.memory[tag.start : tag.start + tag.size()] = payload
            offset += tag.size()
            if index < len(request.tags) - 1 and tag.size() % 2:
                offset += 1
        assert offset == len(packet)
        return bytes(WRITE_RES_OVERHEAD) + b"\xff" * len(request.tags)


@pytest.fixture(params=[S7Client, AsyncS7Client], ids=["sync", "async"])
def connection(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    client = request.param("127.0.0.1", max_pdu=240)
    client._connection_state = ConnectionState.CONNECTED
    plc = MemoryPLC()
    if isinstance(client, AsyncS7Client):
        monkeypatch.setattr(client, "_send_unlocked", AsyncMock(side_effect=plc.send))
    else:
        monkeypatch.setattr(client, "_S7Client__send", Mock(side_effect=plc.send))
    return client, plc


async def call(method, *args, **kwargs):
    result = method(*args, **kwargs)
    return await asyncio.wait_for(result, 1) if inspect.isawaitable(result) else result


@pytest.mark.asyncio
@pytest.mark.parametrize("optimize", [False, True])
@pytest.mark.parametrize("detailed", [False, True])
@pytest.mark.parametrize(
    "capacity,raw,value",
    [
        (26, b"Heating 72\xb0C", "Heating 72°C"),
        (26, b"Men\xfc", "Menü"),
        (26, b"", ""),
        (254, b"A" * 212 + b"\xb0\xfc\xe9" * 14, "A" * 212 + "°üé" * 14),
    ],
    ids=["degree", "umlaut", "empty", "chunk-boundary"],
)
async def test_string_reads_preserve_extended_bytes(
    connection, optimize: bool, detailed: bool, capacity: int, raw: bytes, value: str
) -> None:
    client, plc = connection
    tag = string_tag(capacity)
    plc.memory[: 2 + len(raw)] = bytes([capacity, len(raw)]) + raw
    read = client.read_detailed if detailed else client.read
    results = await call(read, [tag], optimize=optimize)
    if detailed:
        assert results[0].success, results[0].error
        assert results[0].value == value
    else:
        assert results == [value]
    assert client.is_connected
    # A subsequent unrelated value is still readable on the same connection.
    plc.memory[300:302] = b"\x12\x34"
    assert await call(client.read, ["DB1013,W300"], optimize=optimize) == [0x1234]
    if capacity == 254:
        assert any(t.data_type == DataType.CHAR for r in plc.requests for t in r.tags)


@pytest.mark.asyncio
@pytest.mark.parametrize("optimize", [False, True])
@pytest.mark.parametrize("detailed", [False, True])
@pytest.mark.parametrize("raw,value", [(b"\xfc", "ü"), (b"\xb0\xfc\xe9", "°üé")])
async def test_char_reads_and_adjacent_numeric_value(
    connection, optimize: bool, detailed: bool, raw: bytes, value: str
) -> None:
    client, plc = connection
    tags = [
        S7Tag(MemoryArea.DB, 1013, DataType.CHAR, 10, 0, len(raw)),
        S7Tag(MemoryArea.DB, 1013, DataType.INT, 14, 0, 1),
    ]
    plc.memory[10 : 10 + len(raw)] = raw
    plc.memory[14:16] = b"\x01\x23"
    read = client.read_detailed if detailed else client.read
    results = await call(read, tags, optimize=optimize)
    if detailed:
        assert all(result.success for result in results)
        assert [result.value for result in results] == [value, 0x123]
    else:
        assert results == [value, 0x123]


@pytest.mark.asyncio
@pytest.mark.parametrize("detailed", [False, True])
@pytest.mark.parametrize("capacity", [26, 254])
async def test_string_writes_preserve_bytes_and_following_memory(
    connection, detailed: bool, capacity: int
) -> None:
    client, plc = connection
    value = "Heating 72°C / Menü" if capacity == 26 else "°ü" * 127
    raw = b"Heating 72\xb0C / Men\xfc" if capacity == 26 else b"\xb0\xfc" * 127
    tag = string_tag(capacity)
    write = client.write_detailed if detailed else client.write
    results = await call(write, [tag], [value])
    if detailed:
        assert len(results) == 1 and results[0].success
    assert plc.memory[: 2 + len(raw)] == bytes([capacity, len(raw)]) + raw
    assert plc.memory[tag.size() : tag.size() + 4] == b"\xa5" * 4
    if capacity == 26:
        assert plc.memory[2 + len(raw) : tag.size()] == bytes(capacity - len(raw))
    assert await call(client.read, [tag]) == [value]


@pytest.mark.asyncio
@pytest.mark.parametrize("detailed", [False, True])
async def test_char_write_does_not_shift_next_item(connection, detailed: bool) -> None:
    client, plc = connection
    tags = [
        S7Tag(MemoryArea.DB, 1013, DataType.CHAR, 10, 0, 3),
        S7Tag(MemoryArea.DB, 1013, DataType.INT, 14, 0, 1),
    ]
    write = client.write_detailed if detailed else client.write
    results = await call(write, tags, ["°üé", 0x123])
    if detailed:
        assert all(result.success for result in results)
    assert plc.memory[10:16] == b"\xb0\xfc\xe9\xa5\x01\x23"


@pytest.mark.asyncio
@pytest.mark.parametrize("capacity", [26, 254])
@pytest.mark.parametrize("bad_type", [DataType.STRING, DataType.CHAR])
async def test_unrepresentable_write_is_rejected_before_any_io(
    connection, capacity: int, bad_type: DataType
) -> None:
    client, plc = connection
    tags = [string_tag(254), S7Tag(MemoryArea.DB, 1013, bad_type, 300, 0, capacity)]
    with pytest.raises(S7AddressError, match="cannot be encoded as latin-1"):
        await call(client.write, tags, ["valid", "€"])
    assert plc.requests == []
    assert client.is_connected


@pytest.mark.asyncio
@pytest.mark.parametrize("capacity", [26, 254])
async def test_detailed_write_reports_unrepresentable_text(
    connection, capacity: int
) -> None:
    client, plc = connection
    results = await call(client.write_detailed, [string_tag(capacity)], ["🌍"])
    assert len(results) == 1 and not results[0].success
    assert "cannot be encoded as latin-1" in results[0].error
    assert plc.requests == []


@pytest.mark.parametrize("as_view", [False, True])
@pytest.mark.parametrize("raw", [bytes(range(254)), b"\xfe\xff"])
def test_string_parser_accepts_every_byte(as_view: bool, raw: bytes) -> None:
    payload = bytes([254, len(raw)]) + raw + bytes(254 - len(raw))
    data = memoryview(payload) if as_view else payload
    assert _parse_string(data, 0, 254) == "".join(chr(byte) for byte in raw)


@pytest.mark.parametrize("as_view", [False, True])
def test_raw_string_fallback_keeps_extended_bytes(as_view: bool) -> None:
    raw = b"\xfc\xff\0"
    data = memoryview(raw) if as_view else raw
    assert _parse_string(data, 0, len(raw)) == "üÿ"
