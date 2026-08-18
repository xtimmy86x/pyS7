import pytest

from pyS7.constants import READ_RES_OVERHEAD, WRITE_RES_OVERHEAD, DataType, MemoryArea
from pyS7.errors import (
    S7ProtocolError,
    S7ReadResponseError,
    S7WriteResponseError,
)
from pyS7.responses import parse_read_response, parse_write_response
from pyS7.tag import S7Tag

TAG = S7Tag(MemoryArea.DB, 99, DataType.INT, 0, 0, 1)


def test_response_error_construction_is_backward_compatible() -> None:
    read_error = S7ReadResponseError("message")
    write_error = S7WriteResponseError("message")

    assert str(read_error) == str(write_error) == "message"
    assert (read_error.tag, read_error.error_code, read_error.operation) == (
        None,
        None,
        "read",
    )
    assert (write_error.tag, write_error.error_code, write_error.operation) == (
        None,
        None,
        "write",
    )


@pytest.mark.parametrize(
    ("parser", "error_type", "overhead", "operation"),
    [
        (parse_read_response, S7ReadResponseError, READ_RES_OVERHEAD, "read"),
        (parse_write_response, S7WriteResponseError, WRITE_RES_OVERHEAD, "write"),
    ],
)
def test_plc_return_code_error_has_structured_metadata(
    parser: object, error_type: type[Exception], overhead: int, operation: str
) -> None:
    response = bytes(overhead) + b"\x0a"

    with pytest.raises(error_type) as info:
        parser(response, [TAG])  # type: ignore[operator]

    error = info.value
    assert error.tag == TAG  # type: ignore[attr-defined]
    assert error.error_code == 0x0A  # type: ignore[attr-defined]
    assert error.operation == operation  # type: ignore[attr-defined]
    assert "OBJECT_DOES_NOT_EXIST" in str(error)


def test_truncated_read_response_is_protocol_error() -> None:
    with pytest.raises(S7ProtocolError, match="response too short"):
        parse_read_response(b"", [TAG])


def test_truncated_read_payload_chains_low_level_error() -> None:
    response = bytes(READ_RES_OVERHEAD) + b"\xff\x05\x00\x10"

    with pytest.raises(S7ProtocolError, match="Malformed read response") as info:
        parse_read_response(response, [TAG])

    assert info.value.__cause__ is not None


def test_missing_write_return_code_chains_low_level_error() -> None:
    with pytest.raises(S7ProtocolError, match="missing return code") as info:
        parse_write_response(b"", [TAG])

    assert info.value.__cause__ is not None