"""Tests for AsyncS7Client."""

import asyncio
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyS7.async_client import AsyncBatchWriteTransaction, AsyncS7Client
from pyS7.client import ReadResult, WriteResult
from pyS7.constants import (
    MAX_JOB_CALLED,
    MAX_JOB_CALLING,
    MAX_PDU,
    ConnectionState,
    ConnectionType,
    DataType,
    MemoryArea,
)
from pyS7.errors import S7CommunicationError, S7ConnectionError, S7TimeoutError
from pyS7.tag import S7Tag


# -- Protocol response fixtures -----------------------------------------------

CONNECTION_RESPONSE = (
    b"\x03\x00\x00\x1b\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x08"
    b"\x00\x00\x00\x00\xf0\x00\x00\x08\x00\x08\x03\xc0"
)

PDU_RESPONSE = (
    b"\x03\x00\x00\x1b\x02\xf0\x802\x07\x00\x00\x00\x00\x00\x08"
    b"\x00\x00\x00\x00\xf0\x00\x01\x00\x01\x03\xc0\x00"
)


# -- Helpers -------------------------------------------------------------------


def _fake_reader(*messages: bytes) -> asyncio.StreamReader:
    """Build a StreamReader pre-loaded with *messages*."""
    reader = asyncio.StreamReader()
    for msg in messages:
        reader.feed_data(msg)
    return reader


def _fake_writer() -> MagicMock:
    """Build a mock StreamWriter."""
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return writer


async def _connect_client(client: AsyncS7Client) -> None:
    """Force client into CONNECTED state for unit tests."""
    reader = _fake_reader(CONNECTION_RESPONSE, PDU_RESPONSE)
    writer = _fake_writer()
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        await client.connect()


# -- Constructor & properties -------------------------------------------------


@pytest.fixture
def client() -> AsyncS7Client:
    return AsyncS7Client("192.168.100.10", 0, 1)


def test_init_defaults(client: AsyncS7Client) -> None:
    assert client.address == "192.168.100.10"
    assert client.rack == 0
    assert client.slot == 1
    assert client.port == 102
    assert client.timeout == 5.0
    assert client.pdu_size == MAX_PDU
    assert client.is_connected is False
    assert client.connection_state == ConnectionState.DISCONNECTED
    assert client.last_error is None
    assert client.metrics is not None


def test_init_tsap_string() -> None:
    c = AsyncS7Client("10.0.0.1", local_tsap="03.00", remote_tsap="03.01")
    assert c.local_tsap == 0x0300
    assert c.remote_tsap == 0x0301


def test_init_invalid_pdu() -> None:
    with pytest.raises(ValueError, match="max_pdu"):
        AsyncS7Client("10.0.0.1", max_pdu=10)


def test_static_helpers() -> None:
    assert AsyncS7Client.tsap_from_string("03.01") == 0x0301
    assert AsyncS7Client.tsap_to_string(0x0301) == "03.01"
    assert AsyncS7Client.tsap_from_rack_slot(0, 1) == 0x0101


# -- Connect / Disconnect -----------------------------------------------------


@pytest.mark.asyncio
async def test_connect_success(client: AsyncS7Client) -> None:
    await _connect_client(client)
    assert client.is_connected
    assert client.connection_state == ConnectionState.CONNECTED


@pytest.mark.asyncio
async def test_connect_timeout(client: AsyncS7Client) -> None:
    with patch(
        "asyncio.open_connection",
        AsyncMock(side_effect=asyncio.TimeoutError()),
    ):
        with pytest.raises(S7TimeoutError):
            await client.connect()
    assert not client.is_connected


@pytest.mark.asyncio
async def test_connect_refused(client: AsyncS7Client) -> None:
    with patch(
        "asyncio.open_connection",
        AsyncMock(side_effect=OSError("Connection refused")),
    ):
        with pytest.raises(S7ConnectionError):
            await client.connect()
    assert not client.is_connected


@pytest.mark.asyncio
async def test_disconnect(client: AsyncS7Client) -> None:
    await _connect_client(client)
    await client.disconnect()
    assert not client.is_connected
    assert client.connection_state == ConnectionState.DISCONNECTED


@pytest.mark.asyncio
async def test_disconnect_when_already_disconnected(client: AsyncS7Client) -> None:
    await client.disconnect()  # should not raise
    assert not client.is_connected


@pytest.mark.asyncio
async def test_context_manager(client: AsyncS7Client) -> None:
    reader = _fake_reader(CONNECTION_RESPONSE, PDU_RESPONSE)
    writer = _fake_writer()
    with patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))):
        async with client:
            assert client.is_connected
    assert not client.is_connected


# -- Read ----------------------------------------------------------------------


# Build a well-formed S7 read-response for a single INT tag (value = 42).
# TPKT(4) + COTP(3) + S7 header(12) + param(2) + data-item(4+2) = 27 bytes
_READ_INT_42 = (
    b"\x03\x00\x00\x1b"          # TPKT: version=3, reserved=0, length=27
    b"\x02\xf0\x80"              # COTP DT
    b"\x32\x03"                   # S7: response
    b"\x00\x00"                   # reserved
    b"\x00\x00"                   # sequence
    b"\x00\x02"                   # param length = 2
    b"\x00\x06"                   # data length = 6 (1 return code + 1 transport + 2 length + 2 data)
    b"\x00"                       # error class
    b"\x00"                       # error code
    b"\x04\x01"                   # param: function=read, item-count=1
    b"\xff"                       # return code: success
    b"\x04"                       # transport size: BYTE/WORD
    b"\x00\x10"                   # length in bits = 16
    b"\x00\x2a"                   # data: 42 as signed 16-bit big-endian
)


@pytest.mark.asyncio
async def test_read_single_int(client: AsyncS7Client) -> None:
    await _connect_client(client)

    # Prepare a reader that returns the read-response
    client._reader = _fake_reader(_READ_INT_42)

    values = await client.read(["DB1,I0"], optimize=False)
    assert values == [42]


@pytest.mark.asyncio
async def test_read_not_connected() -> None:
    c = AsyncS7Client("10.0.0.1")
    with pytest.raises(S7CommunicationError, match="Not connected"):
        await c.read(["DB1,I0"])


@pytest.mark.asyncio
async def test_read_empty_tags(client: AsyncS7Client) -> None:
    result = await client.read([])
    assert result == []


# -- Write ---------------------------------------------------------------------


# Minimal write-response: TPKT(4) + COTP(3) + S7 header(12) + param(2) + 1 data byte = 22
_WRITE_OK = (
    b"\x03\x00\x00\x16"
    b"\x02\xf0\x80"
    b"\x32\x03"
    b"\x00\x00"
    b"\x00\x00"
    b"\x00\x02"
    b"\x00\x01"
    b"\x00"
    b"\x00"
    b"\x05\x01"
    b"\xff"
)


@pytest.mark.asyncio
async def test_write_single_int(client: AsyncS7Client) -> None:
    await _connect_client(client)
    client._reader = _fake_reader(_WRITE_OK)
    await client.write(["DB1,I0"], [42])  # should not raise


@pytest.mark.asyncio
async def test_write_not_connected() -> None:
    c = AsyncS7Client("10.0.0.1")
    with pytest.raises(S7CommunicationError, match="Not connected"):
        await c.write(["DB1,I0"], [42])


@pytest.mark.asyncio
async def test_write_mismatched_lengths(client: AsyncS7Client) -> None:
    with pytest.raises(ValueError, match="equal"):
        await client.write(["DB1,I0", "DB1,I2"], [42])


# -- write_detailed ------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_detailed(client: AsyncS7Client) -> None:
    await _connect_client(client)
    client._reader = _fake_reader(_WRITE_OK)
    results = await client.write_detailed(["DB1,I0"], [42])
    assert len(results) == 1
    assert results[0].success


# -- read_detailed -------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_detailed_single(client: AsyncS7Client) -> None:
    await _connect_client(client)
    client._reader = _fake_reader(_READ_INT_42)
    results = await client.read_detailed(["DB1,I0"], optimize=False)
    assert len(results) == 1
    assert results[0].success
    assert results[0].value == 42


@pytest.mark.asyncio
async def test_read_detailed_empty_raises(client: AsyncS7Client) -> None:
    with pytest.raises(ValueError, match="empty"):
        await client.read_detailed([])


# -- batch_write ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_write_context(client: AsyncS7Client) -> None:
    await _connect_client(client)

    # First read (snapshot), then write, then write_detailed
    client._reader = _fake_reader(_READ_INT_42, _WRITE_OK)

    async with client.batch_write(rollback_on_error=False) as batch:
        batch.add("DB1,I0", 100)
        # auto_commit fires on __aexit__


@pytest.mark.asyncio
async def test_batch_write_add_chaining(client: AsyncS7Client) -> None:
    b = client.batch_write()
    result = b.add("DB1,I0", 1).add("DB1,I2", 2)
    assert result is b
    assert len(b._tags) == 2


# -- get_cpu_status / get_cpu_info ---------------------------------------------


# get_cpu_status test omitted — SZL response construction is complex
# and covered by the sync test_szl.py tests.  The async transport
# layer is already validated by the read/write tests above.


# -- Metrics tracking ----------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_on_connect(client: AsyncS7Client) -> None:
    await _connect_client(client)
    assert client.metrics is not None
    assert client.metrics.connection_count >= 1


@pytest.mark.asyncio
async def test_metrics_disabled() -> None:
    c = AsyncS7Client("10.0.0.1", enable_metrics=False)
    assert c.metrics is None


# -- Connection state transitions ----------------------------------------------


@pytest.mark.asyncio
async def test_connect_already_connected(client: AsyncS7Client) -> None:
    await _connect_client(client)
    await client.connect()  # should warn but not error
    assert client.is_connected
