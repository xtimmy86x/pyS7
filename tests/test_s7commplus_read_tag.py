from datetime import timedelta
from unittest.mock import Mock

import pytest

from pyS7.constants import DataType
from pyS7.errors import S7CommPlusSymbolNotFoundError
from pyS7.s7commplus import S7CommPlusClient, S7SymbolicTag
from pyS7.s7commplus.browse import S7DataBlockInfo
from pyS7.s7commplus.value import decode_symbolic_value


@pytest.mark.parametrize(
    ("data_type", "raw", "expected"),
    [
        (DataType.BIT, b"\x00", False),
        (DataType.BIT, b"\x01", True),
        (DataType.INT, b"\x30\x39", 12345),
        (DataType.INT, b"\xcf\xc7", -12345),
        (DataType.DINT, b"\x00\x01\xe2\x40", 123456),
        (DataType.DINT, b"\xff\xfe\x1d\xc0", -123456),
        (DataType.REAL, b"\x41\x28\x00\x00", 10.5),
        (DataType.TIME, b"\x00\x00\x01\xf4", timedelta(milliseconds=500)),
        (DataType.STRING, b"\xfe\x0aTestString", "TestString"),
        (
            DataType.WSTRING,
            bytes.fromhex(
                "00fe 000b 0054 0065 0073 0074 0057 0073 0074 0072 0069 006e 0067"
            ),
            "TestWstring",
        ),
    ],
)
def test_decode_symbolic_scalars(
    data_type: DataType, raw: bytes, expected: object
) -> None:
    assert decode_symbolic_value(data_type, raw) == expected


def configured_client() -> tuple[S7CommPlusClient, S7SymbolicTag]:
    client = S7CommPlusClient("plc")
    tag = S7SymbolicTag(
        0x8A0E0064,
        (0x22,),
        data_type=DataType.REAL,
        name="DB_Test.Real",
        symbol_crc=0x35D91B1D,
    )
    client.list_datablocks = Mock(  # type: ignore[method-assign]
        return_value=[S7DataBlockInfo("DB_Test", 100, tag.access_area, tag.access_area)]
    )
    client.browse = Mock(return_value=[tag])  # type: ignore[method-assign]
    # A mocked browse does not execute the production cache side effect, so mirror it.
    client.browse.side_effect = lambda db_number: (  # type: ignore[attr-defined]
        client._cache_symbols([tag]) or [tag]
    )
    client.read_symbolic = Mock(  # type: ignore[method-assign]
        return_value=bytes.fromhex("41280000")
    )
    return client, tag


def test_read_tag_resolves_reads_and_caches() -> None:
    client, tag = configured_client()

    assert client.read_tag(tag.name) == 10.5
    assert client.read_tag(tag.name) == 10.5

    client.browse.assert_called_once_with(100)  # type: ignore[attr-defined]
    client.read_symbolic.assert_called_with(  # type: ignore[attr-defined]
        0x8A0E0064, (0x22,), 0
    )

    client.clear_symbol_cache()
    assert client.read_tag(tag.name) == 10.5
    assert client.browse.call_count == 2  # type: ignore[attr-defined]


def test_browse_populates_cache_for_later_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7CommPlusClient("plc")
    tag = S7SymbolicTag(
        0x8A0E0064,
        (0x22,),
        data_type=DataType.REAL,
        name="DB_Test.Real",
    )
    db = S7DataBlockInfo("DB_Test", 100, tag.access_area, tag.access_area)
    client.list_datablocks = Mock(return_value=[db])  # type: ignore[method-assign]
    client.retrieve_type_info_raw = Mock(  # type: ignore[method-assign]
        return_value=(123, b"type-info")
    )
    monkeypatch.setattr(
        "pyS7.s7commplus.client.parse_type_info", Mock(return_value=[tag])
    )
    client.read_symbolic = Mock(  # type: ignore[method-assign]
        return_value=bytes.fromhex("41280000")
    )

    assert client.browse(db_number=100) == [tag]
    assert client.read_tag(tag.name) == 10.5
    client.retrieve_type_info_raw.assert_called_once_with(tag.access_area)  # type: ignore[attr-defined]


def test_read_symbolic_preserves_explicit_item_address_crc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S7CommPlusClient("plc")
    build = Mock(return_value=b"request")
    request = Mock(return_value=b"response")
    monkeypatch.setattr("pyS7.s7commplus.client.build_symbolic_read", build)
    monkeypatch.setattr(
        "pyS7.s7commplus.client.parse_symbolic_read", Mock(return_value=b"value")
    )
    client._connection.request = request  # type: ignore[method-assign]

    assert client.read_symbolic(0x8A0E0064, (0x22,), 1234) == b"value"
    build.assert_called_once_with(
        0x8A0E0064, (0x22,), 1234, client._connection.protocol_version
    )
    request.assert_called_once_with(0x054C, b"request")


def test_missing_symbol_raises_clear_error() -> None:
    client, _tag = configured_client()
    client.browse.side_effect = lambda db_number: []  # type: ignore[attr-defined]

    with pytest.raises(S7CommPlusSymbolNotFoundError, match="DoesNotExist"):
        client.read_tag("DB_Test.DoesNotExist")
