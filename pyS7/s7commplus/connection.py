"""Synchronous ISO-on-TCP transport and unauthenticated V1 session setup."""

import socket
import struct
import threading
from types import TracebackType
from typing import Type

from ..errors import S7CommPlusProtocolError, S7ConnectionError, S7TimeoutError
from .codec import decode_frame, encode_frame, encode_request_header, parse_response
from .protocol import (
    DEFAULT_PORT,
    LOCAL_TSAP,
    MAX_PACKET_SIZE,
    REMOTE_TSAP,
    FunctionCode,
    ProtocolVersion,
)
from .vlq import decode_uint32, decode_uint64, encode_uint32


def _cotp_connection_request() -> bytes:
    parameters = (
        b"\xc1\x02"
        + struct.pack(">H", LOCAL_TSAP)
        + b"\xc2"
        + bytes((len(REMOTE_TSAP),))
        + REMOTE_TSAP
        + b"\xc0\x01\x0a"
    )
    cotp = bytes((6 + len(parameters), 0xE0)) + b"\x00\x00\x00\x01\x00" + parameters
    return b"\x03\x00" + struct.pack(">H", len(cotp) + 4) + cotp


class S7CommPlusConnection:
    """Own one S7CommPlus socket; all request/response pairs are serialized."""

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0
    ) -> None:
        if not host:
            raise ValueError("host must not be empty")
        if not 1 <= port <= 65535 or timeout <= 0:
            raise ValueError("invalid port or timeout")
        self.host, self.port, self.timeout = host, port, timeout
        self._socket: socket.socket | None = None
        self._lock = threading.RLock()
        self.session_id = 0
        self.protocol_version = 0
        self._sequence = 0

    @property
    def connected(self) -> bool:
        return self._socket is not None and self.session_id != 0

    def _reset(self) -> None:
        sock, self._socket = self._socket, None
        self.session_id = self.protocol_version = self._sequence = 0
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def connect(self) -> None:
        """Connect, negotiate COTP, send InitSSL, then create a V1 session."""
        with self._lock:
            self._reset()
            try:
                self._socket = socket.create_connection(
                    (self.host, self.port), self.timeout
                )
                self._socket.settimeout(self.timeout)
                self._socket.sendall(_cotp_connection_request())
                confirmation = self._receive_tpkt()
                if len(confirmation) < 7 or confirmation[1] != 0xD0:
                    raise S7CommPlusProtocolError(
                        "PLC did not return a COTP connection confirmation"
                    )
                self._exchange(
                    FunctionCode.INIT_SSL,
                    struct.pack(">I", 0),
                    session_id=0,
                    flags=0x30,
                    version=1,
                )
                response = self._exchange(
                    FunctionCode.CREATE_OBJECT,
                    self._create_object_payload(),
                    session_id=288,
                    version=1,
                )
                status, used = decode_uint64(response)
                if status:
                    raise S7ConnectionError(
                        f"S7CommPlus session creation failed with status 0x{status:x}"
                    )
                if used >= len(response):
                    raise S7CommPlusProtocolError(
                        "session response is missing its object count"
                    )
                count = response[used]
                if not count:
                    raise S7CommPlusProtocolError(
                        "session response contains no session ID"
                    )
                session, _ = decode_uint32(response, used + 1)
                if not session:
                    raise S7CommPlusProtocolError(
                        "PLC returned an invalid zero session ID"
                    )
                self.session_id = session
                self.protocol_version = ProtocolVersion.V1
            except socket.timeout as exc:
                self._reset()
                raise S7TimeoutError(
                    f"S7CommPlus connection to {self.host} timed out"
                ) from exc
            except (S7CommPlusProtocolError, S7ConnectionError):
                self._reset()
                raise
            except OSError as exc:
                self._reset()
                raise S7ConnectionError(
                    f"could not connect to S7CommPlus PLC {self.host}:{self.port}"
                ) from exc
            except Exception as exc:
                self._reset()
                raise S7ConnectionError(
                    f"could not establish S7CommPlus session with {self.host}"
                ) from exc

    @staticmethod
    def _create_object_payload() -> bytes:
        # NullServerSession PObject, deliberately minimal for unauthenticated V1 PLCs.
        return (
            struct.pack(">I", 285)
            + bytes((0, 4, 0))
            + struct.pack(">I", 0)
            + b"\xa1"
            + struct.pack(">I", 211)
            + encode_uint32(287)
            + b"\0\0\xa3"
            + encode_uint32(300)
            + bytes((0, 0x12))
            + struct.pack(">I", 0x80C3C901)
            + b"\xa2"
            + struct.pack(">I", 0)
        )

    def disconnect(self) -> None:
        with self._lock:
            self._reset()

    def request(self, function: int, payload: bytes) -> bytes:
        with self._lock:
            if not self.connected:
                raise S7ConnectionError("S7CommPlus client is not connected")
            try:
                return self._exchange(
                    function, payload, self.session_id, version=self.protocol_version
                )
            except (S7CommPlusProtocolError, S7ConnectionError, S7TimeoutError):
                self._reset()
                raise
            except OSError as exc:
                self._reset()
                raise S7ConnectionError("S7CommPlus transport failed") from exc

    def _exchange(
        self,
        function: int,
        payload: bytes,
        session_id: int,
        flags: int = 0x36,
        version: int = 1,
    ) -> bytes:
        if self._socket is None:
            raise S7ConnectionError("S7CommPlus transport is not connected")
        sequence = self._sequence
        self._sequence = (sequence + 1) & 0xFFFF
        packet = encode_request_header(function, sequence, session_id, flags) + payload
        self._send_cotp(encode_frame(version, packet))
        response_version, body = decode_frame(self._receive_cotp())
        if response_version != version:
            raise S7CommPlusProtocolError("unexpected S7CommPlus protocol version")
        return parse_response(body, function, sequence)

    def _send_cotp(self, data: bytes) -> None:
        assert self._socket is not None
        packet = b"\x03\x00" + struct.pack(">H", len(data) + 7) + b"\x02\xf0\x80" + data
        self._socket.sendall(packet)

    def _receive_tpkt(self) -> bytes:
        header = self._recv_exact(4)
        if header[:2] != b"\x03\x00":
            raise S7CommPlusProtocolError("invalid TPKT header")
        length = struct.unpack_from(">H", header, 2)[0]
        if length < 7 or length > MAX_PACKET_SIZE:
            raise S7CommPlusProtocolError("invalid TPKT packet length")
        return self._recv_exact(length - 4)

    def _receive_cotp(self) -> bytes:
        packet = self._receive_tpkt()
        if packet[:3] != b"\x02\xf0\x80":
            raise S7CommPlusProtocolError("invalid COTP data header")
        return packet[3:]

    def _recv_exact(self, length: int) -> bytes:
        assert self._socket is not None
        result = bytearray()
        try:
            while len(result) < length:
                chunk = self._socket.recv(length - len(result))
                if not chunk:
                    raise S7ConnectionError(
                        "connection closed in the middle of a frame"
                    )
                result.extend(chunk)
        except socket.timeout as exc:
            raise S7TimeoutError(
                "timed out while receiving an S7CommPlus frame"
            ) from exc
        return bytes(result)

    def __enter__(self) -> "S7CommPlusConnection":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()
