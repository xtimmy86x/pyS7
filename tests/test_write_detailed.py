"""Tests for write_detailed method with detailed results."""

import socket
from typing import Any
from unittest.mock import MagicMock

import pytest

from pyS7 import S7Client, WriteResult
from pyS7.constants import ConnectionState, ConnectionType, DataType, MemoryArea, ReturnCode
from pyS7.tag import S7Tag


def _set_client_connected(client: S7Client, sock: socket.socket) -> None:
    """Helper to set client as connected for testing."""
    client.socket = sock
    client._connection_state = ConnectionState.CONNECTED


@pytest.fixture
def client() -> S7Client:
    """Create a test client."""
    client = S7Client("192.168.100.10", 0, 1, ConnectionType.S7Basic, 102, 5)
    return client


@pytest.fixture(autouse=True)
def mock_socket_getpeername(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatically mock socket.getpeername() for all tests."""
    monkeypatch.setattr("socket.socket.getpeername", lambda self: ("192.168.100.10", 102))


class TestWriteDetailed:
    """Test write_detailed method with detailed results."""

    def test_write_detailed_all_success(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test write_detailed when all writes succeed."""
        # Response with 3 successful writes (return code 0xFF = success)
        # Based on real protocol format: TPKT(4) + COTP(3) + S7Header(12) + Param(2) + Data
        write_response = (
            b"\x03\x00\x00\x18"  # TPKT: version=3, length=24
            b"\x02\xf0\x80"  # COTP
            b"\x32\x03\x00\x00\x00\x00\x00\x02\x00\x03\x00\x00"  # S7 header (12 bytes)
            b"\x05\x03"  # Parameter: function=5, item_count=3
            b"\xff\xff\xff"  # 3 success codes
        )
        
        # Mock __send to return our response
        def mock_send(self, bytes_request: bytes) -> bytes:
            return write_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        # Ensure socket is initialized and state is connected
        _set_client_connected(client, MagicMock())

        tags = ["DB1,I0", "DB1,I2", "DB1,I4"]
        values = [100, 200, 300]

        results = client.write_detailed(tags, values)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert all(r.error is None for r in results)
        assert all(r.error_code is None for r in results)

    def test_write_detailed_partial_failure(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test write_detailed when some writes fail."""
        # Response: success, failure (0x05 = address out of range), success
        write_response = (
            b"\x03\x00\x00\x18"  # TPKT: length=24
            b"\x02\xf0\x80"  # COTP
            b"\x32\x03\x00\x00\x00\x00\x00\x02\x00\x03\x00\x00"  # S7 header
            b"\x05\x03"  # Parameter: function=5, item_count=3
            b"\xff\x05\xff"  # success, error, success
        )
        
        def mock_send(self, bytes_request: bytes) -> bytes:
            return write_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)

        _set_client_connected(client, MagicMock())

        tags = ["DB1,I0", "DB1,I2", "DB1,I4"]
        values = [100, 200, 300]

        results = client.write_detailed(tags, values)

        assert len(results) == 3
        assert results[0].success is True
        assert results[0].error is None

        assert results[1].success is False
        assert results[1].error is not None
        assert results[1].error_code == 0x05

        assert results[2].success is True
        assert results[2].error is None

    def test_write_detailed_all_failure(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test write_detailed when all writes fail."""
        # Response: all failures (0x0A = item not available)
        write_response = (
            b"\x03\x00\x00\x18"  # TPKT: length=24
            b"\x02\xf0\x80"  # COTP
            b"\x32\x03\x00\x00\x00\x00\x00\x02\x00\x03\x00\x00"  # S7 header
            b"\x05\x03"  # Parameter: function=5, item_count=3
            b"\x0a\x0a\x0a"  # 3 failures
        )
        
        def mock_send(self, bytes_request: bytes) -> bytes:
            return write_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)

        _set_client_connected(client, MagicMock())

        tags = ["DB99,I0", "DB99,I2", "DB99,I4"]
        values = [100, 200, 300]

        results = client.write_detailed(tags, values)

        assert len(results) == 3
        assert all(not r.success for r in results)
        assert all(r.error is not None for r in results)
        assert all(r.error_code == 0x0A for r in results)

    def test_write_detailed_empty_tags(self, client: S7Client) -> None:
        """Test write_detailed with empty tags raises ValueError."""
        with pytest.raises(ValueError, match="Tags and values lists cannot be empty"):
            client.write_detailed([], [])

    def test_write_detailed_mismatched_lengths(self, client: S7Client) -> None:
        """Test write_detailed with mismatched list lengths raises ValueError."""
        with pytest.raises(ValueError, match="Tags and values must have the same length"):
            client.write_detailed(["DB1,I0", "DB1,I2"], [100])

    def test_write_detailed_not_connected(self, client: S7Client) -> None:
        """Test write_detailed when not connected raises ConnectionError."""
        client.socket = None
        
        with pytest.raises(ConnectionError, match="Not connected to PLC"):
            client.write_detailed(["DB1,I0"], [100])

    def test_write_detailed_single_tag(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test write_detailed with single tag."""
        write_response = (
            b"\x03\x00\x00\x16"  # TPKT: length=22
            b"\x02\xf0\x80"  # COTP
            b"\x32\x03\x00\x00\x00\x00\x00\x02\x00\x01\x00\x00"  # S7 header
            b"\x05\x01"  # Parameter: function=5, item_count=1
            b"\xff"  # Single success
        )
        
        def mock_send(self, bytes_request: bytes) -> bytes:
            return write_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)

        _set_client_connected(client, MagicMock())

        results = client.write_detailed(["DB1,I0"], [42])

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].error is None

    def test_write_detailed_preserves_order(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that write_detailed preserves tag order in results."""
        # Response with mixed results
        write_response = (
            b"\x03\x00\x00\x1a"  # TPKT: length=26 (21 overhead + 5 return codes)
            b"\x02\xf0\x80"  # COTP
            b"\x32\x03\x00\x00\x00\x00\x00\x02\x00\x05\x00\x00"  # S7 header
            b"\x05\x05"  # Parameter: function=5, item_count=5
            b"\xff\x05\xff\x0a\xff"  # success, error, success, error, success
        )
        
        def mock_send(self, bytes_request: bytes) -> bytes:
            return write_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)

        _set_client_connected(client, MagicMock())

        tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,I6", "DB1,I8"]
        values = [1, 2, 3, 4, 5]

        results = client.write_detailed(tags, values)

        # Verify order is preserved
        assert len(results) == 5
        assert results[0].tag.start == 0
        assert results[1].tag.start == 2
        assert results[2].tag.start == 4
        assert results[3].tag.start == 6
        assert results[4].tag.start == 8

        # Verify success/failure pattern
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True
        assert results[3].success is False
        assert results[4].success is True

    def test_write_detailed_with_s7tag_objects(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test write_detailed with S7Tag objects instead of strings."""
        write_response = (
            b"\x03\x00\x00\x17"  # TPKT: length=23 (21 overhead + 2 return codes)
            b"\x02\xf0\x80"  # COTP
            b"\x32\x03\x00\x00\x00\x00\x00\x02\x00\x02\x00\x00"  # S7 header
            b"\x05\x02"  # Parameter: function=5, item_count=2
            b"\xff\xff"  # 2 successes
        )
        
        def mock_send(self, bytes_request: bytes) -> bytes:
            return write_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)

        _set_client_connected(client, MagicMock())

        tags = [
            S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1),
            S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1),
        ]
        values = [100, 200]

        results = client.write_detailed(tags, values)

        assert len(results) == 2
        assert all(r.success for r in results)


class TestWriteResultDataclass:
    """Test WriteResult dataclass."""

    def test_write_result_success(self) -> None:
        """Test WriteResult for successful write."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        result = WriteResult(tag=tag, success=True, error=None, error_code=None)

        assert result.success is True
        assert result.error is None
        assert result.error_code is None
        assert result.tag == tag

    def test_write_result_failure(self) -> None:
        """Test WriteResult for failed write."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        result = WriteResult(
            tag=tag, success=False, error="Address out of range", error_code=0x05
        )

        assert result.success is False
        assert result.error == "Address out of range"
        assert result.error_code == 0x05
        assert result.tag == tag

    def test_write_result_repr(self) -> None:
        """Test WriteResult string representation."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        result = WriteResult(
            tag=tag, success=False, error="Test error", error_code=0x05
        )

        repr_str = repr(result)
        assert "WriteResult" in repr_str
        assert "success=False" in repr_str
