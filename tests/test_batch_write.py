"""Tests for batch write transaction functionality."""

import socket
from typing import Any
from unittest.mock import MagicMock

import pytest

from pyS7 import BatchWriteTransaction, S7Client, WriteResult
from pyS7.constants import ConnectionState, ConnectionType, DataType, MemoryArea
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


class TestBatchWriteTransaction:
    """Test BatchWriteTransaction functionality."""

    def test_batch_write_context_manager(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test batch write with context manager."""
        # Mock write_detailed to return success
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            return [
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 4, 0, 1), success=True),
            ]
        
        # Mock read for rollback support
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            return [0, 0, 0]
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write() as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            batch.add("DB1,I4", 300)
        
        # Batch should auto-commit

    def test_batch_write_manual_commit(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test batch write with manual commit."""
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            return [
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1), success=True),
            ]
        
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            return [0, 0]
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write(auto_commit=False) as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            results = batch.commit()
        
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_batch_write_method_chaining(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test batch write with method chaining."""
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            return [
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 4, 0, 1), success=True),
            ]
        
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            return [0, 0, 0]
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write(auto_commit=False) as batch:
            results = batch.add("DB1,I0", 100).add("DB1,I2", 200).add("DB1,I4", 300).commit()
        
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_batch_write_rollback_on_error(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test batch write rollback when error occurs."""
        write_calls = []
        
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            write_calls.append(("write_detailed", tags, values))
            # First write fails, others succeed
            return [
                WriteResult(
                    tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1),
                    success=False,
                    error="Address out of range"
                ),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 4, 0, 1), success=True),
            ]
        
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            return [10, 20, 30]  # Original values
        
        def mock_write(self: S7Client, tags: Any, values: Any) -> None:
            write_calls.append(("write", tags, values))
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        monkeypatch.setattr(S7Client, "write", mock_write)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write(auto_commit=False, rollback_on_error=True) as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            batch.add("DB1,I4", 300)
            results = batch.commit()
        
        # Should have write_detailed call and rollback write call
        assert len(write_calls) == 2
        assert write_calls[0][0] == "write_detailed"
        assert write_calls[1][0] == "write"
        # Rollback should write original values
        assert write_calls[1][2] == [10, 20, 30]

    def test_batch_write_no_rollback(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test batch write without rollback."""
        write_calls = []
        
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            write_calls.append(("write_detailed", tags, values))
            return [
                WriteResult(
                    tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1),
                    success=False,
                    error="Error"
                ),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1), success=True),
            ]
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write(auto_commit=False, rollback_on_error=False) as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            results = batch.commit()
        
        # Should only have write_detailed call, no rollback
        assert len(write_calls) == 1
        assert write_calls[0][0] == "write_detailed"

    def test_batch_write_empty_raises_error(
        self, client: S7Client
    ) -> None:
        """Test that committing empty batch raises error."""
        _set_client_connected(client, MagicMock())
        
        with pytest.raises(ValueError, match="No tags added to batch"):
            with client.batch_write(auto_commit=False) as batch:
                batch.commit()

    def test_batch_write_empty_no_autocommit(
        self, client: S7Client
    ) -> None:
        """Test that empty batch with no auto-commit doesn't raise error."""
        _set_client_connected(client, MagicMock())
        
        # Should not raise error
        with client.batch_write(auto_commit=False) as batch:
            pass  # Don't add anything, don't commit

    def test_batch_write_with_s7tag_objects(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test batch write with S7Tag objects."""
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            return [
                WriteResult(tag=tags[0], success=True),
                WriteResult(tag=tags[1], success=True),
            ]
        
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            return [0, 0]
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        
        _set_client_connected(client, MagicMock())
        
        tag1 = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        tag2 = S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1)
        
        with client.batch_write(auto_commit=False) as batch:
            batch.add(tag1, 100)
            batch.add(tag2, 200)
            results = batch.commit()
        
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_batch_write_manual_rollback(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test manual rollback."""
        write_calls = []
        
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            return [
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1), success=True),
            ]
        
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            return [50, 60]
        
        def mock_write(self: S7Client, tags: Any, values: Any) -> None:
            write_calls.append(values)
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        monkeypatch.setattr(S7Client, "write", mock_write)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write(auto_commit=False, rollback_on_error=True) as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            batch.commit()
            batch.rollback()
        
        # Should have rolled back to original values
        assert len(write_calls) == 1
        assert write_calls[0] == [50, 60]

    def test_batch_write_rollback_without_commit_raises_error(
        self, client: S7Client
    ) -> None:
        """Test that manual rollback without commit raises error."""
        _set_client_connected(client, MagicMock())
        
        with pytest.raises(RuntimeError, match="Cannot rollback: no original values saved"):
            with client.batch_write(auto_commit=False, rollback_on_error=False) as batch:
                batch.add("DB1,I0", 100)
                batch.rollback()

    def test_batch_write_all_success(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test batch write where all writes succeed."""
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            return [
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1), success=True),
                WriteResult(tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 4, 0, 1), success=True),
            ]
        
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            return [10, 20, 30]
        
        write_calls = []
        
        def mock_write(self: S7Client, tags: Any, values: Any) -> None:
            write_calls.append(values)
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        monkeypatch.setattr(S7Client, "write", mock_write)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write(auto_commit=False, rollback_on_error=True) as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            batch.add("DB1,I4", 300)
            results = batch.commit()
        
        # All succeeded, no rollback should occur
        assert len(write_calls) == 0
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_batch_write_read_failure_no_rollback(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that batch write continues if read for rollback fails."""
        write_calls = []
        
        def mock_write_detailed(
            self: S7Client, tags: Any, values: Any
        ) -> list[WriteResult]:
            write_calls.append("write_detailed")
            return [
                WriteResult(
                    tag=S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1),
                    success=False,
                    error="Error"
                ),
            ]
        
        def mock_read(self: S7Client, tags: Any) -> list[Any]:
            raise Exception("Read failed")
        
        monkeypatch.setattr(S7Client, "write_detailed", mock_write_detailed)
        monkeypatch.setattr(S7Client, "read", mock_read)
        
        _set_client_connected(client, MagicMock())
        
        with client.batch_write(auto_commit=False, rollback_on_error=True) as batch:
            batch.add("DB1,I0", 100)
            results = batch.commit()
        
        # Write should have been attempted even though read failed
        assert len(write_calls) == 1
        assert not results[0].success


class TestBatchWriteDataclass:
    """Test BatchWriteTransaction dataclass properties."""

    def test_batch_write_transaction_creation(self, client: S7Client) -> None:
        """Test creating a BatchWriteTransaction."""
        batch = BatchWriteTransaction(
            client=client,
            auto_commit=True,
            rollback_on_error=True
        )
        
        assert batch._client is client
        assert batch.auto_commit is True
        assert batch.rollback_on_error is True
        assert batch._tags == []
        assert batch._values == []
        assert batch._original_values is None

    def test_batch_write_transaction_add(self, client: S7Client) -> None:
        """Test adding tags to batch."""
        batch = BatchWriteTransaction(client=client)
        
        batch.add("DB1,I0", 100)
        batch.add("DB1,I2", 200)
        
        assert len(batch._tags) == 2
        assert len(batch._values) == 2
        assert batch._tags[0] == "DB1,I0"
        assert batch._tags[1] == "DB1,I2"
        assert batch._values[0] == 100
        assert batch._values[1] == 200
