"""Async facade sharing the synchronous protocol implementation and codecs."""

import asyncio
from collections.abc import Sequence
from types import TracebackType
from typing import Any, Callable, Type, TypeVar

from .browse import S7DataBlockInfo
from .client import S7CommPlusClient
from .protocol import DEFAULT_PORT
from .tag import S7SymbolicTag

_T = TypeVar("_T")


class AsyncS7CommPlusClient:
    """Serialize synchronous operations in worker threads.

    Cancellation stops waiting for an operation, not the underlying socket call.  The
    lock is deliberately retained until that worker finishes so a cancelled operation
    can never overlap and corrupt the session used by a following coroutine.
    """

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0
    ) -> None:
        self._client = S7CommPlusClient(host, port, timeout)
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._client.connected

    async def _run(
        self, operation: Callable[..., _T], *args: object, **kwargs: Any
    ) -> _T:
        async with self._lock:
            worker = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                # asyncio.to_thread cannot cancel a running OS call.  Finish it while
                # still holding the session lock, then propagate cancellation.
                try:
                    await worker
                except Exception:
                    pass
                raise

    async def connect(
        self,
        *,
        use_tls: bool = False,
        tls_ca: str | None = None,
        tls_cert: str | None = None,
        tls_key: str | None = None,
        tls_verify: bool = False,
    ) -> None:
        await self._run(
            self._client.connect,
            use_tls=use_tls,
            tls_ca=tls_ca,
            tls_cert=tls_cert,
            tls_key=tls_key,
            tls_verify=tls_verify,
        )

    async def disconnect(self) -> None:
        await self._run(self._client.disconnect)

    async def read_symbolic(
        self, access_area: int, access_sequence: Sequence[int], symbol_crc: int = 0
    ) -> bytes:
        return await self._run(
            self._client.read_symbolic, access_area, access_sequence, symbol_crc
        )

    async def read_symbolic_raw(self, tag: S7SymbolicTag) -> bytes:
        return await self.read_symbolic(
            tag.access_area, tag.access_sequence, tag.symbol_crc
        )

    async def explore_raw(self, rid: int, attribute_ids: Sequence[int] = ()) -> bytes:
        return await self._run(self._client.explore_raw, rid, attribute_ids)

    async def list_datablocks(self) -> list[S7DataBlockInfo]:
        return await self._run(self._client.list_datablocks)

    async def resolve_type_info_rid(self, access_area: int) -> int:
        return await self._run(self._client.resolve_type_info_rid, access_area)

    async def retrieve_type_info_raw(self, access_area: int) -> tuple[int, bytes]:
        return await self._run(self._client.retrieve_type_info_raw, access_area)

    async def browse(self, db_number: int | None = None) -> list[S7SymbolicTag]:
        """Discover flat scalar members without blocking the event loop."""
        return await self._run(self._client.browse, db_number)

    async def write_symbolic(
        self,
        access_area: int,
        access_sequence: Sequence[int],
        data: bytes,
        symbol_crc: int = 0,
    ) -> None:
        await self._run(
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
