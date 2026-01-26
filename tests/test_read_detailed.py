"""Tests for read_detailed method with detailed results."""

import socket
import struct
from typing import Any
from unittest.mock import MagicMock

import pytest

from pyS7 import ReadResult, S7Client
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


class TestReadDetailed:
    """Test read_detailed functionality."""

    def test_read_detailed_all_success(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test read_detailed when all reads succeed."""
        # Response with 3 successful reads
        # Format: TPKT(4) + COTP(3) + S7Header(12) + Param(2) + Data(18)
        read_response = (
            b"\x03\x00\x00'"  # TPKT: length=39
            b"\x02\xf0\x80"  # COTP
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x12\x00\x00"  # S7 header (data_len=0x12=18)
            b"\x04\x03"  # Parameter: function=4, item_count=3
            # Item 1: BIT, 1 bit (6 bytes total)
            b"\xff\x03\x00\x01\x01\x00"  # RC=0xFF, TS=0x03, len=1, data=0x01, fill
            # Item 2: BIT, 1 bit (6 bytes total)
            b"\xff\x03\x00\x01\x01\x00"  # RC=0xFF, TS=0x03, len=1, data=0x01, fill
            # Item 3: INT, 16 bits (6 bytes total)
            b"\xff\x04\x00\x10\x00\x00"  # RC=0xFF, TS=0x04, len=16, data=0x0000
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        tags = ["DB1,X0.0", "DB1,X0.1", "DB2,I2"]
        results = client.read_detailed(tags, optimize=False)
        
        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].value == True
        assert results[1].value == True
        assert results[2].value == 0

    def test_read_detailed_partial_failure(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test read_detailed when some reads fail."""
        # Response: success, failure (0x0A = object does not exist), success
        read_response = (
            b"\x03\x00\x00#"  # TPKT: length=35 (4+3+12+2+14)
            b"\x02\xf0\x80"  # COTP
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x0e\x00\x00"  # S7 header (data_len=14)
            b"\x04\x03"  # Parameter: function=4, item_count=3
            # Item 1: BIT success (6 bytes: RC+TS+len+data+fill)
            b"\xff\x03\x00\x01\x01\x00"  # RC=0xFF, TS=0x03, len=1, data=0x01, fill
            # Item 2: Error (2 bytes: RC+fill)
            b"\x0a\x00"  # RC=0x0A (OBJECT_DOES_NOT_EXIST) + fill
            # Item 3: INT success (6 bytes: RC+TS+len+data)
            b"\xff\x04\x00\x10\x00\x64"  # RC=0xFF, TS=0x04, len=16, data=100
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        tags = ["DB1,X0.0", "DB99,I10", "DB1,I4"]
        results = client.read_detailed(tags, optimize=False)
        
        assert len(results) == 3
        assert results[0].success is True
        assert results[0].value == True
        assert results[1].success is False
        assert "object_does_not_exist" in results[1].error.lower()
        assert results[2].success is True
        assert results[2].value == 100

    def test_read_detailed_all_failure(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test read_detailed when all reads fail."""
        # Response: all failures (0x05 = address out of range)
        read_response = (
            b"\x03\x00\x00\x19"  # TPKT: length=25 (4+3+12+2+4)
            b"\x02\xf0\x80"  # COTP
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x04\x00\x00"  # S7 header (data_len=4)
            b"\x04\x02"  # Parameter: function=4, item_count=2
            b"\x05\x00"  # Item 1: Error 0x05 + fill
            b"\x05\x00"  # Item 2: Error 0x05 + fill
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        tags = ["DB99,I0", "DB99,I2"]
        results = client.read_detailed(tags, optimize=False)
        
        assert len(results) == 2
        assert all(not r.success for r in results)
        assert all("out_of_range" in r.error.lower() for r in results)

    def test_read_detailed_empty_tags_raises_error(
        self, client: S7Client
    ) -> None:
        """Test that empty tags list raises error."""
        _set_client_connected(client, MagicMock())
        
        with pytest.raises(ValueError, match="Tags list cannot be empty"):
            client.read_detailed([])

    def test_read_detailed_not_connected(
        self, client: S7Client
    ) -> None:
        """Test that read_detailed raises error when not connected."""
        # Don't connect
        with pytest.raises(Exception, match="Not connected"):
            client.read_detailed(["DB1,I0"])

    def test_read_detailed_with_s7tag_objects(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test read_detailed with S7Tag objects."""
        read_response = (
            b"\x03\x00\x00\x1d\x02\xf0\x80"
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x08\x00\x00"
            b"\x04\x02"
            b"\xff\x04\x00\x10\x00\x64"  # INT value 100
            b"\xff\x04\x00\x10\x00\xc8"  # INT value 200
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        tag1 = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        tag2 = S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1)
        
        results = client.read_detailed([tag1, tag2], optimize=False)
        
        assert len(results) == 2
        assert all(r.success for r in results)
        assert results[0].value == 100
        assert results[1].value == 200

    def test_read_detailed_mixed_success_and_errors(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test read_detailed with various error types."""
        # Response with different error codes
        # Item 1: INT success (6 bytes), Item 2: error (2 bytes), Item 3: error (2 bytes), Item 4: INT success (6 bytes)
        read_response = (
            b"\x03\x00\x00%"  # TPKT: length=37 (4+3+12+2+16)
            b"\x02\xf0\x80"  # COTP
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x10\x00\x00"  # S7 header (data_len=16)
            b"\x04\x04"  # 4 items
            b"\xff\x04\x00\x10\x00\x0a"  # Success INT, value=10 (6 bytes)
            b"\x05\x00"  # Error 0x05 + fill (2 bytes)
            b"\x0a\x00"  # Error 0x0A + fill (2 bytes)
            b"\xff\x04\x00\x10\x00\x14"  # Success INT, value=20 (6 bytes)
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        tags = ["DB1,I0", "DB1,I2", "DB99,I0", "DB1,I4"]
        results = client.read_detailed(tags, optimize=False)
        
        assert len(results) == 4
        assert results[0].success is True
        assert results[0].value == 10
        assert results[1].success is False
        assert results[2].success is False
        assert results[3].success is True
        assert results[3].value == 20

    def test_read_detailed_single_tag(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test read_detailed with single tag."""
        read_response = (
            b"\x03\x00\x00\x19\x02\xf0\x80"
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x04\x00\x00"
            b"\x04\x01"  # 1 item
            b"\xff\x04\x00\x10\x00\x2a"  # Success, value=42
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        results = client.read_detailed(["DB1,I0"], optimize=False)
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].value == 42

    def test_read_detailed_preserves_order(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that read_detailed preserves tag order."""
        read_response = (
            b"\x03\x00\x00)\x02\xf0\x80"
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x14\x00\x00"
            b"\x04\x05"  # 5 items
            b"\xff\x04\x00\x10\x00\x01"  # value=1
            b"\xff\x04\x00\x10\x00\x02"  # value=2
            b"\xff\x04\x00\x10\x00\x03"  # value=3
            b"\xff\x04\x00\x10\x00\x04"  # value=4
            b"\xff\x04\x00\x10\x00\x05"  # value=5
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,I6", "DB1,I8"]
        results = client.read_detailed(tags, optimize=False)
        
        assert len(results) == 5
        for i, result in enumerate(results, 1):
            assert result.success is True
            assert result.value == i

    def test_read_detailed_different_data_types(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test read_detailed with different data types."""
        # BIT(6), BYTE(6), INT(6), DINT(8) = 26 bytes total
        read_response = (
            b"\x03\x00\x003"  # TPKT: length=51 (4+3+12+2+26)
            b"\x02\xf0\x80"  # COTP
            b"2\x03\x00\x00\x00\x00\x00\x02\x00\x1a\x00\x00"  # S7 header (data_len=26)
            b"\x04\x04"  # 4 items
            b"\xff\x03\x00\x01\x01\x00"  # BIT, value=True (6 bytes: RC+TS+len+data+fill)
            b"\xff\x04\x00\x08\xff\x00"  # BYTE, value=255 (6 bytes: RC+TS+len+data+fill)
            b"\xff\x04\x00\x10\x7d\x00"  # INT, value=32000 (6 bytes: RC+TS+len+data)
            b"\xff\x04\x00\x20\x00\x01\x86\xa0"  # DINT, value=100000 (8 bytes: RC+TS+len+data)
        )
        
        def mock_send(self: S7Client, request: Any) -> bytes:
            return read_response
        
        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)
        
        _set_client_connected(client, MagicMock())
        
        tags = ["DB1,X0.0", "DB1,B2", "DB1,I4", "DB1,DI6"]
        results = client.read_detailed(tags, optimize=False)
        
        assert len(results) == 4
        assert all(r.success for r in results)
        assert results[0].value == True
        assert results[1].value == 255
        assert results[2].value == 32000
        assert results[3].value == 100000


class TestReadResultDataclass:
    """Test ReadResult dataclass properties."""

    def test_read_result_success(self) -> None:
        """Test ReadResult for successful read."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        result = ReadResult(tag=tag, success=True, value=42)
        
        assert result.tag == tag
        assert result.success is True
        assert result.value == 42
        assert result.error is None
        assert result.error_code is None

    def test_read_result_failure(self) -> None:
        """Test ReadResult for failed read."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        result = ReadResult(
            tag=tag,
            success=False,
            error="Address not available",
            error_code=0x0A
        )
        
        assert result.tag == tag
        assert result.success is False
        assert result.value is None
        assert result.error == "Address not available"
        assert result.error_code == 0x0A

    def test_read_result_repr(self) -> None:
        """Test ReadResult string representation."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        result = ReadResult(tag=tag, success=True, value=123)
        
        repr_str = repr(result)
        assert "ReadResult" in repr_str
        assert "success=True" in repr_str
        assert "value=123" in repr_str
