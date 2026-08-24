"""S7CommPlus ISO-on-TCP transport with TLS tunneled in COTP."""

import logging
import socket
import ssl
import struct
import threading
from dataclasses import dataclass
from types import TracebackType
from typing import Type, cast

from ..errors import (
    S7CommPlusProtocolError,
    S7CommPlusSessionError,
    S7CommPlusTLSError,
    S7CommPlusUnsupportedSecurityError,
    S7ConnectionError,
    S7TimeoutError,
)
from .codec import (
    encode_frame,
    encode_object_qualifier,
    encode_request_header,
    parse_response,
)
from .protocol import (
    DEFAULT_PORT,
    LOCAL_TSAP,
    MAX_PACKET_SIZE,
    READ_FUNCTION_CODES,
    REMOTE_TSAP,
    DataType,
    FunctionCode,
    ProtocolVersion,
)
from .vlq import decode_uint32, decode_uint64, encode_uint32

logger = logging.getLogger(__name__)
_S7_CIPHERS = "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256"
_MAX_TLS_BUFFER = MAX_PACKET_SIZE + 64 * 1024
MAX_REASSEMBLED_FRAGMENTS = 4096
MAX_REASSEMBLED_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class _RequestContext:
    """Immutable metadata needed to validate one matching response."""

    sequence_number: int
    request_integrity_id: int | None
    function_code: int
    is_read: bool


def _cotp_connection_request() -> bytes:
    parameters = (
        b"\xc1\x02"
        + struct.pack(">H", LOCAL_TSAP)
        + b"\xc2"
        + bytes((len(REMOTE_TSAP),))
        + REMOTE_TSAP
        + b"\xc0\x01\x0a"
    )
    cotp = bytes((6 + len(parameters), 0xE0)) + b"\0\0\0\1\0" + parameters
    return b"\x03\x00" + struct.pack(">H", len(cotp) + 4) + cotp


def _skip_value(data: bytes, pos: int, datatype: int, flags: int) -> int:
    """Return the bounded end of one typed value in a PObject tree."""
    if flags & 0x10:
        count, used = decode_uint32(data, pos)
        pos += used
        sizes = {1: 1, 2: 1, 6: 1, 10: 1, 3: 2, 7: 2, 11: 2, 14: 4, 15: 8, 16: 8, 18: 4}
        size = sizes.get(datatype)
        if size is None:
            for _ in range(count):
                _, used = decode_uint32(data, pos)
                pos += used
        else:
            pos += count * size
    elif datatype in (0,):
        pass
    elif datatype in (1, 2, 6, 10):
        pos += 1
    elif datatype in (3, 7, 11):
        pos += 2
    elif datatype in (4, 8, 19):
        _, used = decode_uint32(data, pos)
        pos += used
    elif datatype in (5, 9, 17):
        _, used = decode_uint64(data, pos)
        pos += used
    elif datatype in (12, 14):
        pos += 4
    elif datatype in (13, 15, 16, 18):
        pos += 8 if datatype != 18 else 4
    elif datatype in (20, 21):
        length, used = decode_uint32(data, pos)
        pos += used + length
    elif datatype == 23:
        pos += 4
        while pos < len(data) and data[pos]:
            _, used = decode_uint32(data, pos)
            pos += used
            if pos + 2 > len(data):
                raise S7CommPlusProtocolError("truncated session-version struct")
            subflags, subtype = data[pos : pos + 2]
            pos = _skip_value(data, pos + 2, subtype, subflags)
        pos += 1
    else:
        raise S7CommPlusProtocolError(
            f"unsupported session attribute datatype 0x{datatype:02x}"
        )
    if pos > len(data):
        raise S7CommPlusProtocolError("truncated session attribute")
    return pos


def _find_server_session_version(data: bytes) -> bytes | None:
    # Attribute marker A3 followed by canonical VLQ 306 (82 32).
    needle = b"\xa3" + encode_uint32(306)
    start = data.find(needle)
    if start < 0:
        return None
    value = start + len(needle)
    if value + 2 > len(data):
        raise S7CommPlusProtocolError("truncated ServerSessionVersion")
    end = _skip_value(data, value + 2, data[value + 1], data[value])
    return bytes(data[value:end])


class S7CommPlusConnection:
    """Own one serialized S7CommPlus TLS/V2 session."""

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
        self._ssl_object: ssl.SSLObject | None = None
        self._incoming_bio: ssl.MemoryBIO | None = None
        self._outgoing_bio: ssl.MemoryBIO | None = None
        self._plain_buffer = bytearray()
        self.session_id = 0
        self.protocol_version = 0
        self.negotiated_initial_version = 0
        self._sequence = 0
        self._tls_active = False
        self._ready = False
        self._integrity_read = self._integrity_write = 0
        self._with_integrity = False
        self.protection_level: int | None = None
        self.last_response = b""

    @property
    def tls_active(self) -> bool:
        return self._tls_active

    @property
    def connected(self) -> bool:
        return self._ready and self._socket is not None

    @property
    def integrity_id_read(self) -> int:
        return self._integrity_read

    @property
    def integrity_id_write(self) -> int:
        return self._integrity_write

    def _reset(self) -> None:
        sock = self._socket
        sslobj, self._ssl_object = self._ssl_object, None
        if sslobj is not None and self._tls_active:
            try:
                sslobj.unwrap()
                self._flush_tls()
            except (OSError, ssl.SSLError, S7ConnectionError):
                pass
        self._socket = None
        self._incoming_bio = self._outgoing_bio = None
        self._plain_buffer.clear()
        self.session_id = self.protocol_version = self.negotiated_initial_version = (
            self._sequence
        ) = 0
        self._tls_active = self._ready = self._with_integrity = False
        self._integrity_read = self._integrity_write = 0
        self.protection_level = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def connect(
        self,
        *,
        use_tls: bool = False,
        tls_ca: str | None = None,
        tls_cert: str | None = None,
        tls_key: str | None = None,
        tls_verify: bool = False,
    ) -> None:
        """Establish COTP, InitSSL, TLS, CreateObject, and the V2 session."""
        with self._lock:
            self._reset()
            self.last_response = b""
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
                initial, _ = cast(
                    tuple[int, bytes],
                    self._exchange(
                        FunctionCode.INIT_SSL,
                        struct.pack(">I", 0),
                        0,
                        flags=0x30,
                        version=1,
                        accept_any_version=True,
                    ),
                )
                self.negotiated_initial_version = initial
                if not use_tls:
                    raise S7CommPlusUnsupportedSecurityError(
                        "this backend requires the verified TLS/V2 session; reconnect with use_tls=True"
                    )
                self._activate_tls(tls_ca, tls_cert, tls_key, tls_verify)
                version, response = cast(
                    tuple[int, bytes],
                    self._exchange(
                        FunctionCode.CREATE_OBJECT,
                        self._create_object_payload(),
                        288,
                        version=1,
                        accept_any_version=True,
                    ),
                )
                status, used = decode_uint64(response)
                if used >= len(response):
                    raise S7CommPlusProtocolError(
                        "CreateObject response is missing object count"
                    )
                count = response[used]
                used += 1
                if count < 1 or count > 16:
                    raise S7CommPlusProtocolError(
                        "CreateObject returned invalid object count"
                    )
                ids = []
                for _ in range(count):
                    oid, consumed = decode_uint32(response, used)
                    used += consumed
                    ids.append(oid)
                if not ids[0]:
                    raise S7CommPlusProtocolError(
                        "PLC returned an invalid zero session ID"
                    )
                if status:
                    raise S7CommPlusSessionError(
                        f"CreateObject failed with status 0x{status:x}",
                        error_code=status,
                    )
                session_version = _find_server_session_version(response[used:])
                if session_version is None:
                    raise S7CommPlusSessionError(
                        "CreateObject response omitted ServerSessionVersion"
                    )
                self.session_id = ids[0]
                # TLS setup is deliberately V2 even though InitSSL/CreateObject frame as V1.
                self.protocol_version = ProtocolVersion.V2
                self._setup_session(session_version)
                self._with_integrity = True
                self._integrity_read = self._integrity_write = 0
                self._ready = True
                self._read_protection_level()
                logger.info(
                    "S7CommPlus TLS/V2 session ready (initial=V%s session=0x%08x)",
                    version,
                    self.session_id,
                )
            except socket.timeout as exc:
                self._reset()
                raise S7TimeoutError(
                    f"S7CommPlus connection to {self.host} timed out"
                ) from exc
            except (
                S7CommPlusProtocolError,
                S7CommPlusSessionError,
                S7CommPlusTLSError,
                S7CommPlusUnsupportedSecurityError,
                S7ConnectionError,
                S7TimeoutError,
            ):
                self._reset()
                raise
            except OSError as exc:
                self._reset()
                raise S7ConnectionError(
                    f"could not connect to S7CommPlus PLC {self.host}:{self.port}"
                ) from exc
            except Exception as exc:
                self._reset()
                raise S7CommPlusProtocolError(
                    "failed to establish S7CommPlus session"
                ) from exc

    @staticmethod
    def _create_object_payload() -> bytes:
        def wstring(attribute: int, value: str) -> bytes:
            encoded = value.encode()
            return (
                b"\xa3"
                + encode_uint32(attribute)
                + bytes((0, 0x15))
                + encode_uint32(len(encoded))
                + encoded
            )

        name = "pyS7"
        payload = bytearray(struct.pack(">I", 285))
        payload += bytes((0, 4, 0)) + struct.pack(">I", 0)
        payload += b"\xa1" + struct.pack(">I", 211) + encode_uint32(287) + b"\0\0"
        for aid, value in (
            (233, name),
            (289, f"1:::6.0::{name}"),
            (296, name),
            (297, ""),
            (298, name),
        ):
            payload += wstring(aid, value)
        payload += b"\xa3" + encode_uint32(299) + bytes((0, 4)) + encode_uint32(1)
        payload += (
            b"\xa3"
            + encode_uint32(300)
            + bytes((0, 0x12))
            + struct.pack(">I", 0x80C3C901)
            + wstring(301, "")
        )
        payload += (
            b"\xa1"
            + struct.pack(">I", 211)
            + encode_uint32(255)
            + b"\0\0"
            + wstring(233, "SubscriptionContainer")
            + b"\xa2\xa2"
            + struct.pack(">I", 0)
        )
        return bytes(payload)

    def _setup_session(self, value: bytes) -> None:
        payload = (
            struct.pack(">I", self.session_id)
            + encode_uint32(1)
            + encode_uint32(1)
            + encode_uint32(306)
            + encode_uint32(1)
            + value
            + b"\0"
            + encode_object_qualifier(ProtocolVersion.V2)
            + struct.pack(">I", 0)
        )
        response = cast(
            bytes,
            self._exchange(
                FunctionCode.SET_MULTI_VARIABLES,
                payload,
                self.session_id,
                flags=0x34,
                version=ProtocolVersion.V2,
            ),
        )
        status, _ = decode_uint64(response)
        if status:
            raise S7CommPlusSessionError(
                f"SetupSession failed with status 0x{status:x}", error_code=status
            )

    def _read_protection_level(self) -> None:
        payload = (
            struct.pack(">I", self.session_id)
            + bytes((0x20, DataType.UDINT, 1))
            + encode_uint32(1842)
            + encode_object_qualifier(ProtocolVersion.V2)
            + struct.pack(">H", 1)
            + struct.pack(">I", 0)
        )
        response = self.request(FunctionCode.GET_VAR_SUBSTREAMED, payload)
        status, pos = decode_uint64(response)
        if status or pos + 3 > len(response):
            logger.warning("PLC did not report an effective protection level")
            return
        pos += 1
        if response[pos : pos + 2] != bytes((0, DataType.UDINT)):
            logger.warning("PLC did not report an effective protection level")
            return
        self.protection_level, _ = decode_uint32(response, pos + 2)

    def disconnect(self) -> None:
        with self._lock:
            self._reset()

    def request(
        self, function: int, payload: bytes, *, integrity_tail: int = 4
    ) -> bytes:
        with self._lock:
            if not self.connected:
                raise S7ConnectionError("S7CommPlus client is not connected")
            is_read = function in READ_FUNCTION_CODES
            iid = self._integrity_read if is_read else self._integrity_write
            if self._with_integrity:
                if integrity_tail < 0 or len(payload) < integrity_tail:
                    raise S7CommPlusProtocolError(
                        "request has no IntegrityId insertion point"
                    )
                split = len(payload) - integrity_tail
                payload = payload[:split] + encode_uint32(iid) + payload[split:]
            sequence = self._sequence
            context = _RequestContext(
                sequence, iid if self._with_integrity else None, function, is_read
            )
            if self._with_integrity:
                logger.debug(
                    "V2 request: function=0x%04x seq=%d iid=%d",
                    function,
                    sequence,
                    iid,
                )
                # Consumed requests are never retried with a reused IntegrityId.
                if is_read:
                    self._integrity_read = (iid + 1) & 0xFFFFFFFF
                else:
                    self._integrity_write = (iid + 1) & 0xFFFFFFFF
            try:
                result = cast(
                    bytes,
                    self._exchange(
                        function,
                        payload,
                        self.session_id,
                        flags=(
                            0x34
                            if function
                            in (FunctionCode.GET_MULTI_VARIABLES, FunctionCode.EXPLORE)
                            else 0x36
                        ),
                        version=self.protocol_version,
                        context=context,
                    ),
                )
                if self._with_integrity:
                    result = self._remove_response_integrity_trailer(result, context)
                return result
            except socket.timeout as exc:
                self._reset()
                raise S7TimeoutError("S7CommPlus request timed out") from exc
            except (OSError, ssl.SSLError) as exc:
                self._reset()
                raise S7ConnectionError("S7CommPlus transport failed") from exc
            except (S7CommPlusProtocolError, S7CommPlusSessionError):
                # A transmitted request with an unusable response leaves the
                # peer's IntegrityId state uncertain.  Require a fresh session.
                self._reset()
                raise

    @staticmethod
    def _remove_response_integrity_trailer(
        payload: bytes, context: _RequestContext
    ) -> bytes:
        """Validate and remove the V2 session trailer from an application payload.

        V2 responses contain ``sequence + request IntegrityId`` as a VLQ,
        immediately before a four-byte zero fill. Keeping this here makes the session the
        sole owner of both IntegrityId counters and leaves operation codecs to
        parse only their application data.
        """
        if context.request_integrity_id is None:
            raise S7CommPlusProtocolError("response did not expect an IntegrityId")
        expected = (context.sequence_number + context.request_integrity_id) & 0xFFFFFFFF
        encoded_length = len(encode_uint32(expected))
        if len(payload) < encoded_length + 4:
            raise S7CommPlusProtocolError("truncated V2 response integrity trailer")
        if payload[-4:] != b"\0\0\0\0":
            raise S7CommPlusProtocolError("invalid V2 response trailer fill")
        start = len(payload) - 4 - encoded_length
        actual, consumed = decode_uint32(payload, start)
        if consumed != encoded_length or start + consumed != len(payload) - 4:
            raise S7CommPlusProtocolError("invalid V2 response IntegrityId encoding")
        if actual != expected:
            raise S7CommPlusProtocolError("unexpected V2 response IntegrityId")
        logger.debug(
            "V2 response: seq=%d iid=%d expected=%d",
            context.sequence_number,
            actual,
            expected,
        )
        return payload[:start]

    def _exchange(
        self,
        function: int,
        payload: bytes,
        session_id: int,
        flags: int = 0x36,
        version: int = 1,
        accept_any_version: bool = False,
        context: _RequestContext | None = None,
    ) -> bytes | tuple[int, bytes]:
        sequence = context.sequence_number if context is not None else self._sequence
        if context is not None and context.function_code != function:
            raise S7CommPlusProtocolError("request function context does not match")
        if sequence != self._sequence:
            raise S7CommPlusProtocolError("request sequence context is stale")
        self._sequence = (sequence + 1) & 0xFFFF
        packet = encode_request_header(function, sequence, session_id, flags) + payload
        self._send_application(encode_frame(version, packet))
        response_version, body = self._receive_application()
        self.last_response = body
        if response_version != version and not accept_any_version:
            raise S7CommPlusProtocolError("unexpected S7CommPlus protocol version")
        parsed = parse_response(body, function, sequence)
        return (response_version, parsed) if accept_any_version else parsed

    def _activate_tls(
        self, ca: str | None, cert: str | None, key: str | None, verify: bool
    ) -> None:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.set_ciphers(_S7_CIPHERS)
            for group in ("X25519", "prime256v1"):
                try:
                    ctx.set_ecdh_curve(group)
                    break
                except (ssl.SSLError, ValueError):
                    continue
            else:
                raise S7CommPlusTLSError(
                    "OpenSSL supports neither X25519 nor prime256v1"
                )
            ctx.options |= ssl.OP_NO_TICKET
            if cert or key:
                if not cert or not key:
                    raise S7CommPlusTLSError("both tls_cert and tls_key are required")
                ctx.load_cert_chain(cert, key)
            if verify:
                if ca:
                    ctx.load_verify_locations(ca)
                else:
                    ctx.load_default_certs()
                ctx.check_hostname = True
                ctx.verify_mode = ssl.CERT_REQUIRED
            else:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                logger.warning(
                    "PLC certificate verification is explicitly disabled (tls_verify=False)"
                )
            self._incoming_bio, self._outgoing_bio = ssl.MemoryBIO(), ssl.MemoryBIO()
            self._ssl_object = ctx.wrap_bio(
                self._incoming_bio,
                self._outgoing_bio,
                server_hostname=self.host if verify else None,
            )
            while True:
                try:
                    self._ssl_object.do_handshake()
                    break
                except ssl.SSLWantReadError:
                    self._flush_tls()
                    self._feed_tls()
                except ssl.SSLWantWriteError:
                    self._flush_tls()
            self._flush_tls()
            self._tls_active = True
        except S7CommPlusTLSError:
            raise
        except (ssl.SSLError, OSError, ValueError) as exc:
            raise S7CommPlusTLSError(
                "S7CommPlus TLS handshake/configuration failed"
            ) from exc

    def _flush_tls(self) -> None:
        assert self._outgoing_bio is not None
        while self._outgoing_bio.pending:
            data = self._outgoing_bio.read(min(self._outgoing_bio.pending, 0xFFFF - 7))
            if data:
                self._send_cotp(data)

    def _feed_tls(self) -> None:
        assert self._incoming_bio is not None
        data = self._receive_cotp()
        if not data:
            raise S7CommPlusTLSError("socket closed during TLS handshake")
        if self._incoming_bio.pending + len(data) > _MAX_TLS_BUFFER:
            raise S7CommPlusProtocolError("TLS input exceeds buffer limit")
        self._incoming_bio.write(data)

    def _send_application(self, data: bytes) -> None:
        if self._ssl_object:
            view = memoryview(data)
            while view:
                try:
                    used = self._ssl_object.write(view)
                    view = view[used:]
                    self._flush_tls()
                except ssl.SSLWantWriteError:
                    self._flush_tls()
        else:
            self._send_cotp(data)

    def _receive_application(self) -> tuple[int, bytes]:
        """Reassemble S7CommPlus fragments above TLS/COTP framing."""
        version: int | None = None
        result = bytearray()
        fragments = 0
        while True:
            if len(self._plain_buffer) >= 4:
                protocol_id, fragment_version, length = struct.unpack_from(
                    ">BBH", self._plain_buffer
                )
                if protocol_id != 0x72:
                    raise S7CommPlusProtocolError("invalid S7CommPlus fragment header")
                try:
                    ProtocolVersion(fragment_version)
                except ValueError as exc:
                    raise S7CommPlusProtocolError(
                        "invalid S7CommPlus fragment version"
                    ) from exc
                if version is None:
                    version = fragment_version
                elif fragment_version != version:
                    raise S7CommPlusProtocolError("S7CommPlus fragment version changed")
                if length == 0:
                    del self._plain_buffer[:4]
                    if not fragments:
                        raise S7CommPlusProtocolError(
                            "S7CommPlus response has no data fragment"
                        )
                    return version, bytes(result)
                if len(self._plain_buffer) >= 4 + length:
                    result.extend(self._plain_buffer[4 : 4 + length])
                    del self._plain_buffer[: 4 + length]
                    fragments += 1
                    if fragments > MAX_REASSEMBLED_FRAGMENTS:
                        raise S7CommPlusProtocolError(
                            "S7CommPlus response has too many fragments"
                        )
                    if len(result) > MAX_REASSEMBLED_BYTES:
                        raise S7CommPlusProtocolError(
                            "S7CommPlus reassembled response exceeds limit"
                        )
                    continue
            if self._ssl_object:
                try:
                    chunk = self._ssl_object.read(65536)
                    if not chunk:
                        raise S7ConnectionError("TLS peer closed connection")
                    self._plain_buffer.extend(chunk)
                except ssl.SSLWantReadError:
                    self._feed_tls()
            else:
                chunk = self._receive_cotp()
                if not chunk:
                    raise S7CommPlusProtocolError(
                        "truncated S7CommPlus fragment sequence"
                    )
                self._plain_buffer.extend(chunk)
            if len(self._plain_buffer) > max(_MAX_TLS_BUFFER, 0xFFFF + 4):
                raise S7CommPlusProtocolError("decrypted data exceeds buffer limit")

    def _send_cotp(self, data: bytes) -> None:
        if self._socket is None:
            raise S7ConnectionError("transport is disconnected")
        if len(data) > 0xFFFF - 7:
            raise S7CommPlusProtocolError("COTP payload exceeds limit")
        self._socket.sendall(
            b"\x03\x00" + struct.pack(">H", len(data) + 7) + b"\x02\xf0\x80" + data
        )

    def _receive_tpkt(self) -> bytes:
        header = self._recv_exact(4)
        if header[:2] != b"\x03\x00":
            raise S7CommPlusProtocolError("invalid TPKT header")
        length = struct.unpack_from(">H", header, 2)[0]
        if length < 7 or length > min(MAX_PACKET_SIZE, 0xFFFF):
            raise S7CommPlusProtocolError("invalid TPKT packet length")
        return self._recv_exact(length - 4)

    def _receive_cotp(self) -> bytes:
        packet = self._receive_tpkt()
        if packet[:3] != b"\x02\xf0\x80":
            raise S7CommPlusProtocolError("invalid COTP data header")
        return packet[3:]

    def _recv_exact(self, length: int) -> bytes:
        if self._socket is None:
            raise S7ConnectionError("transport is disconnected")
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
        self.connect(use_tls=True)
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()
