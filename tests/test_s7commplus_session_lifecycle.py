import struct

import pytest

from pyS7.s7commplus import S7CommPlusClient
from pyS7.s7commplus.protocol import FunctionCode, ProtocolVersion
from pyS7.s7commplus.vlq import encode_uint32


def test_delete_server_session_sends_request_iid_but_expects_no_response_iid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7CommPlusClient("192.0.2.1")
    connection = client._connection
    connection._socket = object()  # type: ignore[assignment]
    connection._ready = True
    connection._with_integrity = True
    connection.session_id = 0x70400000
    connection.protocol_version = ProtocolVersion.V2
    connection._sequence = 10
    connection._integrity_write = 3

    captured: dict[str, object] = {}

    def exchange(
        function: int,
        payload: bytes,
        session_id: int,
        *,
        flags: int,
        version: int,
        context: object,
        **_: object,
    ) -> bytes:
        captured.update(
            function=function,
            payload=payload,
            session_id=session_id,
            flags=flags,
            version=version,
            context=context,
        )
        # When deleting our own Session Object-ID the response has no
        # IntegrityId. ReturnValue=0 followed by the deleted Object-ID is
        # sufficient to model the response application payload.
        return b"\x00" + struct.pack(">I", session_id)

    def unexpected_normalize(*_: object, **__: object) -> bytes:
        raise AssertionError(
            "own-session DeleteObject response must not be IntegrityId-normalized"
        )

    monkeypatch.setattr(connection, "_exchange", exchange)
    monkeypatch.setattr(
        connection, "_normalize_response_integrity", unexpected_normalize
    )

    client._delete_server_session()

    assert captured["function"] == FunctionCode.DELETE_OBJECT
    assert captured["session_id"] == 0x70400000
    assert captured["flags"] == 0x34
    assert captured["version"] == ProtocolVersion.V2
    payload = captured["payload"]
    assert isinstance(payload, bytes)
    assert payload.startswith(struct.pack(">I", 0x70400000) + b"\x00")
    assert payload.endswith(encode_uint32(3) + b"\x00" * 4)
    assert connection._integrity_write == 4


def test_disconnect_always_closes_transport_when_delete_object_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7CommPlusClient("192.0.2.1")
    events: list[str] = []

    class FakeConnection:
        connected = True

        def disconnect(self) -> None:
            events.append("transport")

    client._connection = FakeConnection()  # type: ignore[assignment]
    client._symbol_cache["x"] = object()  # type: ignore[assignment]
    client._datablock_cache = []

    def fail_delete() -> None:
        events.append("delete")
        raise OSError("peer already gone")

    monkeypatch.setattr(client, "_delete_server_session", fail_delete)

    client.disconnect()

    assert events == ["delete", "transport"]
    assert client._symbol_cache == {}
    assert client._datablock_cache is None


def test_connect_tears_down_existing_session_before_reconnect() -> None:
    client = S7CommPlusClient("192.0.2.1")
    events: list[str] = []

    class FakeConnection:
        connected = True

        def connect(self, **_: object) -> None:
            events.append("connect")

        def disconnect(self) -> None:
            events.append("transport")

    client._connection = FakeConnection()  # type: ignore[assignment]
    client._delete_server_session = lambda: events.append("delete")  # type: ignore[method-assign]

    client.connect(use_tls=True)

    assert events == ["delete", "transport", "connect"]
