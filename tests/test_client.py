import socket
import threading
import time
from typing import Any, Callable, Dict, Optional, cast

import pytest

from pyS7.client import S7Client
from pyS7.constants import MAX_JOB_CALLED, MAX_JOB_CALLING, MAX_PDU, ConnectionType


@pytest.fixture
def client() -> S7Client:
    client = S7Client("192.168.100.10", 0, 1, ConnectionType.S7Basic, 102, 5)
    return client


def _mock_recv_factory(*messages: bytes) -> Callable[[Any, int], bytes]:
    buffers = [memoryview(message) for message in messages]
    current: Optional[memoryview] = None

    def _mock_recv(self: Any, buf_size: int) -> bytes:
        nonlocal current

        if buf_size <= 0:
            return b""

        while current is None or len(current) == 0:
            if not buffers:
                return b""
            current = buffers.pop(0)

        if len(current) <= buf_size:
            chunk = current.tobytes()
            current = None
            return chunk

        chunk = current[:buf_size].tobytes()
        current = current[buf_size:]
        return chunk

    return _mock_recv


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

    def mock_sendall(self: Any, bytes_request: bytes) -> None:
        return None

    connection_response = (
        b"\x03\x00\x00\x1b\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x00\x08\x00\x08\x03\xc0"
    )
    pdu_response = (
        b"\x03\x00\x00\x1b\x02\xf0\x802\x07\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x01\x00\x01\x03\xc0\x00"
    )

    monkeypatch.setattr("socket.socket.connect", mock_connect)
    monkeypatch.setattr("socket.socket.sendall", mock_sendall)
    monkeypatch.setattr(
        "socket.socket.recv", _mock_recv_factory(connection_response, pdu_response)
    )

    client.connect()

    assert client.socket is not None
    assert client.socket.gettimeout() == 5


def test_client_disconnect(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("socket.socket.shutdown", lambda *args, **kwargs: None)
    monkeypatch.setattr("socket.socket.close", lambda *args, **kwargs: None)

    client.disconnect()

    assert client.socket is None


def test_read(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_sendall(self: Any, bytes_request: bytes) -> None:
        return None

    read_response = (
        b"\x03\x00\x00'\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x02\x00\x12\x00\x00\x04\x03\xff\x03\x00\x01\x01\x00\xff\x03\x00\x01\x01\x00\xff\x05\x00\x10\x00\x00"
    )

    monkeypatch.setattr("socket.socket.sendall", mock_sendall)
    monkeypatch.setattr("socket.socket.recv", _mock_recv_factory(read_response))

    # Ensure socket is initialized
    client.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    tags = ["DB1,X0.0", "DB1,X0.1", "DB2,I2"]
    result = client.read(tags, optimize=False)
    assert result == [True, True, 0]


def test_read_returns_empty_list_for_no_tags(
    client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*_: Any, **__: Any) -> Any:
        raise AssertionError("read should not prepare requests when no tags are provided")

    client.socket = cast(socket.socket, object())

    monkeypatch.setattr("pyS7.client.prepare_optimized_requests", unexpected)
    monkeypatch.setattr("pyS7.client.S7Client._S7Client__send", unexpected)

    result = client.read(())

    assert result == []


def test_read_optimized(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_sendall(self: Any, bytes_request: bytes) -> None:
        return None

    read_response = (
        b"\x03\x00\x00!\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x02\x00\x0c\x00\x00\x04\x02\xff\x03\x00\x01\x01\x00\xff\x05\x00\x10\x00\x00"
    )

    monkeypatch.setattr("socket.socket.sendall", mock_sendall)
    monkeypatch.setattr("socket.socket.recv", _mock_recv_factory(read_response))

    # Ensure socket is initialized
    client.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    tags = ["DB1,X0.1", "DB2,I2"]
    result = client.read(tags, optimize=True)
    assert result == [False, 0]


def test_write(client: S7Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_sendall(self: Any, bytes_request: bytes) -> None:
        return None
    
    write_response = (
        b"\x03\x00\x00\x18\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x02\x00\x03\x00\x00\x05\x03\xff\xff\xff"
    )

    monkeypatch.setattr("socket.socket.sendall", mock_sendall)
    monkeypatch.setattr("socket.socket.recv", _mock_recv_factory(write_response))

    # Ensure socket is initialized
    client.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    tags = ["DB1,X0.0", "DB1,X0.1", "DB2,I2"]
    values = [False, True, 69]

    client.write(tags, values)


class _DummyRequest:
    def __init__(self, payload: bytes) -> None:
        self.request = bytearray(payload)

    def serialize(self) -> bytes:
        return bytes(self.request)


def _tpkt(payload: bytes) -> bytes:
    length = len(payload) + 4
    return b"\x03\x00" + length.to_bytes(2, byteorder="big", signed=False) + payload


class _ResponseStream:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0

    def read(self, size: int) -> bytes:
        end = self._offset + size
        if end > len(self._payload):
            raise AssertionError(
                f"Requested {size} bytes but only {len(self._payload) - self._offset} remaining"
            )

        chunk = self._payload[self._offset : end]
        self._offset = end
        return chunk

    def reset(self) -> None:
        self._offset = 0

    def finished(self) -> bool:
        return self._offset == len(self._payload)


class _SerializingFakeSocket:
    def __init__(self, responses: Dict[bytes, bytes]) -> None:
        self._streams = {request: _ResponseStream(response) for request, response in responses.items()}
        self._current_request: bytes | None = None
        self._current_stream: _ResponseStream | None = None
        self._lock = threading.Lock()
        self._request_ready = threading.Event()

    def sendall(self, data: bytes) -> None:
        with self._lock:
            if self._current_request is not None:
                raise AssertionError("Concurrent send detected")

            try:
                stream = self._streams[data]
            except KeyError as exc:  # pragma: no cover - misconfigured test double
                raise AssertionError(f"Unexpected request payload: {data!r}") from exc

            stream.reset()
            self._current_request = data
            self._current_stream = stream
            self._request_ready.set()

        time.sleep(0.01)

    def recv(self, buf_size: int) -> bytes:
        if not self._request_ready.wait(timeout=0.1):
            raise AssertionError("recv without matching send")

        with self._lock:
            if self._current_stream is None:
                raise AssertionError("recv without matching send")

            chunk = self._current_stream.read(buf_size)
            finished = self._current_stream.finished()

            if finished:
                self._current_request = None
                self._current_stream = None
                self._request_ready.clear()

        time.sleep(0.01)

        return chunk


def test_client_serializes_socket_access(client: S7Client) -> None:
    responses: Dict[bytes, bytes] = {
        b"req-0": _tpkt(b"resp-0"),
        b"req-1": _tpkt(b"resp-1"),
        b"req-2": _tpkt(b"resp-2"),
    }

    client.socket = cast(socket.socket, _SerializingFakeSocket(responses))

    barrier = threading.Barrier(len(responses))
    results: Dict[bytes, bytes] = {}
    errors: list[BaseException] = []

    def worker(payload: bytes) -> None:
        request = _DummyRequest(payload)

        try:
            barrier.wait()
            response = cast(
                Callable[[Any], bytes], getattr(client, "_S7Client__send")
            )(request)
            results[payload] = response
        except BaseException as exc:  # pragma: no cover - surfaced via errors list
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(payload,)) for payload in responses]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert not errors, f"Errors raised during concurrent access: {errors!r}"
    assert results == responses