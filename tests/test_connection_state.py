"""Tests for connection state management."""

from unittest.mock import MagicMock, patch
import socket

import pytest

from pyS7 import S7Client, ConnectionState
from pyS7.constants import ConnectionType
from pyS7.errors import S7ConnectionError, S7TimeoutError, S7ProtocolError


@pytest.fixture
def client() -> S7Client:
    """Create a test client."""
    return S7Client("192.168.100.10", 0, 1, ConnectionType.S7Basic, 102, 5)


class TestConnectionState:
    """Test connection state management."""

    def test_initial_state_is_disconnected(self, client: S7Client) -> None:
        """Test that initial state is DISCONNECTED."""
        assert client.connection_state == ConnectionState.DISCONNECTED
        assert not client.is_connected
        assert client.last_error is None

    def test_connection_state_during_connect(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test state transitions during successful connection."""
        states_observed = []

        # Mock socket operations
        mock_socket = MagicMock()
        mock_socket.connect = MagicMock()
        mock_socket.settimeout = MagicMock()
        mock_socket.getpeername = MagicMock(return_value=("192.168.100.10", 102))

        def track_state(*args, **kwargs):
            states_observed.append(client.connection_state)

        # Patch socket creation
        original_socket = socket.socket

        def mock_socket_create(*args, **kwargs):
            track_state()
            return mock_socket

        monkeypatch.setattr(socket, "socket", mock_socket_create)

        # Mock __send to return valid responses
        connection_response = bytes.fromhex(
            "03 00 00 16 11 D0 00 02 00 00 00 C0 01 0A C1 02 03 02 C2 02 01 00"
        )
        pdu_response = bytes.fromhex(
            "03 00 00 1b 02 f0 80 32 03 00 00 00 00 00 08 00 00 00 00 f0 00 00 08 00 08 03 c0"
        )

        responses = [connection_response, pdu_response]
        response_iter = iter(responses)

        def mock_send(self, request):
            track_state()
            return next(response_iter)

        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)

        # Initial state
        assert client.connection_state == ConnectionState.DISCONNECTED

        # Connect
        client.connect()

        # Should have transitioned through CONNECTING to CONNECTED
        assert ConnectionState.CONNECTING in states_observed
        assert client.connection_state == ConnectionState.CONNECTED
        assert client.is_connected
        assert client.last_error is None

    def test_connection_state_on_timeout(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test state transitions when connection times out."""
        # Mock socket to raise timeout
        def mock_socket_create(*args, **kwargs):
            mock = MagicMock()
            mock.connect.side_effect = socket.timeout("Connection timed out")
            return mock

        monkeypatch.setattr(socket, "socket", mock_socket_create)

        # Attempt connection
        with pytest.raises(S7TimeoutError):
            client.connect()

        # Should be in ERROR state
        assert client.connection_state == ConnectionState.ERROR
        assert not client.is_connected
        assert client.last_error is not None
        assert "timeout" in client.last_error.lower()

    def test_connection_state_on_socket_error(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test state transitions when socket error occurs."""
        # Mock socket to raise error
        def mock_socket_create(*args, **kwargs):
            mock = MagicMock()
            mock.connect.side_effect = socket.error("Connection refused")
            return mock

        monkeypatch.setattr(socket, "socket", mock_socket_create)

        # Attempt connection
        with pytest.raises(S7ConnectionError):
            client.connect()

        # Should be in ERROR state
        assert client.connection_state == ConnectionState.ERROR
        assert not client.is_connected
        assert client.last_error is not None
        assert "connection refused" in client.last_error.lower()

    def test_connection_state_on_protocol_error(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test state transitions when protocol error occurs."""
        # Mock socket operations
        mock_socket = MagicMock()
        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)

        # Mock __send to return invalid response
        def mock_send(self, request):
            return b"\x00\x00\x00\x00"  # Invalid response

        monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", mock_send)

        # Attempt connection
        with pytest.raises(S7ProtocolError):
            client.connect()

        # Should be in ERROR state
        assert client.connection_state == ConnectionState.ERROR
        assert not client.is_connected
        assert client.last_error is not None

    def test_disconnect_from_connected(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test disconnect from CONNECTED state."""
        # Setup connected client
        client._connection_state = ConnectionState.CONNECTED
        client.socket = MagicMock()

        # Disconnect
        client.disconnect()

        # Should be DISCONNECTED
        assert client.connection_state == ConnectionState.DISCONNECTED
        assert not client.is_connected
        assert client.socket is None

    def test_disconnect_from_error(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test disconnect from ERROR state preserves error."""
        # Setup error state
        error_msg = "Test error"
        client._connection_state = ConnectionState.ERROR
        client._last_error = error_msg
        client.socket = MagicMock()

        # Disconnect
        client.disconnect()

        # Should remain in ERROR state with error preserved
        assert client.connection_state == ConnectionState.ERROR
        assert client.last_error == error_msg
        assert client.socket is None

    def test_disconnect_when_already_disconnected(self, client: S7Client) -> None:
        """Test disconnect when already disconnected is idempotent."""
        assert client.connection_state == ConnectionState.DISCONNECTED

        # Disconnect again
        client.disconnect()

        # Should still be DISCONNECTED
        assert client.connection_state == ConnectionState.DISCONNECTED

    def test_connect_when_already_connected(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test connect when already connected is idempotent."""
        # Setup connected client
        client._connection_state = ConnectionState.CONNECTED
        client.socket = MagicMock()

        # Spy on socket creation to ensure it's not called
        socket_spy = MagicMock()
        monkeypatch.setattr(socket, "socket", socket_spy)

        # Try to connect again
        client.connect()

        # Should still be CONNECTED and socket not recreated
        assert client.connection_state == ConnectionState.CONNECTED
        socket_spy.assert_not_called()

    def test_connect_when_connecting(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test connect when connection in progress."""
        # Setup connecting state
        client._connection_state = ConnectionState.CONNECTING

        # Spy on socket creation to ensure it's not called
        socket_spy = MagicMock()
        monkeypatch.setattr(socket, "socket", socket_spy)

        # Try to connect again
        client.connect()

        # Should still be CONNECTING and socket not recreated
        assert client.connection_state == ConnectionState.CONNECTING
        socket_spy.assert_not_called()

    def test_state_cleared_on_successful_reconnect(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that error is cleared on successful reconnect."""
        # Setup error state
        client._connection_state = ConnectionState.ERROR
        client._last_error = "Previous error"

        # Mock successful connection
        mock_socket = MagicMock()
        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)

        connection_response = bytes.fromhex(
            "03 00 00 16 11 D0 00 02 00 00 00 C0 01 0A C1 02 03 02 C2 02 01 00"
        )
        pdu_response = bytes.fromhex(
            "03 00 00 1b 02 f0 80 32 03 00 00 00 00 00 08 00 00 00 00 f0 00 00 08 00 08 03 c0"
        )

        responses = iter([connection_response, pdu_response])
        monkeypatch.setattr(
            "pyS7.client.S7Client._S7Client__send", lambda self, req: next(responses)
        )

        # Reconnect
        client.connect()

        # Should be CONNECTED with error cleared
        assert client.connection_state == ConnectionState.CONNECTED
        assert client.is_connected
        assert client.last_error is None

    def test_is_connected_only_true_when_connected(self, client: S7Client) -> None:
        """Test is_connected property for all states."""
        # DISCONNECTED
        client._connection_state = ConnectionState.DISCONNECTED
        assert not client.is_connected

        # CONNECTING
        client._connection_state = ConnectionState.CONNECTING
        assert not client.is_connected

        # CONNECTED
        client._connection_state = ConnectionState.CONNECTED
        assert client.is_connected

        # ERROR
        client._connection_state = ConnectionState.ERROR
        assert not client.is_connected

        # DISCONNECTING
        client._connection_state = ConnectionState.DISCONNECTING
        assert not client.is_connected

    def test_context_manager_state_transitions(
        self, client: S7Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test state transitions when using context manager."""
        # Mock successful connection
        mock_socket = MagicMock()
        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)

        connection_response = bytes.fromhex(
            "03 00 00 16 11 D0 00 02 00 00 00 C0 01 0A C1 02 03 02 C2 02 01 00"
        )
        pdu_response = bytes.fromhex(
            "03 00 00 1b 02 f0 80 32 03 00 00 00 00 00 08 00 00 00 00 f0 00 00 08 00 08 03 c0"
        )

        responses = iter([connection_response, pdu_response])
        monkeypatch.setattr(
            "pyS7.client.S7Client._S7Client__send", lambda self, req: next(responses)
        )

        # Use context manager
        assert client.connection_state == ConnectionState.DISCONNECTED

        with client:
            assert client.connection_state == ConnectionState.CONNECTED
            assert client.is_connected

        # Should be disconnected after context
        assert client.connection_state == ConnectionState.DISCONNECTED
        assert not client.is_connected


class TestConnectionStateProperties:
    """Test connection state properties."""

    def test_connection_state_enum_values(self) -> None:
        """Test ConnectionState enum has expected values."""
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.ERROR.value == "error"
        assert ConnectionState.DISCONNECTING.value == "disconnecting"

    def test_last_error_none_initially(self, client: S7Client) -> None:
        """Test last_error is None initially."""
        assert client.last_error is None

    def test_last_error_set_on_error(self, client: S7Client) -> None:
        """Test last_error is set when entering ERROR state."""
        error_msg = "Test error message"
        client._set_connection_state(ConnectionState.ERROR, error_msg)

        assert client.last_error == error_msg
        assert client.connection_state == ConnectionState.ERROR

    def test_last_error_cleared_on_connect(self, client: S7Client) -> None:
        """Test last_error is cleared when connecting successfully."""
        # Set error
        client._set_connection_state(ConnectionState.ERROR, "Previous error")
        assert client.last_error == "Previous error"

        # Connect successfully
        client._set_connection_state(ConnectionState.CONNECTED)

        assert client.last_error is None
        assert client.connection_state == ConnectionState.CONNECTED
