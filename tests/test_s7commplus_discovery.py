import struct

import pytest

from pyS7.errors import S7CommPlusProtocolError
from pyS7.s7commplus.browse import (
    BLOCK_NUMBER_AID,
    DB_CLASS_RID,
    OBJECT_VARIABLE_TYPE_NAME_AID,
    PLC_PROGRAM_RID,
    build_explore_request,
    parse_datablocks,
)
from pyS7.s7commplus.connection import S7CommPlusConnection, _RequestContext
from pyS7.s7commplus.protocol import DataType, FunctionCode, ProtocolVersion
from pyS7.s7commplus.vlq import encode_uint32


def fragment(payload: bytes, length: int | None = None) -> bytes:
    size = len(payload) if length is None else length
    return struct.pack(">BBH", 0x72, ProtocolVersion.V2, size) + payload


TRAILER = fragment(b"")


def test_explore_request_static_encoding() -> None:
    assert build_explore_request(PLC_PROGRAM_RID, (233, 2521)) == bytes.fromhex(
        "00000003 00 01 01 00 00 02 8169 93 59 0000000000"
    )


def test_integrity_tail_five_insertion_and_iid_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = S7CommPlusConnection("plc")
    connection._socket = object()  # type: ignore[assignment]
    connection._ready = connection._with_integrity = True
    connection.protocol_version = ProtocolVersion.V2
    captured = b""

    def exchange(
        function: int, payload: bytes, *args: object, **kwargs: object
    ) -> bytes:
        nonlocal captured
        captured = payload
        context = kwargs["context"]
        assert isinstance(context, _RequestContext)
        return b"answer" + encode_uint32(context.sequence_number) + bytes(4)

    monkeypatch.setattr(connection, "_exchange", exchange)
    assert (
        connection.request(FunctionCode.EXPLORE, b"body" + bytes(5), integrity_tail=5)
        == b"answer"
    )
    assert captured == b"body" + bytes(6)


def receiving(chunks: list[bytes]) -> S7CommPlusConnection:
    connection = S7CommPlusConnection("plc")
    iterator = iter(chunks)
    connection._receive_cotp = lambda: next(iterator)  # type: ignore[method-assign]
    return connection


def test_single_and_multi_frame_response_with_zero_trailer() -> None:
    assert receiving([fragment(b"one") + TRAILER])._receive_application() == (2, b"one")
    assert receiving(
        [fragment(b"one")[:2], fragment(b"one")[2:] + fragment(b"two"), TRAILER]
    )._receive_application() == (2, b"onetwo")


def test_truncated_fragment_is_rejected() -> None:
    connection = receiving([fragment(b"x", 4), b""])
    with pytest.raises(S7CommPlusProtocolError, match="truncated"):
        connection._receive_application()


def test_excessive_fragment_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pyS7.s7commplus.connection.MAX_REASSEMBLED_FRAGMENTS", 1)
    with pytest.raises(S7CommPlusProtocolError, match="too many"):
        receiving([fragment(b"a") + fragment(b"b") + TRAILER])._receive_application()


def test_excessive_response_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pyS7.s7commplus.connection.MAX_REASSEMBLED_BYTES", 2)
    with pytest.raises(S7CommPlusProtocolError, match="exceeds"):
        receiving([fragment(b"abc") + TRAILER])._receive_application()


def pobj(
    relation: int, class_id: int, name: bytes = b"", number: int | None = None
) -> bytes:
    value = b"\xa1" + struct.pack(">I", relation) + encode_uint32(class_id) + b"\0\0"
    if name:
        value += b"\xa3" + encode_uint32(OBJECT_VARIABLE_TYPE_NAME_AID)
        value += bytes((0, DataType.WSTRING)) + encode_uint32(len(name)) + name
    if number is not None:
        value += b"\xa3" + encode_uint32(BLOCK_NUMBER_AID)
        value += bytes((0, DataType.UDINT)) + encode_uint32(number)
    return value + b"\xa2"


def test_valid_db_relation_and_unrelated_object_ignored() -> None:
    payload = b"\0" + pobj(0x8A0E0064, DB_CLASS_RID, b"DB_Test", 100)
    payload += pobj(3, 2520, b"program")
    assert parse_datablocks(payload)[0].access_area == 0x8A0E0064
    assert parse_datablocks(payload)[0].number == 100


@pytest.mark.parametrize("payload", [b"\0\xa1", b"\0\xa2", b"\0\xa3", b"\0\xff"])
def test_malformed_pobject_db_enumeration(payload: bytes) -> None:
    with pytest.raises(S7CommPlusProtocolError):
        parse_datablocks(payload)
