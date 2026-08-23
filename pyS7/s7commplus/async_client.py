"""Async facade sharing the synchronous protocol implementation and codecs."""

import asyncio
from collections.abc import Sequence
from types import TracebackType
from typing import Type

from .client import S7CommPlusClient
from .protocol import DEFAULT_PORT
from .tag import S7SymbolicTag


class AsyncS7CommPlusClient:
    """Non-blocking facade that runs bounded socket operations in worker threads."""

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0
    ) -> None:
        self._client = S7CommPlusClient(host, port, timeout)
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._client.connected

    async def connect(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._client.connect)

    async def disconnect(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._client.disconnect)

    async def read_symbolic(
        self, access_area: int, access_sequence: Sequence[int], symbol_crc: int = 0
    ) -> bytes:
        async with self._lock:
            return await asyncio.to_thread(
                self._client.read_symbolic, access_area, access_sequence, symbol_crc
            )

    async def read_symbolic_raw(self, tag: S7SymbolicTag) -> bytes:
        return await self.read_symbolic(
            tag.access_area, tag.access_sequence, tag.symbol_crc
        )

    async def write_symbolic(
        self,
        access_area: int,
        access_sequence: Sequence[int],
        data: bytes,
        symbol_crc: int = 0,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._client.write_symbolic,
                access_area,
                access_sequence,
                data,
                symbol_crc,
            )

    async def write_symbolic_raw(self, tag: S7SymbolicTag, data: bytes) -> None:
        await self.write_symbolic(
            tag.access_area, tag.access_sequence, data, tag.symbol_crc
        )

    async def __aenter__(self) -> "AsyncS7CommPlusClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()
