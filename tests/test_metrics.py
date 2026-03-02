"""Tests for ClientMetrics functionality."""

import time
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from pyS7 import ClientMetrics, S7Client
from pyS7.constants import ConnectionState


def _mock_recv_factory(*messages: bytes) -> Callable[[Any, int], bytes]:
    """Factory to create a mock recv function that handles multiple messages.
    
    This properly simulates socket.recv() behavior for _recv_exact().
    """
    buffers = [memoryview(message) for message in messages]
    current = [None]  # Use list to allow mutation in nested function
    
    def _mock_recv(self: Any, buf_size: int) -> bytes:
        if buf_size <= 0:
            return b""
        
        while current[0] is None or len(current[0]) == 0:
            if not buffers:
                return b""
            current[0] = buffers.pop(0)
        
        if len(current[0]) <= buf_size:
            chunk = current[0].tobytes()
            current[0] = None
            return chunk
        
        chunk = current[0][:buf_size].tobytes()
        current[0] = current[0][buf_size:]
        return chunk
    
    return _mock_recv


class TestClientMetrics:
    """Test ClientMetrics class."""
    
    def test_initialization(self):
        """Test metrics initialization with default values."""
        metrics = ClientMetrics()
        
        assert metrics.connected is False
        assert metrics.connection_start_time is None
        assert metrics.connection_count == 0
        assert metrics.disconnection_count == 0
        assert metrics.read_count == 0
        assert metrics.write_count == 0
        assert metrics.read_errors == 0
        assert metrics.write_errors == 0
        assert metrics.timeout_errors == 0
        assert metrics.last_read_duration == 0.0
        assert metrics.last_write_duration == 0.0
        assert metrics.total_read_duration == 0.0
        assert metrics.total_write_duration == 0.0
        assert metrics.total_bytes_read == 0
        assert metrics.total_bytes_written == 0
    
    def test_record_connection(self):
        """Test recording a connection."""
        metrics = ClientMetrics()
        
        before_time = time.time()
        metrics.record_connection()
        after_time = time.time()
        
        assert metrics.connected is True
        assert metrics.connection_count == 1
        assert metrics.connection_start_time is not None
        assert before_time <= metrics.connection_start_time <= after_time
    
    def test_record_disconnection(self):
        """Test recording a disconnection."""
        metrics = ClientMetrics()
        
        metrics.record_connection()
        assert metrics.connected is True
        
        metrics.record_disconnection()
        assert metrics.connected is False
        assert metrics.connection_start_time is None
        assert metrics.disconnection_count == 1
    
    def test_connection_uptime(self):
        """Test connection uptime calculation."""
        metrics = ClientMetrics()
        
        # Not connected - uptime should be 0
        assert metrics.connection_uptime == 0.0
        
        # Connect and wait a bit
        metrics.record_connection()
        time.sleep(0.1)  # 100ms
        
        uptime = metrics.connection_uptime
        assert uptime >= 0.1
        assert uptime < 0.2  # Should be close to 100ms
        
        # Disconnect - uptime should go back to 0
        metrics.record_disconnection()
        assert metrics.connection_uptime == 0.0
    
    def test_record_read_success(self):
        """Test recording successful read operations."""
        metrics = ClientMetrics()
        
        metrics.record_read(duration=0.025, bytes_read=100, success=True)
        
        assert metrics.read_count == 1
        assert metrics.last_read_duration == 0.025
        assert metrics.total_read_duration == 0.025
        assert metrics.total_bytes_read == 100
        assert metrics.read_errors == 0
        
        # Record another read
        metrics.record_read(duration=0.030, bytes_read=50, success=True)
        
        assert metrics.read_count == 2
        assert metrics.last_read_duration == 0.030
        assert metrics.total_read_duration == 0.055
        assert metrics.total_bytes_read == 150
    
    def test_record_read_failure(self):
        """Test recording failed read operations."""
        metrics = ClientMetrics()
        
        metrics.record_read(duration=0.015, bytes_read=0, success=False)
        
        assert metrics.read_count == 1
        assert metrics.read_errors == 1
        assert metrics.total_bytes_read == 0
    
    def test_record_write_success(self):
        """Test recording successful write operations."""
        metrics = ClientMetrics()
        
        metrics.record_write(duration=0.035, bytes_written=200, success=True)
        
        assert metrics.write_count == 1
        assert metrics.last_write_duration == 0.035
        assert metrics.total_write_duration == 0.035
        assert metrics.total_bytes_written == 200
        assert metrics.write_errors == 0
    
    def test_record_write_failure(self):
        """Test recording failed write operations."""
        metrics = ClientMetrics()
        
        metrics.record_write(duration=0.020, bytes_written=0, success=False)
        
        assert metrics.write_count == 1
        assert metrics.write_errors == 1
        assert metrics.total_bytes_written == 0
    
    def test_record_timeout(self):
        """Test recording timeout errors."""
        metrics = ClientMetrics()
        
        metrics.record_timeout()
        assert metrics.timeout_errors == 1
        
        metrics.record_timeout()
        assert metrics.timeout_errors == 2
    
    def test_avg_read_duration(self):
        """Test average read duration calculation."""
        metrics = ClientMetrics()
        
        # No reads - should be 0
        assert metrics.avg_read_duration == 0.0
        
        # Add multiple reads
        metrics.record_read(duration=0.010, bytes_read=100)
        metrics.record_read(duration=0.020, bytes_read=100)
        metrics.record_read(duration=0.030, bytes_read=100)
        
        assert metrics.avg_read_duration == 0.020  # (0.010 + 0.020 + 0.030) / 3
    
    def test_avg_write_duration(self):
        """Test average write duration calculation."""
        metrics = ClientMetrics()
        
        # No writes - should be 0
        assert metrics.avg_write_duration == 0.0
        
        # Add multiple writes
        metrics.record_write(duration=0.015, bytes_written=50)
        metrics.record_write(duration=0.025, bytes_written=50)
        
        assert metrics.avg_write_duration == 0.020  # (0.015 + 0.025) / 2
    
    def test_total_operations(self):
        """Test total operations property."""
        metrics = ClientMetrics()
        
        assert metrics.total_operations == 0
        
        metrics.record_read(duration=0.010, bytes_read=100)
        assert metrics.total_operations == 1
        
        metrics.record_write(duration=0.015, bytes_written=50)
        assert metrics.total_operations == 2
    
    def test_total_errors(self):
        """Test total errors property."""
        metrics = ClientMetrics()
        
        assert metrics.total_errors == 0
        
        metrics.record_read(duration=0.010, bytes_read=0, success=False)
        assert metrics.total_errors == 1
        
        metrics.record_write(duration=0.015, bytes_written=0, success=False)
        assert metrics.total_errors == 2
        
        metrics.record_timeout()
        assert metrics.total_errors == 3
    
    def test_error_rate(self):
        """Test error rate calculation."""
        metrics = ClientMetrics()
        
        # No operations - should be 0
        assert metrics.error_rate == 0.0
        
        # 2 successful, 1 failed = 33.33% error rate
        metrics.record_read(duration=0.010, bytes_read=100, success=True)
        metrics.record_read(duration=0.010, bytes_read=100, success=True)
        metrics.record_read(duration=0.010, bytes_read=0, success=False)
        
        assert abs(metrics.error_rate - 33.333) < 0.01
    
    def test_success_rate(self):
        """Test success rate calculation."""
        metrics = ClientMetrics()
        
        # No operations - should be 100%
        assert metrics.success_rate == 100.0
        
        # 3 successful, 1 failed = 75% success rate
        metrics.record_read(duration=0.010, bytes_read=100, success=True)
        metrics.record_read(duration=0.010, bytes_read=100, success=True)
        metrics.record_read(duration=0.010, bytes_read=100, success=True)
        metrics.record_read(duration=0.010, bytes_read=0, success=False)
        
        assert metrics.success_rate == 75.0
    
    def test_operations_per_minute(self):
        """Test operations per minute calculation."""
        metrics = ClientMetrics()
        
        # Not connected - should be 0
        assert metrics.operations_per_minute == 0.0
        
        # Mock connection time
        metrics.connected = True
        metrics.connection_start_time = time.time() - 60.0  # 60 seconds ago
        
        # 120 operations in 60 seconds = 120 ops/min
        for _ in range(60):
            metrics.record_read(duration=0.010, bytes_read=100)
        for _ in range(60):
            metrics.record_write(duration=0.015, bytes_written=50)
        
        ops_per_min = metrics.operations_per_minute
        assert abs(ops_per_min - 120.0) < 5.0  # Allow some timing variance
    
    def test_avg_bytes_per_read(self):
        """Test average bytes per read calculation."""
        metrics = ClientMetrics()
        
        # No reads - should be 0
        assert metrics.avg_bytes_per_read == 0.0
        
        metrics.record_read(duration=0.010, bytes_read=100)
        metrics.record_read(duration=0.010, bytes_read=200)
        
        assert metrics.avg_bytes_per_read == 150.0  # (100 + 200) / 2
    
    def test_avg_bytes_per_write(self):
        """Test average bytes per write calculation."""
        metrics = ClientMetrics()
        
        # No writes - should be 0
        assert metrics.avg_bytes_per_write == 0.0
        
        metrics.record_write(duration=0.015, bytes_written=50)
        metrics.record_write(duration=0.015, bytes_written=100)
        metrics.record_write(duration=0.015, bytes_written=150)
        
        assert metrics.avg_bytes_per_write == 100.0  # (50 + 100 + 150) / 3
    
    def test_reset(self):
        """Test resetting all metrics."""
        metrics = ClientMetrics()
        
        # Add some data
        metrics.record_connection()
        metrics.record_read(duration=0.010, bytes_read=100)
        metrics.record_write(duration=0.015, bytes_written=50)
        metrics.record_timeout()
        
        # Verify data exists
        assert metrics.connected is True
        assert metrics.read_count > 0
        assert metrics.write_count > 0
        
        # Reset
        metrics.reset()
        
        # Verify everything is reset
        assert metrics.connected is False
        assert metrics.connection_start_time is None
        assert metrics.connection_count == 0
        assert metrics.disconnection_count == 0
        assert metrics.read_count == 0
        assert metrics.write_count == 0
        assert metrics.read_errors == 0
        assert metrics.write_errors == 0
        assert metrics.timeout_errors == 0
        assert metrics.total_read_duration == 0.0
        assert metrics.total_write_duration == 0.0
        assert metrics.total_bytes_read == 0
        assert metrics.total_bytes_written == 0
    
    def test_as_dict(self):
        """Test exporting metrics as dictionary."""
        metrics = ClientMetrics()
        
        metrics.record_connection()
        metrics.record_read(duration=0.010, bytes_read=100)
        metrics.record_write(duration=0.015, bytes_written=50)
        
        data = metrics.as_dict()
        
        # Verify dict contains expected keys
        assert 'connected' in data
        assert 'connection_uptime' in data
        assert 'read_count' in data
        assert 'write_count' in data
        assert 'total_operations' in data
        assert 'total_errors' in data
        assert 'error_rate' in data
        assert 'success_rate' in data
        assert 'avg_read_duration' in data
        assert 'avg_write_duration' in data
        assert 'operations_per_minute' in data
        
        # Verify values
        assert data['connected'] is True
        assert data['read_count'] == 1
        assert data['write_count'] == 1
        assert data['total_operations'] == 2
    
    def test_str_representation(self):
        """Test string representation of metrics."""
        metrics = ClientMetrics()
        
        metrics.record_connection()
        metrics.record_read(duration=0.010, bytes_read=100)
        
        str_repr = str(metrics)
        
        # Verify string contains key information
        assert "S7Client Metrics" in str_repr
        assert "Connected" in str_repr
        assert "Operations:" in str_repr
        assert "Errors:" in str_repr


class TestS7ClientMetricsIntegration:
    """Test metrics integration with S7Client."""
    
    def test_client_with_metrics_enabled(self):
        """Test client with metrics enabled."""
        client = S7Client("192.168.5.100", 0, 1, enable_metrics=True)
        
        assert client.metrics is not None
        assert isinstance(client.metrics, ClientMetrics)
    
    def test_client_with_metrics_disabled(self):
        """Test client with metrics disabled."""
        client = S7Client("192.168.5.100", 0, 1, enable_metrics=False)
        
        assert client.metrics is None
    
    def test_client_default_metrics_enabled(self):
        """Test client has metrics enabled by default."""
        client = S7Client("192.168.5.100", 0, 1)
        
        assert client.metrics is not None
    
    def test_connect_tracks_metrics(self, monkeypatch: pytest.MonkeyPatch):
        """Test that connect() updates metrics."""
        def mock_connect(self: Any, *args: Any) -> None:
            return None
        
        def mock_sendall(self: Any, bytes_request: bytes) -> None:
            return None
        
        # Mock successful connection responses (same as in test_client.py)
        connection_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x00\x08\x00\x08\x03\xc0"
        )
        pdu_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x07\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x01\x00\x01\x03\xc0\x00"
        )
        
        monkeypatch.setattr("socket.socket.connect", mock_connect)
        monkeypatch.setattr("socket.socket.sendall", mock_sendall)
        monkeypatch.setattr("socket.socket.recv", _mock_recv_factory(connection_response, pdu_response))
        monkeypatch.setattr("socket.socket.getpeername", lambda self: ("192.168.5.100", 102))
        
        client = S7Client("192.168.5.100", 0, 1, enable_metrics=True)
        
        assert client.metrics.connection_count == 0
        assert client.metrics.connected is False
        
        client.connect()
        
        assert client.metrics.connection_count == 1
        assert client.metrics.connected is True
        assert client.metrics.connection_start_time is not None
    
    def test_disconnect_tracks_metrics(self):
        """Test that disconnect() updates metrics."""
        client = S7Client("192.168.5.100", 0, 1, enable_metrics=True)
        
        # Manually set connected state
        client._connection_state = ConnectionState.CONNECTED
        client.socket = MagicMock()
        client.metrics.record_connection()
        
        assert client.metrics.disconnection_count == 0
        
        client.disconnect()
        
        assert client.metrics.disconnection_count == 1
        assert client.metrics.connected is False
