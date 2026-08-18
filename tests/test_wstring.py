"""Hardware-derived WSTRING regressions for UTF-16 storage and chunking."""

import struct
from unittest.mock import AsyncMock

import pytest

from pyS7.async_client import AsyncS7Client
from pyS7.client import S7Client
from pyS7.constants import DataType, MemoryArea
from pyS7.errors import S7AddressError, S7CommunicationError
from pyS7.requests import WriteRequest, _pack_wstring_data
from pyS7.responses import _parse_wstring
from pyS7.tag import S7Tag


def wstring_tag(length: int = 10, start: int = 566) -> S7Tag:
    return S7Tag(MemoryArea.DB, 1, DataType.WSTRING, start, 0, length)


@pytest.mark.parametrize("value", ["", "AB", "東京", "🌍", "Hi 🌍", "😀😁"])
def test_wstring_packer_has_exact_declared_size(value: str) -> None:
    tag = wstring_tag()
    packed = _pack_wstring_data(value, tag.length, tag)

    assert len(packed) == 24
    assert struct.unpack(">HH", packed[:4]) == (10, len(value))
    encoded = value.encode("utf-16-be")
    assert packed[4 : 4 + len(encoded)] == encoded
    assert packed[4 + len(encoded) :] == bytes(20 - len(encoded))


@pytest.mark.parametrize("value", ["A" * 254, "🌍" * 127, "A" * 252 + "🌍"])
def test_wstring_utf16_capacity_boundaries_accept(value: str) -> None:
    tag = wstring_tag(254)
    assert len(_pack_wstring_data(value, tag.length, tag)) == 512


@pytest.mark.parametrize("value", ["🌍" * 128, "A" * 253 + "🌍"])
def test_wstring_utf16_capacity_boundaries_reject(value: str) -> None:
    tag = wstring_tag(254)
    with pytest.raises(S7AddressError, match="UTF-16 code units"):
        _pack_wstring_data(value, tag.length, tag)


@pytest.mark.parametrize("value,following", [("🌍", 63), ("Hi 🌍", 64), ("😀😁", 65)])
def test_wstring_multi_write_does_not_shift_following_item(
    value: str, following: int
) -> None:
    tags = [wstring_tag(10, 1078), S7Tag(MemoryArea.DB, 1, DataType.USINT, 1590, 0, 1)]
    packet = bytes(WriteRequest(tags, [value, following]).request)
    ascii_packet = bytes(WriteRequest(tags, ["AB", following]).request)

    assert len(packet) == len(ascii_packet)
    packed = _pack_wstring_data(value, 10, tags[0])
    assert len(packed) == tags[0].size()
    assert packet.find(packed) >= 0
    assert packet[packet.find(packed) + len(packed) :].endswith(bytes([following]))


@pytest.mark.parametrize(
    "value,current_length",
    [("🌍", 1), ("😀😁", 2)],
)
def test_normal_wstring_parser_handles_non_bmp(value: str, current_length: int) -> None:
    # Real PLC observation: max=254, current=1, payload=D83CDF0D for 🌍.
    raw = struct.pack(">HH", 254, current_length) + value.encode("utf-16-be")
    raw += bytes(508 - len(value.encode("utf-16-be")))
    assert _parse_wstring(raw, 0, 254) == value


def test_large_wstring_read_preserves_surrogate_across_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7Client("127.0.0.1", 0, 1)
    client.pdu_size = 240
    tag = wstring_tag(254)
    value = "A" * 109 + "🌍"  # First 220-byte chunk ends with the high surrogate.
    payload = value.encode("utf-16-be") + "stale".encode("utf-16-be")
    header = struct.pack(">HH", 254, len(value))

    def fake_read(tags: list[S7Tag], optimize: bool = True) -> list[object]:
        requested = tags[0]
        if requested.start == tag.start:
            return [tuple(header)]
        offset = requested.start - tag.start - 4
        return [tuple(payload[offset : offset + requested.length])]

    monkeypatch.setattr(client, "read", fake_read)
    assert client._read_large_string(tag) == value


def test_large_wstring_read_ignores_stale_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7Client("127.0.0.1", 0, 1)
    tag = wstring_tag(254)
    payload = "🌍fé".encode("utf-16-be")
    header = struct.pack(">HH", 254, 1)

    def fake_read(tags: list[S7Tag], optimize: bool = True) -> list[object]:
        requested = tags[0]
        if requested.start == tag.start:
            return [tuple(header)]
        return [tuple(payload[: requested.length])]

    monkeypatch.setattr(client, "read", fake_read)
    assert client._read_large_string(tag) == "🌍"


def test_large_wstring_write_rejects_before_sync_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7Client("127.0.0.1", 0, 1)
    write = AsyncMock()
    monkeypatch.setattr(client, "write", write)
    with pytest.raises(S7AddressError, match="256 UTF-16 code units"):
        client._write_large_string(wstring_tag(254), "🌍" * 128)
    write.assert_not_called()


@pytest.mark.parametrize("value", ["🌍", "Hello 🌍", "😀😁", "🌍" * 127])
def test_large_wstring_write_chunks_encoded_bytes_safely(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = S7Client("127.0.0.1", 0, 1)
    client.pdu_size = 240
    tag = wstring_tag(254)
    writes: list[tuple[S7Tag, object]] = []

    def fake_write(tags: list[S7Tag], values: list[object]) -> None:
        writes.append((tags[0], values[0]))

    monkeypatch.setattr(client, "write", fake_write)
    client._write_large_string(tag, value)

    header_tag, header_value = writes[0]
    assert header_tag.start == tag.start
    assert header_value == (0, 254, 0, len(value))
    payload_writes = writes[1:]
    assert all(chunk_tag.length % 2 == 0 for chunk_tag, _ in payload_writes)
    assert [chunk_tag.start for chunk_tag, _ in payload_writes] == [
        tag.start + 4 + sum(previous.length for previous, _ in payload_writes[:index])
        for index, (chunk_tag, _) in enumerate(payload_writes)
    ]
    payload = b"".join(bytes(chunk) for _, chunk in payload_writes)  # type: ignore[arg-type]
    assert payload == value.encode("utf-16-be")
    assert len(payload) <= tag.length * 2


@pytest.mark.asyncio
async def test_large_wstring_write_rejects_before_async_io() -> None:
    client = AsyncS7Client("127.0.0.1", 0, 1)
    send = AsyncMock()
    with pytest.raises(S7AddressError, match="255 UTF-16 code units"):
        await client._write_large_string_inner(wstring_tag(254), "A" * 253 + "🌍", send)
    send.assert_not_awaited()


def test_large_wstring_rejects_impossible_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7Client("127.0.0.1", 0, 1)
    tag = wstring_tag(4)
    monkeypatch.setattr(
        client, "read", lambda tags, optimize=False: [tuple(struct.pack(">HH", 4, 5))]
    )
    with pytest.raises(S7CommunicationError, match="Invalid WSTRING header"):
        client._read_large_string(tag)
