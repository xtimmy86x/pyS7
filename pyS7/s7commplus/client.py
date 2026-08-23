"""Experimental synchronous low-level symbolic client."""

from collections.abc import Sequence
from types import TracebackType
from typing import Type

from .codec import (
    build_symbolic_read,
    build_symbolic_write,
    parse_symbolic_read,
    parse_symbolic_write,
)
from .connection import S7CommPlusConnection
from .protocol import DEFAULT_PORT, FunctionCode
from .tag import S7SymbolicTag


class S7CommPlusClient:
    """Explicit S7CommPlus backend; it never replaces or falls back from S7Client."""

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0
    ) -> None:
        self._connection = S7CommPlusConnection(host, port, timeout)

    @property
    def connected(self) -> bool:
        return self._connection.connected

    def connect(self) -> None:
        self._connection.connect()

    def disconnect(self) -> None:
        self._connection.disconnect()

    def read_symbolic(
        self, access_area: int, access_sequence: Sequence[int], symbol_crc: int = 0
    ) -> bytes:
        payload = build_symbolic_read(
            access_area, access_sequence, symbol_crc, self._connection.protocol_version
        )
        return parse_symbolic_read(
            self._connection.request(FunctionCode.GET_MULTI_VARIABLES, payload)
        )

    def read_symbolic_raw(self, tag: S7SymbolicTag) -> bytes:
        return self.read_symbolic(tag.access_area, tag.access_sequence, tag.symbol_crc)

    def write_symbolic(
        self,
        access_area: int,
        access_sequence: Sequence[int],
        data: bytes,
        symbol_crc: int = 0,
    ) -> None:
        payload = build_symbolic_write(
            access_area,
            access_sequence,
            data,
            symbol_crc,
            self._connection.protocol_version,
        )
        parse_symbolic_write(
            self._connection.request(FunctionCode.SET_MULTI_VARIABLES, payload)
        )

    def write_symbolic_raw(self, tag: S7SymbolicTag, data: bytes) -> None:
        self.write_symbolic(tag.access_area, tag.access_sequence, data, tag.symbol_crc)

    def __enter__(self) -> "S7CommPlusClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()
