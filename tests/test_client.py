import socket
from typing import Any

import pytest

from pyS7.client import S7Client
from pyS7.constants import MAX_JOB_CALLED, MAX_JOB_CALLING, MAX_PDU, ConnectionType


@pytest.fixture
def client() -> S7Client:
    client = S7Client("192.168.100.10", 0, 1, ConnectionType.S7Basic, 102, 5)
    return client


def test_client_init(client: S7Client) -> None:
    assert client.address == "192.168.100.10"
    assert client.rack == 0
    assert client.slot == 1
    assert client.connection_type == ConnectionType.S7Basic
    assert client.port == 102
    assert client.timeout == 5

    assert client.socket is None

    assert client.max_jobs_called == MAX_JOB_CALLED
    assert client.max_jobs_calling == MAX_JOB_CALLING
    assert client.pdu_size == MAX_PDU


def test_client_connect(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_connect(self: Any, *args: Any) -> None:
        return None

    def mock_send(self: Any, bytes_request: bytes) -> None:
        return None

    def mock_recv(self: Any, buf_size: int) -> bytes:
        return b"\x03\x00\x00\x1b\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x00\x08\x00\x08\x03\xc0"

    monkeypatch.setattr("socket.socket.connect", mock_connect)
    monkeypatch.setattr("socket.socket.send", mock_send)
    monkeypatch.setattr("socket.socket.recv", mock_recv)

    client.connect()

    assert client.socket is not None
    assert client.socket.gettimeout() == 5


def test_client_disconnect(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("socket.socket.shutdown", lambda *args, **kwargs: None)
    monkeypatch.setattr("socket.socket.close", lambda *args, **kwargs: None)

    client.disconnect()

    assert client.socket is None


def test_read(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_send(self: Any, bytes_request: bytes) -> None:
        return None

    def mock_recv(self: Any, buf_size: int) -> bytes:
        return b"\x03\x00\x00'\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x02\x00\x12\x00\x00\x04\x03\xff\x03\x00\x01\x01\x00\xff\x03\x00\x01\x01\x00\xff\x05\x00\x10\x00\x00"

    monkeypatch.setattr("socket.socket.send", mock_send)
    monkeypatch.setattr("socket.socket.recv", mock_recv)

    # Ensure socket is initialized
    client.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    tags = ["DB1,X0.0", "DB1,X0.1", "DB2,I2"]
    result = client.read(tags, optimize=False)
    assert result == [True, True, 0]


def test_read_optimized(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_send(self: Any, bytes_request: bytes) -> None:
        return None

    def mock_recv(self: Any, buf_size: int) -> bytes:
        return b"\x03\x00\x00!\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x02\x00\x0c\x00\x00\x04\x02\xff\x03\x00\x01\x01\x00\xff\x05\x00\x10\x00\x00"

    monkeypatch.setattr("socket.socket.send", mock_send)
    monkeypatch.setattr("socket.socket.recv", mock_recv)

    # Ensure socket is initialized
    client.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    tags = ["DB1,X0.1", "DB2,I2"]
    result = client.read(tags, optimize=True)
    assert result == [True, 0]


def test_write(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_send(self: Any, bytes_request: bytes) -> None:
        return None

    def mock_recv(self: Any, buf_size: int) -> bytes:
        return b"\x03\x00\x00\x18\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x02\x00\x03\x00\x00\x05\x03\xff\xff\xff"

    monkeypatch.setattr("socket.socket.send", mock_send)
    monkeypatch.setattr("socket.socket.recv", mock_recv)

    # Ensure socket is initialized
    client.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    tags = ["DB1,X0.0", "DB1,X0.1", "DB2,I2"]
    values = [False, True, 69]

    client.write(tags, values)
