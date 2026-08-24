import struct

import pytest

from pyS7.errors import S7CommPlusProtocolError
from pyS7.s7commplus.browse import (
    BLOCK_NUMBER_AID,
    DB_CLASS_RID,
    OBJECT_VARIABLE_TYPE_NAME_AID,
    PLC_PROGRAM_CLASS_RID,
    PLC_PROGRAM_RID,
    _decode_object,
    _decode_object_list,
    build_explore_request,
    parse_datablocks,
)
from pyS7.s7commplus.codec import extract_embedded_response_integrity
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
        return (
            b"\0\x12\x34\x56\x78" + encode_uint32(context.sequence_number) + b"answer"
        )

    monkeypatch.setattr(connection, "_exchange", exchange)
    assert (
        connection.request(FunctionCode.EXPLORE, b"body" + bytes(5), integrity_tail=5)
        == b"\0\x12\x34\x56\x78answer"
    )
    assert captured == b"body" + bytes(6)


def test_explore_embedded_response_integrity_is_extracted() -> None:
    objects = b"\xa1synthetic-pobject"
    payload = b"\0\x12\x34\x56\x78\x05" + objects
    context = _RequestContext(4, 1, FunctionCode.EXPLORE, True)

    normalized, response_iid = extract_embedded_response_integrity(
        payload, FunctionCode.EXPLORE
    )
    assert response_iid == 5
    assert normalized == b"\0\x12\x34\x56\x78" + objects
    assert (
        S7CommPlusConnection._normalize_response_integrity(payload, context)
        == normalized
    )


@pytest.mark.parametrize("response_iid", [4, 6])
def test_explore_rejects_incorrect_embedded_integrity(response_iid: int) -> None:
    payload = b"\0\x12\x34\x56\x78" + encode_uint32(response_iid) + b"objects"
    context = _RequestContext(4, 1, FunctionCode.EXPLORE, True)
    with pytest.raises(S7CommPlusProtocolError, match="IntegrityId"):
        S7CommPlusConnection._normalize_response_integrity(payload, context)


@pytest.mark.parametrize(
    "payload",
    [
        b"",  # Missing ReturnValue.
        b"\0\x12\x34\x56",  # Missing one byte of the fixed ExploreId.
        b"\0\x12\x34\x56\x78",  # Missing IntegrityId.
        b"\0\x12\x34\x56\x78\x80",  # Truncated IntegrityId VLQ.
        b"\0\x12\x34\x56\x78" + b"\x80" * 5,  # Unterminated VLQ.
    ],
)
def test_explore_rejects_truncated_or_malformed_envelope(payload: bytes) -> None:
    context = _RequestContext(4, 1, FunctionCode.EXPLORE, True)
    with pytest.raises(S7CommPlusProtocolError):
        S7CommPlusConnection._normalize_response_integrity(payload, context)


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
    relation: int,
    class_id: int,
    name: bytes = b"",
    number: int | None = None,
    contents: bytes = b"",
) -> bytes:
    value = b"\xa1" + struct.pack(">I", relation) + encode_uint32(class_id) + b"\0\0"
    if name:
        value += b"\xa3" + encode_uint32(OBJECT_VARIABLE_TYPE_NAME_AID)
        value += bytes((0, DataType.WSTRING)) + encode_uint32(len(name)) + name
    if number is not None:
        value += b"\xa3" + encode_uint32(BLOCK_NUMBER_AID)
        value += bytes((0, DataType.UDINT)) + encode_uint32(number)
    return value + contents + b"\xa2"


def program(*children: bytes) -> bytes:
    return pobj(3, PLC_PROGRAM_CLASS_RID, b"PLCProgram", contents=b"".join(children))


def test_valid_db_relation_and_unrelated_object_ignored() -> None:
    payload = b"\0\x12\x34\x56\x78" + program(
        pobj(7, 3333, b"unrelated"),
        pobj(0x8A0E0064, DB_CLASS_RID, b"DB_Test", 100),
    )
    assert parse_datablocks(payload)[0].access_area == 0x8A0E0064
    assert parse_datablocks(payload)[0].number == 100


@pytest.mark.parametrize("explore_id", [0, 0x12345678])
def test_normalized_explore_envelope_precedes_pobject_list(explore_id: int) -> None:
    payload = b"\0" + struct.pack(">I", explore_id)
    payload += program(pobj(0x8A0E0064, DB_CLASS_RID, b"DB_Test", 100))

    info = parse_datablocks(payload)[0]
    assert (info.name, info.number, info.relation_id, info.access_area) == (
        "DB_Test",
        100,
        0x8A0E0064,
        0x8A0E0064,
    )


def test_explore_debug_log_is_bounded(caplog: pytest.LogCaptureFixture) -> None:
    payload = b"\0\x12\x34\x56\x78" + pobj(3, 2520) + b"x" * 100
    with caplog.at_level("DEBUG", logger="pyS7.s7commplus.browse"):
        parse_datablocks(payload)
    message = caplog.messages[0]
    assert "return_value=0x0 explore_id=0x12345678" in message
    assert len(message.rsplit("object_bytes=", 1)[1]) == 128
    assert "offset=0xf" in caplog.messages[1]
    assert "byte=0x78" in caplog.messages[1]
    assert len(caplog.messages[1].rsplit("context=", 1)[1]) <= 66


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\x01\0\0\0\0", "PLC status 0x1"),
        (b"\0\0\0\0", "ExploreId"),
        (b"\0\0\0\0\0", "missing EXPLORE PObject list"),
        (b"\0\0\0\0\0\xa1", "object relation ID"),
        (b"\0\0\0\0\0" + pobj(3, 2520)[:-1], "truncated"),
    ],
)
def test_explore_envelope_and_object_structural_errors(
    payload: bytes, message: str
) -> None:
    with pytest.raises(S7CommPlusProtocolError, match=message):
        parse_datablocks(payload)


def test_known_unneeded_pobject_elements_preserve_alignment() -> None:
    extras = b"\xa4\x01\x01\x02\x03\x04"  # Relation ID VLQ + UInt32 value.
    extras += b"\xa7"  # StartTagDescription is a body-less marker.
    extras += b"\xab\x00\x02hi\x00\x00"  # VartypeList block chain.
    extras += b"\xac\x00\x01x\x00\x00"  # VarnameList block chain.
    body = program(pobj(0x8A0E0064, DB_CLASS_RID, b"DB_Test", 100, extras))

    assert parse_datablocks(b"\0\0\0\0\0" + body)[0].number == 100


def test_standalone_pobject_attributes_and_a2_termination() -> None:
    raw = pobj(4, 5, b"object")
    obj, pos = _decode_object(raw, 0)
    assert (obj.relation_id, obj.class_id, pos) == (4, 5, len(raw))
    assert obj.attributes[OBJECT_VARIABLE_TYPE_NAME_AID] == b"object"


def test_parent_with_multiple_nested_children() -> None:
    raw = program(pobj(10, 20), pobj(11, 21), pobj(12, 22))
    obj, pos = _decode_object(raw, 0)
    assert pos == len(raw)
    assert [(child.relation_id, child.class_id) for child in obj.children] == [
        (10, 20),
        (11, 21),
        (12, 22),
    ]


def test_top_level_non_start_and_zero_terminate_without_scanning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = pobj(1, 2)
    raw = first + b"\0" + pobj(3, 4)
    with caplog.at_level("DEBUG", logger="pyS7.s7commplus.browse"):
        objects, pos = _decode_object_list(raw, 0)
    assert len(objects) == 1
    assert pos == len(first) and raw[pos] == 0
    assert f"offset=0x{len(first):x}" in caplog.messages[-1]


def test_relation_is_consumed_and_retained() -> None:
    raw = pobj(1, 2, contents=b"\xa4\x03\x01\x02\x03\x04")
    obj, pos = _decode_object(raw, 0)
    assert pos == len(raw) and obj.relations == {3: 0x01020304}


def test_truncated_relation_id_and_value_are_rejected() -> None:
    for relation in (b"\xa4\x80", b"\xa4\x01\x01\x02\x03"):
        with pytest.raises(S7CommPlusProtocolError):
            _decode_object(pobj(1, 2, contents=relation)[:-1], 0)


def test_malformed_nested_pobject_is_rejected() -> None:
    raw = pobj(1, 2)[:-1] + pobj(3, 4)[:-1]
    with pytest.raises(S7CommPlusProtocolError, match="truncated"):
        _decode_object(raw, 0)


def test_unknown_inside_object_ends_only_that_object(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = pobj(1, 2)[:-1] + b"\0"
    with caplog.at_level("DEBUG", logger="pyS7.s7commplus.browse"):
        obj, pos = _decode_object(raw, 0)
    assert obj.class_id == 2 and pos == len(raw)
    assert "relation_id=0x00000001" in caplog.messages[-1]
    assert "byte=0x00" in caplog.messages[-1]


@pytest.mark.parametrize(
    "payload",
    [
        b"\0\0\0\0\0\xa1",
        b"\0\0\0\0\0\xa2",
        b"\0\0\0\0\0\xa3",
        b"\0\0\0\0\0\xff",
    ],
)
def test_malformed_pobject_db_enumeration(payload: bytes) -> None:
    with pytest.raises(S7CommPlusProtocolError):
        parse_datablocks(payload)
