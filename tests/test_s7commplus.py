import asyncio
import socket
import struct
import threading
import time
from collections import deque

import pytest

from pyS7.errors import (
    S7CommPlusProtocolError,
    S7CommPlusUnsupportedSecurityError,
    S7ConnectionError,
    S7SymbolicAccessError,
    S7TimeoutError,
)
from pyS7.s7commplus import AsyncS7CommPlusClient, S7SymbolicTag, db_access_area
from pyS7.s7commplus.codec import (
    build_symbolic_read,
    decode_frame,
    decode_pvalue,
    encode_frame,
    encode_item_address,
    parse_response,
    parse_symbolic_read,
    parse_symbolic_write,
)
from pyS7.s7commplus.connection import S7CommPlusConnection, _cotp_connection_request
from pyS7.s7commplus.protocol import DataType, FunctionCode, ProtocolVersion
from pyS7.s7commplus.vlq import decode_uint32, decode_uint64, encode_uint32


@pytest.mark.parametrize("value", [0, 0x7F, 0x80, 0x3FFF, 0x4000, 0xFFFFFFFF])
def test_vlq_boundaries(value: int) -> None:
    encoded = encode_uint32(value)
    assert decode_uint32(encoded) == (value, len(encoded))


@pytest.mark.parametrize(
    "invalid", [b"", b"\x80", b"\x90\x80\x80\x80\x00", b"\x80" * 5]
)
def test_vlq_rejects_malformed_values(invalid: bytes) -> None:
    with pytest.raises(S7CommPlusProtocolError):
        decode_uint32(invalid)


def test_uint64_ninth_byte_form() -> None:
    assert decode_uint64(b"\x81\x80\x80\x80\x80\x80\x80\x80\xff") == (
        0x02000000000000FF,
        9,
    )


def test_access_area_and_symbolic_address_encoding() -> None:
    assert db_access_area(1) == 0x8A0E0001
    zero_crc, fields = encode_item_address(db_access_area(1), [0x10], 0)
    nonzero_crc, nested_fields = encode_item_address(
        db_access_area(1), [0x10, 0x103], 0x1234
    )
    assert zero_crc.startswith(b"\x00\x88\xd0\xb8\x80\x01\x02")
    assert nonzero_crc.startswith(b"\xa4\x34")
    assert fields == 5
    assert nested_fields == 6


def test_static_cotp_connection_request_fixture() -> None:
    # Independently described RFC 1006/COTP CR with Siemens' public HMI TSAP.
    fixture = bytes.fromhex(
        "030000241fe00000000100c1020600c210" "53494d415449432d524f4f542d484d49c0010a"
    )
    assert _cotp_connection_request() == fixture


def test_static_v1_symbolic_read_fixture_has_no_integrity_id() -> None:
    # Sanitized V1 GetMultiVariables payload; this is a wire fixture, not a
    # value produced and decoded by the implementation under test.
    fixture = bytes.fromhex(
        "000000000106a43488d0b88001039376108203"
        "000004e88969001200000000896a001300896b00040000000000000000"
    )
    assert build_symbolic_read(db_access_area(1), [0x10, 0x103], 0x1234, 1) == fixture


@pytest.mark.parametrize("sequence", [[], [-1], [0x100000000], [True], range(65)])
def test_malformed_access_sequence_rejected(sequence: object) -> None:
    with pytest.raises(ValueError):
        encode_item_address(db_access_area(1), sequence)  # type: ignore[arg-type]


def test_v1_and_v2_object_qualifiers_differ() -> None:
    v1 = build_symbolic_read(db_access_area(1), [1], 0, ProtocolVersion.V1)
    v2 = build_symbolic_read(db_access_area(1), [1], 0, ProtocolVersion.V2)
    assert v1 != v2
    assert len(v1) > len(v2)


def test_frame_roundtrip_and_validation() -> None:
    frame = encode_frame(ProtocolVersion.V1, b"abc")
    assert decode_frame(frame) == (ProtocolVersion.V1, b"abc")
    with pytest.raises(S7CommPlusProtocolError, match="length"):
        decode_frame(frame[:-1])
    with pytest.raises(S7CommPlusProtocolError, match="header"):
        decode_frame(b"\x32" + frame[1:])


def test_response_header_validation() -> None:
    header = struct.pack(
        ">BHHHHB", 0x32, 0, FunctionCode.GET_MULTI_VARIABLES, 0, 7, 0x36
    )
    assert parse_response(header + b"ok", FunctionCode.GET_MULTI_VARIABLES, 7) == b"ok"
    with pytest.raises(S7CommPlusProtocolError, match="function"):
        parse_response(header, FunctionCode.SET_MULTI_VARIABLES, 7)
    with pytest.raises(S7CommPlusProtocolError, match="header"):
        parse_response(b"\x99" + header[1:], FunctionCode.GET_MULTI_VARIABLES, 7)
    with pytest.raises(S7CommPlusProtocolError, match="truncated"):
        parse_response(b"short", FunctionCode.GET_MULTI_VARIABLES, 7)


def test_successful_symbolic_read_and_item_errors() -> None:
    payload = b"\0\x01" + bytes((0, DataType.BLOB, 3)) + b"abc\0\0"
    assert parse_symbolic_read(payload) == b"abc"
    with pytest.raises(S7SymbolicAccessError) as exc:
        parse_symbolic_read(b"\x05")
    assert exc.value.error_code == 5
    with pytest.raises(S7SymbolicAccessError) as exc:
        parse_symbolic_write(b"\0\x01\x23")
    assert exc.value.error_code == 0x23


@pytest.mark.parametrize(
    ("wire", "expected"),
    [
        ("000100", b"\0"),
        ("00070001", b"\0\1"),
        ("00080001e240", bytes.fromhex("0001e240")),
        ("000e41280000", bytes.fromhex("41280000")),
        ("000c000001f4", bytes.fromhex("000001f4")),
    ],
)
def test_real_plc_scalar_pvalue_fixtures(wire: str, expected: bytes) -> None:
    """Static sanitized BOOL/INT/DINT/REAL/TIME value fixtures."""
    value, used = decode_pvalue(bytes.fromhex(wire), 0)
    assert value == expected
    assert used == len(bytes.fromhex(wire))


def test_real_plc_string_and_wstring_raw_fixtures() -> None:
    string = bytes.fromhex("fe0a54657374537472696e67")
    wstring = bytes.fromhex("00fe000b005400650073007400570073007400720069006e0067")
    assert string[2 : 2 + string[1]].decode("ascii") == "TestString"
    length = int.from_bytes(wstring[2:4], "big")
    assert wstring[4 : 4 + length * 2].decode("utf-16-be") == "TestWstring"


def test_v2_integrity_id_is_central_and_resets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = S7CommPlusConnection("plc")
    connection._socket = FakeSocket([])  # type: ignore[assignment]
    connection._ready = connection._with_integrity = True
    connection.protocol_version = ProtocolVersion.V2
    captured: list[bytes] = []

    def exchange(
        function: int, payload: bytes, *args: object, **kwargs: object
    ) -> bytes:
        captured.append(payload)
        return b"ok"

    monkeypatch.setattr(connection, "_exchange", exchange)
    assert (
        connection.request(FunctionCode.GET_MULTI_VARIABLES, b"body\0\0\0\0") == b"ok"
    )
    assert (
        connection.request(FunctionCode.GET_MULTI_VARIABLES, b"body\0\0\0\0") == b"ok"
    )
    assert captured == [b"body\0\0\0\0\0", b"body\x01\0\0\0\0"]
    assert connection.integrity_id_read == 2
    connection.disconnect()
    assert connection.integrity_id_read == 0


def test_invalid_and_truncated_pvalue() -> None:
    with pytest.raises(S7CommPlusProtocolError, match="truncated"):
        decode_pvalue(b"\0", 0)
    with pytest.raises(S7CommPlusProtocolError, match="datatype"):
        decode_pvalue(b"\0\xff", 0)
    with pytest.raises(S7CommPlusProtocolError, match="truncated"):
        decode_pvalue(bytes((0, DataType.BLOB, 5)) + b"x", 0)


def test_symbolic_tag_is_immutable_and_hashable() -> None:
    tag = S7SymbolicTag(db_access_area(2), (1, 2), name="value")
    assert {tag} == {tag}
    with pytest.raises(AttributeError):
        tag.name = "changed"  # type: ignore[misc]


class FakeSocket:
    def __init__(self, chunks: list[bytes | BaseException]) -> None:
        self.chunks = deque(chunks)
        self.closed = False

    def recv(self, length: int) -> bytes:
        value = self.chunks.popleft()
        if isinstance(value, BaseException):
            raise value
        if len(value) > length:
            self.chunks.appendleft(value[length:])
            return value[:length]
        return value

    def shutdown(self, how: int) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_exact_receive_partial_reads_and_mid_frame_close() -> None:
    connection = S7CommPlusConnection("plc")
    connection._socket = FakeSocket([b"a", b"bc"])  # type: ignore[assignment]
    assert connection._recv_exact(3) == b"abc"
    connection._socket = FakeSocket([b"a", b""])  # type: ignore[assignment]
    with pytest.raises(S7ConnectionError, match="middle"):
        connection._recv_exact(2)


def test_exact_receive_timeout_and_double_disconnect() -> None:
    connection = S7CommPlusConnection("plc")
    fake = FakeSocket([socket.timeout()])
    connection._socket = fake  # type: ignore[assignment]
    with pytest.raises(S7TimeoutError):
        connection._recv_exact(1)
    connection.disconnect()
    connection.disconnect()
    assert fake.closed
    assert not connection.connected


def test_failed_connect_cleans_state(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket([b""])
    fake.sendall = lambda data: None  # type: ignore[attr-defined]
    fake.settimeout = lambda timeout: None  # type: ignore[attr-defined]
    monkeypatch.setattr(socket, "create_connection", lambda *args: fake)
    connection = S7CommPlusConnection("plc")
    with pytest.raises(S7ConnectionError):
        connection.connect()
    assert not connection.connected
    assert connection.session_id == 0
    assert fake.closed


def test_connect_without_tls_rejects_before_session_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSocket([])
    fake.sendall = lambda data: None  # type: ignore[attr-defined]
    fake.settimeout = lambda timeout: None  # type: ignore[attr-defined]
    monkeypatch.setattr(socket, "create_connection", lambda *args: fake)
    connection = S7CommPlusConnection("plc")
    monkeypatch.setattr(connection, "_receive_tpkt", lambda: b"\x1f\xd0\0\0\0\1\0")

    def exchange(*args: object, **kwargs: object) -> object:
        return (ProtocolVersion.V3, b"") if kwargs.get("accept_any_version") else b""

    monkeypatch.setattr(connection, "_exchange", exchange)
    with pytest.raises(S7CommPlusUnsupportedSecurityError):
        connection.connect()
    assert not connection.connected
    assert connection.session_id == 0


@pytest.mark.asyncio
async def test_async_symbolic_read_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncS7CommPlusClient("plc")
    worker_thread = 0

    def blocking_read(*args: object) -> bytes:
        nonlocal worker_thread
        worker_thread = threading.get_ident()
        time.sleep(0.08)
        return b"ok"

    monkeypatch.setattr(client._client, "read_symbolic", blocking_read)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while ticks < 3:
            await asyncio.sleep(0.01)
            ticks += 1

    result, _ = await asyncio.gather(client.read_symbolic(1, [1]), ticker())
    assert result == b"ok"
    assert ticks == 3
    assert worker_thread != threading.get_ident()
