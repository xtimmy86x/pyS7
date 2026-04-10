"""Async S7 PLC client based on asyncio.

Provides AsyncS7Client with the same API as S7Client but using non-blocking
asyncio I/O — suitable for SCADA dashboards, IoT applications, and any
asyncio-based system.

Example:
    >>> import asyncio
    >>> from pyS7 import AsyncS7Client
    >>>
    >>> async def main():
    ...     async with AsyncS7Client('192.168.0.1', 0, 1) as client:
    ...         values = await client.read(['DB1,I0', 'DB1,R4'])
    ...         print(values)
    ...
    >>> asyncio.run(main())
"""

import asyncio
import logging
import struct
from dataclasses import dataclass
from time import time
from types import TracebackType
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, Union, cast

from .address_parser import map_address_to_tag
from .client import BatchWriteTransaction, ReadResult, S7Client, WriteResult
from .constants import (
    MAX_JOB_CALLED,
    MAX_JOB_CALLING,
    MAX_PDU,
    MAX_PDU_SIZE,
    MIN_PDU_SIZE,
    TPKT_SIZE,
    ConnectionState,
    ConnectionType,
    DataType,
    READ_RES_OVERHEAD,
    READ_RES_PARAM_SIZE_TAG,
    SZLId,
    WRITE_REQ_OVERHEAD,
    WRITE_REQ_PARAM_SIZE_TAG,
)
from .errors import (
    S7AddressError,
    S7CommunicationError,
    S7ConnectionError,
    S7ProtocolError,
    S7TimeoutError,
)
from .metrics import ClientMetrics
from .requests import (
    ConnectionRequest,
    PDUNegotiationRequest,
    ReadRequest,
    Request,
    SZLRequest,
    Value,
    WriteRequest,
    prepare_optimized_requests,
    prepare_requests,
    prepare_write_requests_and_values,
)
from .responses import (
    ConnectionResponse,
    PDUNegotiationResponse,
    ReadOptimizedResponse,
    ReadResponse,
    SZLResponse,
    WriteResponse,
)
from .tag import S7Tag


@dataclass
class AsyncBatchWriteTransaction:
    """Async batch write transaction for atomic multi-tag writes.

    Example:
        >>> async with client.batch_write() as batch:
        ...     batch.add('DB1,I0', 100)
        ...     batch.add('DB1,I2', 200)
    """

    _client: "AsyncS7Client"
    _tags: List[Union[str, S7Tag]]
    _values: List[Value]
    _original_values: Optional[List[Any]]
    auto_commit: bool = True
    rollback_on_error: bool = True

    def __init__(
        self,
        client: "AsyncS7Client",
        auto_commit: bool = True,
        rollback_on_error: bool = True,
    ):
        self._client = client
        self._tags = []
        self._values = []
        self._original_values = None
        self.auto_commit = auto_commit
        self.rollback_on_error = rollback_on_error

    def add(self, tag: Union[str, S7Tag], value: Value) -> "AsyncBatchWriteTransaction":
        """Add a tag/value pair to the batch. Returns self for chaining."""
        self._tags.append(tag)
        self._values.append(value)
        return self

    async def commit(self) -> List[WriteResult]:
        """Execute all writes in the batch.

        Returns:
            List of WriteResult objects.
        """
        if not self._tags:
            raise ValueError("No tags added to batch")

        if self.rollback_on_error:
            try:
                self._original_values = await self._client.read(self._tags)
            except Exception as e:
                self._client.logger.warning(
                    f"Could not read original values for rollback: {e}"
                )
                self._original_values = None

        results = await self._client.write_detailed(self._tags, self._values)

        if self.rollback_on_error:
            failed = [r for r in results if not r.success]
            if failed and self._original_values is not None:
                self._client.logger.warning(
                    f"Batch write had {len(failed)} failures, rolling back"
                )
                try:
                    await self._client.write(self._tags, self._original_values)
                except Exception as e:
                    self._client.logger.error(f"Rollback failed: {e}")

        return results

    async def rollback(self) -> None:
        """Manually rollback to original values."""
        if self._original_values is None:
            raise RuntimeError(
                "Cannot rollback: no original values saved. "
                "Ensure rollback_on_error=True or call commit() first."
            )
        await self._client.write(self._tags, self._original_values)
        self._client.logger.info("Batch write transaction rolled back")

    async def __aenter__(self) -> "AsyncBatchWriteTransaction":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if exc_type is None and self.auto_commit and self._tags:
            await self.commit()


class AsyncS7Client:
    """Async S7 PLC client using asyncio streams.

    Drop-in async replacement for S7Client.  All I/O methods are coroutines;
    request-building and response-parsing reuse the synchronous helpers
    (they are pure computation with no blocking I/O).

    Attributes:
        address: PLC IP address.
        rack: Rack number (ignored if local_tsap/remote_tsap provided).
        slot: Slot number (ignored if local_tsap/remote_tsap provided).
        connection_type: PLC connection type.
        port: TCP port (default 102).
        timeout: I/O timeout in seconds.
        local_tsap: Local TSAP override.
        remote_tsap: Remote TSAP override.
        max_pdu: Maximum PDU size.

    Example:
        >>> async with AsyncS7Client('192.168.0.1', 0, 1) as client:
        ...     values = await client.read(['DB1,I0', 'DB1,R4'])
    """

    logger = logging.getLogger(f"{__name__}")

    def __init__(
        self,
        address: str,
        rack: int = 0,
        slot: int = 0,
        connection_type: ConnectionType = ConnectionType.S7Basic,
        port: int = 102,
        timeout: float = 5.0,
        local_tsap: Optional[Union[int, str]] = None,
        remote_tsap: Optional[Union[int, str]] = None,
        max_pdu: int = MAX_PDU,
        enable_metrics: bool = True,
    ) -> None:
        self.address = address
        self.rack = rack
        self.slot = slot
        self.connection_type = connection_type
        self.port = port
        self.timeout = timeout

        if isinstance(local_tsap, str):
            local_tsap = S7Client.tsap_from_string(local_tsap)
        if isinstance(remote_tsap, str):
            remote_tsap = S7Client.tsap_from_string(remote_tsap)

        self.local_tsap = local_tsap
        self.remote_tsap = remote_tsap

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._io_lock = asyncio.Lock()
        self._connection_state = ConnectionState.DISCONNECTED
        self._last_error: Optional[str] = None

        if not isinstance(max_pdu, int) or max_pdu < MIN_PDU_SIZE or max_pdu > MAX_PDU_SIZE:
            raise ValueError(
                f"max_pdu must be an integer between {MIN_PDU_SIZE} and {MAX_PDU_SIZE}, "
                f"got {max_pdu!r}"
            )
        self.pdu_size: int = max_pdu
        self.max_jobs_calling: int = MAX_JOB_CALLING
        self.max_jobs_called: int = MAX_JOB_CALLED

        self.metrics: Optional[ClientMetrics] = ClientMetrics() if enable_metrics else None

        if local_tsap is not None or remote_tsap is not None:
            S7Client._validate_tsap(local_tsap, remote_tsap)

    # -- Static helpers delegated to S7Client ----------------------------------

    tsap_from_string = staticmethod(S7Client.tsap_from_string)
    tsap_to_string = staticmethod(S7Client.tsap_to_string)
    tsap_from_rack_slot = staticmethod(S7Client.tsap_from_rack_slot)
    _read_item_data_length = staticmethod(S7Client._read_item_data_length)
    _parse_tag_value = S7Client._parse_tag_value

    # -- Context manager -------------------------------------------------------

    async def __aenter__(self) -> "AsyncS7Client":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        try:
            await self.disconnect()
        except Exception:
            pass

    # -- Properties ------------------------------------------------------------

    @property
    def connection_state(self) -> ConnectionState:
        return self._connection_state

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def is_connected(self) -> bool:
        return self._connection_state == ConnectionState.CONNECTED

    def _set_connection_state(
        self, state: ConnectionState, error: Optional[str] = None
    ) -> None:
        old_state = self._connection_state
        self._connection_state = state
        if state == ConnectionState.ERROR:
            self._last_error = error
        elif state == ConnectionState.CONNECTED:
            self._last_error = None
        if old_state != state:
            self.logger.debug(f"Connection state: {old_state.value} → {state.value}")
            if error:
                self.logger.debug(f"Error: {error}")

    # -- Connection ------------------------------------------------------------

    async def connect(self) -> None:
        """Establish an async TCP connection to the PLC and negotiate parameters."""
        if self._connection_state == ConnectionState.CONNECTED:
            self.logger.warning("Already connected to PLC")
            return
        if self._connection_state == ConnectionState.CONNECTING:
            self.logger.warning("Connection already in progress")
            return

        self._set_connection_state(ConnectionState.CONNECTING)

        if self.local_tsap is not None and self.remote_tsap is not None:
            self.logger.debug(
                f"Connecting to PLC at {self.address}:{self.port} "
                f"(local_tsap={self.local_tsap:#06x}, remote_tsap={self.remote_tsap:#06x})"
            )
        else:
            self.logger.debug(
                f"Connecting to PLC at {self.address}:{self.port} "
                f"(rack={self.rack}, slot={self.slot})"
            )

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.address, self.port),
                timeout=self.timeout,
            )
            self.logger.debug(
                f"TCP connection established to {self.address}:{self.port}"
            )
        except asyncio.TimeoutError as e:
            msg = f"Connection timeout to {self.address}:{self.port} after {self.timeout}s"
            self._reader = self._writer = None
            self._set_connection_state(ConnectionState.DISCONNECTED)
            self.logger.error(msg)
            raise S7TimeoutError(msg) from e
        except OSError as e:
            msg = f"Failed to connect to {self.address}:{self.port}: {e}"
            self._reader = self._writer = None
            self._set_connection_state(ConnectionState.DISCONNECTED)
            self.logger.error(msg)
            raise S7ConnectionError(msg) from e

        try:
            # COTP connection
            connection_request = ConnectionRequest(
                connection_type=self.connection_type,
                rack=self.rack,
                slot=self.slot,
                local_tsap=self.local_tsap,
                remote_tsap=self.remote_tsap,
            )
            resp = await self._send(connection_request)
            ConnectionResponse(response=resp)
            self.logger.debug("COTP connection accepted")

            # PDU negotiation
            requested_pdu = self.pdu_size
            pdu_req = PDUNegotiationRequest(max_pdu=requested_pdu)
            resp = await self._send(pdu_req)
            pdu_resp = PDUNegotiationResponse(response=resp)
            (
                self.max_jobs_calling,
                self.max_jobs_called,
                negotiated_pdu,
            ) = pdu_resp.parse()

            self.pdu_size = S7Client._validate_and_adjust_pdu(
                cast(S7Client, self), requested_pdu, negotiated_pdu
            )

            self._set_connection_state(ConnectionState.CONNECTED)
            self.logger.debug(
                f"Connected to PLC {self.address}:{self.port} - "
                f"PDU: {self.pdu_size} bytes, "
                f"Jobs: {self.max_jobs_calling}/{self.max_jobs_called}"
            )

            if self.metrics:
                self.metrics.record_connection()

        except asyncio.TimeoutError as e:
            msg = f"Connection timeout during COTP/PDU negotiation after {self.timeout}s: {e}"
            self._set_connection_state(ConnectionState.ERROR, msg)
            self.logger.error(msg)
            if self.metrics:
                self.metrics.record_timeout()
            await self.disconnect()
            raise S7TimeoutError(msg) from e
        except OSError as e:
            msg = f"Socket error during connection setup: {e}"
            self._set_connection_state(ConnectionState.ERROR, msg)
            self.logger.error(msg)
            await self.disconnect()
            raise S7ConnectionError(msg) from e
        except S7ConnectionError:
            self._set_connection_state(ConnectionState.ERROR, str(self._last_error))
            await self.disconnect()
            raise
        except S7CommunicationError as e:
            msg = f"Communication error during connection setup: {e}"
            self._set_connection_state(ConnectionState.ERROR, msg)
            self.logger.error(msg)
            await self.disconnect()
            raise S7ConnectionError(msg) from e
        except (ValueError, struct.error) as e:
            msg = f"Invalid protocol response during connection setup: {e}"
            self._set_connection_state(ConnectionState.ERROR, msg)
            self.logger.error(msg)
            await self.disconnect()
            raise S7ProtocolError(msg) from e

    async def disconnect(self) -> None:
        """Close the async TCP connection."""
        if self._connection_state == ConnectionState.DISCONNECTED:
            self.logger.debug("Already disconnected")
            return

        if self._connection_state != ConnectionState.ERROR:
            self._set_connection_state(ConnectionState.DISCONNECTING)

        async with self._io_lock:
            writer = self._writer
            self._writer = None
            self._reader = None

        if writer:
            self.logger.debug(f"Disconnecting from {self.address}:{self.port}")
            try:
                writer.close()
                await writer.wait_closed()
                self.logger.debug(
                    f"Disconnected from PLC {self.address}:{self.port}"
                )
            except Exception as e:
                self.logger.debug(f"Writer close error: {e}")

        if self.metrics:
            self.metrics.record_disconnection()

        if self._connection_state != ConnectionState.ERROR:
            self._set_connection_state(ConnectionState.DISCONNECTED)

    # -- Low-level I/O ---------------------------------------------------------

    async def _send(self, request: Request) -> bytes:
        """Send a request and receive the full TPKT response.

        Holds ``_io_lock`` for the entire send-receive cycle to serialise
        concurrent coroutines sharing this client.
        """
        if not isinstance(request, Request):
            raise ValueError(f"Request type {type(request).__name__} not supported")

        try:
            async with self._io_lock:
                if self._writer is None or self._reader is None:
                    raise S7CommunicationError(
                        "Stream is not initialized. Call connect() first."
                    )

                data = request.serialize()
                self.logger.debug(f"TX -> PLC: {len(data)} bytes [TPKT+COTP+S7]")
                self._writer.write(data)
                await asyncio.wait_for(
                    self._writer.drain(), timeout=self.timeout
                )

                header = await self._recv_exact(TPKT_SIZE)
                if len(header) < 4:
                    raise S7CommunicationError(
                        "Incomplete TPKT header received from the PLC."
                    )
                tpkt_length = int.from_bytes(header[2:4], byteorder="big")
                if tpkt_length < 4:
                    raise S7CommunicationError(
                        "Invalid TPKT length received from the PLC."
                    )

                body = await self._recv_exact(tpkt_length - 4)
                return header + body

        except asyncio.TimeoutError as e:
            msg = f"Communication timeout after {self.timeout}s"
            self.logger.error(msg)
            self._set_connection_state(ConnectionState.ERROR, msg)
            await self._cleanup_on_error()
            self._set_connection_state(ConnectionState.DISCONNECTED)
            raise S7TimeoutError(msg) from e
        except OSError as e:
            msg = f"Socket error during communication: {e}"
            self.logger.error(msg)
            self._set_connection_state(ConnectionState.ERROR, msg)
            await self._cleanup_on_error()
            self._set_connection_state(ConnectionState.DISCONNECTED)
            raise S7CommunicationError(msg) from e

    async def _recv_exact(self, length: int) -> bytes:
        """Read exactly *length* bytes from the stream."""
        if self._reader is None:
            raise S7CommunicationError(
                "Stream is not initialized. Call connect() first."
            )
        if length == 0:
            return b""

        try:
            data = await asyncio.wait_for(
                self._reader.readexactly(length), timeout=self.timeout
            )
            return data
        except asyncio.IncompleteReadError as e:
            msg = (
                f"Incomplete data from PLC: expected {length} bytes, "
                f"received {len(e.partial)} bytes. Connection closed by peer."
            )
            self.logger.error(msg)
            self._set_connection_state(ConnectionState.ERROR, msg)
            self._writer = None
            self._reader = None
            self._set_connection_state(ConnectionState.DISCONNECTED)
            raise S7CommunicationError(msg) from e

    async def _cleanup_on_error(self) -> None:
        """Close streams after a communication error."""
        async with self._io_lock:
            self._cleanup_streams()

    def _cleanup_streams(self) -> None:
        """Close streams without acquiring the lock (caller must hold it)."""
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
        self._writer = None
        self._reader = None

    # -- Read ------------------------------------------------------------------

    async def read(
        self, tags: Sequence[Union[str, S7Tag]], optimize: bool = True
    ) -> List[Value]:
        """Read tags from the PLC.

        Args:
            tags: Sequence of S7Tag or string addresses.
            optimize: Merge adjacent tags to reduce telegrams.

        Returns:
            List of values corresponding to each tag.

        Example:
            >>> values = await client.read(['DB1,X0.0', 'DB1,I2', 'DB1,R4'])
        """
        list_tags: List[S7Tag] = [
            map_address_to_tag(address=t) if isinstance(t, str) else t for t in tags
        ]
        if not list_tags:
            return []

        self.logger.debug(
            f"Reading {len(list_tags)} tag(s) - optimize={optimize}, PDU={self.pdu_size}"
        )

        async with self._io_lock:
            if not self.is_connected:
                raise S7CommunicationError(
                    "Not connected to PLC. Call 'connect' before performing read operations."
                )

            start_time = time() if self.metrics else None
            try:
                regular_tags: List[Tuple[int, S7Tag]] = []
                large_string_indices: List[int] = []
                large_string_tags: List[S7Tag] = []
                data: List[Optional[Value]] = [None] * len(list_tags)

                for i, tag in enumerate(list_tags):
                    resp_size = READ_RES_OVERHEAD + READ_RES_PARAM_SIZE_TAG + tag.size()
                    if resp_size > self.pdu_size:
                        if tag.data_type in (DataType.STRING, DataType.WSTRING):
                            large_string_indices.append(i)
                            large_string_tags.append(tag)
                            continue
                        max_data = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
                        raise S7AddressError(
                            f"{tag} requires {resp_size} bytes but PDU is {self.pdu_size}. "
                            f"Max data: {max_data} bytes."
                        )
                    regular_tags.append((i, tag))

                # Large strings need multiple send/receive cycles.
                # Release the lock so _read_large_string → read() can reacquire it.
                for idx, tag in zip(large_string_indices, large_string_tags):
                    data[idx] = await self._read_large_string_unlocked(tag)

                if regular_tags:
                    tags_only = [t for _, t in regular_tags]

                    if optimize:
                        requests, tags_map = prepare_optimized_requests(
                            tags=tags_only, max_pdu=self.pdu_size
                        )
                        resp_bytes = await self._send_unlocked(
                            ReadRequest(tags=requests[0])
                        )
                        response = ReadOptimizedResponse(
                            response=resp_bytes,
                            tag_map={k: tags_map[k] for k in requests[0]},
                        )
                        for batch in requests[1:]:
                            resp_bytes = await self._send_unlocked(
                                ReadRequest(tags=batch)
                            )
                            response += ReadOptimizedResponse(
                                response=resp_bytes,
                                tag_map={k: tags_map[k] for k in batch},
                            )
                        regular_data = response.parse()
                    else:
                        reqs = prepare_requests(tags=tags_only, max_pdu=self.pdu_size)
                        regular_data = []
                        for req in reqs:
                            resp_bytes = await self._send_unlocked(
                                ReadRequest(tags=req)
                            )
                            rr = ReadResponse(response=resp_bytes, tags=req)
                            regular_data.extend(rr.parse())

                    for (orig_idx, _), value in zip(regular_tags, regular_data):
                        data[orig_idx] = value

                if self.metrics and start_time is not None:
                    duration = time() - start_time
                    self.metrics.record_read(
                        duration, sum(t.size() for t in list_tags), success=True
                    )

                return cast(List[Value], data)

            except Exception:
                if self.metrics and start_time is not None:
                    self.metrics.record_read(time() - start_time, 0, success=False)
                raise

    async def read_detailed(
        self, tags: Sequence[Union[str, S7Tag]], optimize: bool = True
    ) -> List[ReadResult]:
        """Read tags with per-tag success/error details.

        Does not raise on individual tag failures.

        Returns:
            List of ReadResult objects.
        """
        if not tags:
            raise ValueError("Tags list cannot be empty")

        list_tags: List[S7Tag] = [
            map_address_to_tag(address=t) if isinstance(t, str) else t for t in tags
        ]

        async with self._io_lock:
            if not self.is_connected:
                raise S7CommunicationError(
                    "Not connected to PLC. Call 'connect' before performing read operations."
                )

            results: List[ReadResult] = []
            processed: set[int] = set()

            for i, tag in enumerate(list_tags):
                resp_size = READ_RES_OVERHEAD + READ_RES_PARAM_SIZE_TAG + tag.size()
                if resp_size > self.pdu_size:
                    if tag.data_type in (DataType.STRING, DataType.WSTRING):
                        try:
                            val = await self._read_large_string(tag)
                            results.append(ReadResult(tag=tag, success=True, value=val))
                        except Exception as e:
                            results.append(
                                ReadResult(
                                    tag=tag,
                                    success=False,
                                    error=f"Large string read failed: {e}",
                                )
                            )
                    else:
                        max_data = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
                        results.append(
                            ReadResult(
                                tag=tag,
                                success=False,
                                error=(
                                    f"Tag exceeds PDU: {resp_size} > {self.pdu_size}. "
                                    f"Max: {max_data} bytes."
                                ),
                            )
                        )
                    processed.add(i)

            regular_tags = [
                (i, tag) for i, tag in enumerate(list_tags) if i not in processed
            ]

            if regular_tags:
                tags_only = [t for _, t in regular_tags]
                try:
                    if optimize:
                        requests, tags_map = prepare_optimized_requests(
                            tags=tags_only, max_pdu=self.pdu_size
                        )
                        for batch in requests:
                            try:
                                resp_bytes = await self._send_unlocked(
                                    ReadRequest(tags=batch)
                                )
                                batch_map = {
                                    k: tags_map[k] for k in batch if k in tags_map
                                }
                                detailed = S7Client._parse_optimized_read_response_detailed(
                                    cast(S7Client, self), resp_bytes, batch_map
                                )
                                for orig_idx, result in detailed:
                                    if orig_idx not in processed:
                                        results.append(result)
                                        processed.add(orig_idx)
                            except Exception as e:
                                for req_tag in batch:
                                    for mapped in tags_map.get(req_tag, []):
                                        idx, orig_tag = mapped
                                        if idx not in processed:
                                            results.append(
                                                ReadResult(
                                                    tag=orig_tag,
                                                    success=False,
                                                    error=f"Request failed: {e}",
                                                )
                                            )
                                            processed.add(idx)
                    else:
                        reqs = prepare_requests(tags=tags_only, max_pdu=self.pdu_size)
                        for req in reqs:
                            try:
                                resp_bytes = await self._send_unlocked(
                                    ReadRequest(tags=req)
                                )
                                read_results = S7Client._parse_read_response_detailed(
                                    cast(S7Client, self), resp_bytes, req, None
                                )
                                for result in read_results:
                                    for orig_idx, orig_tag in regular_tags:
                                        if (
                                            orig_tag == result.tag
                                            and orig_idx not in processed
                                        ):
                                            results.append(result)
                                            processed.add(orig_idx)
                                            break
                            except Exception as e:
                                for req_tag in req:
                                    for orig_idx, orig_tag in regular_tags:
                                        if (
                                            orig_tag == req_tag
                                            and orig_idx not in processed
                                        ):
                                            results.append(
                                                ReadResult(
                                                    tag=orig_tag,
                                                    success=False,
                                                    error=f"Request failed: {e}",
                                                )
                                            )
                                            processed.add(orig_idx)
                except Exception as e:
                    for orig_idx, orig_tag in regular_tags:
                        if orig_idx not in processed:
                            results.append(
                                ReadResult(
                                    tag=orig_tag,
                                    success=False,
                                    error=f"Unexpected error: {e}",
                                )
                            )

            # Sort by original order
            results_dict: Dict[int, ReadResult] = {}
            for result in results:
                for i, tag in enumerate(list_tags):
                    if tag == result.tag and i not in results_dict:
                        results_dict[i] = result
                        break
            return [results_dict[i] for i in sorted(results_dict)]

    # -- Write -----------------------------------------------------------------

    async def write(
        self, tags: Sequence[Union[str, S7Tag]], values: Sequence[Value]
    ) -> None:
        """Write values to PLC tags.

        Args:
            tags: Sequence of string addresses or S7Tag objects.
            values: Corresponding values.

        Example:
            >>> await client.write(['DB1,I0', 'DB1,R4'], [42, 3.14])
        """
        if len(tags) != len(values):
            raise ValueError(
                "The number of tags should be equal to the number of values."
            )

        tags_list: List[S7Tag] = [
            map_address_to_tag(address=t) if isinstance(t, str) else t for t in tags
        ]
        if not tags_list:
            return

        async with self._io_lock:
            if not self.is_connected:
                raise S7CommunicationError(
                    "Not connected to PLC. Call 'connect' before performing write operations."
                )

            start_time = time() if self.metrics else None
            try:
                regular_tags: List[S7Tag] = []
                regular_values: List[Value] = []

                for i, (tag, value) in enumerate(zip(tags_list, values)):
                    req_size = WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag.size() + 4
                    if req_size > self.pdu_size:
                        if tag.data_type in (DataType.STRING, DataType.WSTRING):
                            await self._write_large_string_unlocked(tag, value)  # type: ignore
                            continue
                        max_data = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
                        raise S7AddressError(
                            f"{tag} requires {req_size} bytes but PDU is {self.pdu_size}. "
                            f"Max data: {max_data} bytes."
                        )
                    regular_tags.append(tag)
                    regular_values.append(value)

                if regular_tags:
                    reqs, reqs_vals = prepare_write_requests_and_values(
                        tags=regular_tags, values=regular_values, max_pdu=self.pdu_size
                    )
                    for i, req in enumerate(reqs):
                        resp = await self._send_unlocked(
                            WriteRequest(tags=req, values=reqs_vals[i])
                        )
                        WriteResponse(response=resp, tags=req).parse()

                if self.metrics and start_time is not None:
                    duration = time() - start_time
                    self.metrics.record_write(
                        duration, sum(t.size() for t in tags_list), success=True
                    )

            except Exception:
                if self.metrics and start_time is not None:
                    self.metrics.record_write(time() - start_time, 0, success=False)
                raise

    async def write_detailed(
        self, tags: Sequence[Union[str, S7Tag]], values: Sequence[Value]
    ) -> List[WriteResult]:
        """Write values with per-tag success/error details.

        Returns:
            List of WriteResult objects.
        """
        if not tags or not values:
            raise ValueError("Tags and values lists cannot be empty")
        if len(tags) != len(values):
            raise ValueError("Tags and values must have the same length")

        tags_list: List[S7Tag] = [
            map_address_to_tag(address=t) if isinstance(t, str) else t for t in tags
        ]

        async with self._io_lock:
            if not self.is_connected:
                raise S7CommunicationError(
                    "Not connected to PLC. Call 'connect' before performing write operations."
                )

            results: List[WriteResult] = []
            processed: set[int] = set()

            # Large strings
            for i, (tag, value) in enumerate(zip(tags_list, values)):
                req_size = WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag.size() + 4
                if req_size > self.pdu_size:
                    if tag.data_type in (DataType.STRING, DataType.WSTRING):
                        try:
                            await self._write_large_string_unlocked(tag, value)  # type: ignore
                            results.append(WriteResult(tag=tag, success=True))
                        except Exception as e:
                            results.append(
                                WriteResult(
                                    tag=tag,
                                    success=False,
                                    error=f"Large string write failed: {e}",
                                )
                            )
                    else:
                        max_data = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
                        results.append(
                            WriteResult(
                                tag=tag,
                                success=False,
                                error=(
                                    f"Tag exceeds PDU: {req_size} > {self.pdu_size}. "
                                    f"Max: {max_data}."
                                ),
                            )
                        )
                    processed.add(i)

            regular_tags = []
            regular_values = []
            regular_indices = []
            for i, (tag, val) in enumerate(zip(tags_list, values)):
                if i not in processed:
                    regular_tags.append(tag)
                    regular_values.append(val)
                    regular_indices.append(i)

            if regular_tags:
                reqs, reqs_vals = prepare_write_requests_and_values(
                    tags=regular_tags, values=regular_values, max_pdu=self.pdu_size
                )
                tag_offset = 0
                for batch_idx, req in enumerate(reqs):
                    try:
                        resp = await self._send_unlocked(
                            WriteRequest(tags=req, values=reqs_vals[batch_idx])
                        )
                        batch_results = S7Client._parse_write_response_detailed(
                            cast(S7Client, self), resp, req
                        )
                        for br in batch_results:
                            results.append(br)
                        tag_offset += len(req)
                    except Exception as e:
                        for j in range(len(req)):
                            results.append(
                                WriteResult(
                                    tag=req[j],
                                    success=False,
                                    error=f"Communication error: {e}",
                                )
                            )
                        tag_offset += len(req)

            # Sort by original order
            tag_to_idx = {id(tag): i for i, tag in enumerate(tags_list)}
            results.sort(key=lambda r: tag_to_idx.get(id(r.tag), 0))
            return results

    def batch_write(
        self,
        auto_commit: bool = True,
        rollback_on_error: bool = True,
    ) -> AsyncBatchWriteTransaction:
        """Create an async batch write transaction.

        Example:
            >>> async with client.batch_write() as batch:
            ...     batch.add('DB1,I0', 100).add('DB1,I2', 200)
        """
        return AsyncBatchWriteTransaction(
            client=self,
            auto_commit=auto_commit,
            rollback_on_error=rollback_on_error,
        )

    # -- Diagnostics -----------------------------------------------------------

    async def get_cpu_status(self) -> str:
        """Get the CPU operating status ("RUN" or "STOP")."""
        async with self._io_lock:
            if not self.is_connected:
                raise S7CommunicationError(
                    "Not connected to PLC. Call 'connect' before getting CPU status."
                )
            szl_req = SZLRequest(
                szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000
            )
            resp = await self._send_unlocked(szl_req)
            szl_resp = SZLResponse(response=resp)
            status = szl_resp.parse_cpu_status()
            self.logger.debug(f"CPU status: {status}")
            return status

    async def get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU model, hardware/firmware versions.

        Returns:
            Dict with keys: module_type_name, hardware_version,
            firmware_version, index, modules.
        """
        async with self._io_lock:
            if not self.is_connected:
                raise S7CommunicationError(
                    "Not connected to PLC. Call 'connect' before getting CPU info."
                )
            szl_req = SZLRequest(
                szl_id=SZLId.MODULE_IDENTIFICATION, szl_index=0x0000
            )
            resp = await self._send_unlocked(szl_req)
            szl_resp = SZLResponse(response=resp)
            return szl_resp.parse_cpu_info()

    # -- Large string helpers --------------------------------------------------

    async def _read_large_string(self, tag: S7Tag) -> str:
        """Read large string acquiring _io_lock for each sub-read."""
        # This variant is safe to call from outside the lock.
        return await self._read_large_string_inner(
            tag, self._send
        )

    async def _read_large_string_unlocked(self, tag: S7Tag) -> str:
        """Read large string when caller already holds _io_lock."""
        return await self._read_large_string_inner(
            tag, self._send_unlocked
        )

    async def _read_large_string_inner(
        self, tag: S7Tag, send_fn: Any
    ) -> str:
        """Shared implementation for large string reads."""
        chunks: List[str] = []

        if tag.data_type == DataType.STRING:
            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=2,
            )
            reqs = prepare_requests(tags=[header_tag], max_pdu=self.pdu_size)
            resp = await send_fn(ReadRequest(tags=reqs[0]))
            header_bytes = ReadResponse(response=resp, tags=reqs[0]).parse()[0]
            if not isinstance(header_bytes, tuple) or len(header_bytes) < 2:
                raise S7CommunicationError(
                    f"Invalid STRING header: expected tuple ≥2, got {type(header_bytes).__name__}"
                )
            current_length = int(header_bytes[1])
            if current_length == 0:
                return ""

            max_data = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
            offset = 0
            while offset < current_length:
                chunk_size = min(max_data, current_length - offset)
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.CHAR,
                    start=tag.start + 2 + offset,
                    bit_offset=0,
                    length=chunk_size,
                )
                reqs = prepare_requests(tags=[chunk_tag], max_pdu=self.pdu_size)
                resp = await send_fn(ReadRequest(tags=reqs[0]))
                chunk = ReadResponse(response=resp, tags=reqs[0]).parse()[0]
                if not isinstance(chunk, str):
                    raise S7CommunicationError(
                        f"Invalid STRING chunk: expected str, got {type(chunk).__name__}"
                    )
                chunks.append(chunk)
                offset += chunk_size
            return "".join(chunks)

        elif tag.data_type == DataType.WSTRING:
            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=4,
            )
            reqs = prepare_requests(tags=[header_tag], max_pdu=self.pdu_size)
            resp = await send_fn(ReadRequest(tags=reqs[0]))
            header_bytes = ReadResponse(response=resp, tags=reqs[0]).parse()[0]
            if not isinstance(header_bytes, tuple) or len(header_bytes) < 4:
                raise S7CommunicationError(
                    f"Invalid WSTRING header: expected tuple ≥4, got {type(header_bytes).__name__}"
                )
            max_length = (int(header_bytes[0]) << 8) | int(header_bytes[1])
            current_length = (int(header_bytes[2]) << 8) | int(header_bytes[3])
            if current_length == 0:
                return ""

            # Validate current_length does not exceed max_length
            if current_length > max_length:
                self.logger.warning(
                    "WSTRING current_length (%d) exceeds max_length (%d), clamping",
                    current_length, max_length,
                )
                current_length = max_length

            max_data = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
            bytes_to_read = current_length * 2
            offset = 0
            while offset < bytes_to_read:
                chunk_size = min(max_data, bytes_to_read - offset)
                if chunk_size % 2 != 0:
                    chunk_size -= 1
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.BYTE,
                    start=tag.start + 4 + offset,
                    bit_offset=0,
                    length=chunk_size,
                )
                reqs = prepare_requests(tags=[chunk_tag], max_pdu=self.pdu_size)
                resp = await send_fn(ReadRequest(tags=reqs[0]))
                raw = ReadResponse(response=resp, tags=reqs[0]).parse()[0]
                if not isinstance(raw, tuple):
                    raise S7CommunicationError(
                        f"Invalid WSTRING chunk: expected tuple, got {type(raw).__name__}"
                    )
                chunks.append(bytes(int(b) for b in raw).decode("utf-16-be"))
                offset += chunk_size
            return "".join(chunks)

        raise ValueError(f"Unsupported data type for large string read: {tag.data_type}")

    async def _write_large_string(self, tag: S7Tag, value: str) -> None:
        """Write large string acquiring _io_lock for each sub-write."""
        await self._write_large_string_inner(tag, value, self._send)

    async def _write_large_string_unlocked(self, tag: S7Tag, value: str) -> None:
        """Write large string when caller already holds _io_lock."""
        await self._write_large_string_inner(tag, value, self._send_unlocked)

    async def _write_large_string_inner(
        self, tag: S7Tag, value: str, send_fn: Any
    ) -> None:
        """Shared implementation for large string writes."""
        if tag.data_type == DataType.STRING:
            max_length = tag.length
            encoded = value.encode("ascii", errors="replace")
            if len(encoded) > 254:
                raise S7AddressError(
                    f"STRING length ({len(encoded)}) exceeds max 254 characters."
                )
            if len(encoded) > max_length:
                raise ValueError(
                    f"String length ({len(encoded)}) exceeds declared max ({max_length})"
                )
            current_length = len(encoded)

            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=2,
            )
            hdr_max = min(max_length, 254)
            reqs, reqs_vals = prepare_write_requests_and_values(
                tags=[header_tag], values=[(hdr_max, current_length)],
                max_pdu=self.pdu_size,
            )
            for i, req in enumerate(reqs):
                resp = await send_fn(WriteRequest(tags=req, values=reqs_vals[i]))
                WriteResponse(response=resp, tags=req).parse()
            if current_length == 0:
                return

            max_data = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
            offset = 0
            while offset < current_length:
                chunk_size = min(max_data, current_length - offset)
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.CHAR,
                    start=tag.start + 2 + offset,
                    bit_offset=0,
                    length=chunk_size,
                )
                chunk_val = encoded[offset : offset + chunk_size].decode("ascii")
                reqs, reqs_vals = prepare_write_requests_and_values(
                    tags=[chunk_tag], values=[chunk_val], max_pdu=self.pdu_size,
                )
                for i, req in enumerate(reqs):
                    resp = await send_fn(WriteRequest(tags=req, values=reqs_vals[i]))
                    WriteResponse(response=resp, tags=req).parse()
                offset += chunk_size

        elif tag.data_type == DataType.WSTRING:
            max_length = tag.length
            if len(value) > max_length:
                raise ValueError(
                    f"String length ({len(value)}) exceeds max ({max_length})"
                )
            current_length = len(value)
            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=4,
            )
            hdr_max = min(max_length, 65535)
            hdr = (
                (hdr_max >> 8) & 0xFF,
                hdr_max & 0xFF,
                (current_length >> 8) & 0xFF,
                current_length & 0xFF,
            )
            reqs, reqs_vals = prepare_write_requests_and_values(
                tags=[header_tag], values=[hdr], max_pdu=self.pdu_size,
            )
            for i, req in enumerate(reqs):
                resp = await send_fn(WriteRequest(tags=req, values=reqs_vals[i]))
                WriteResponse(response=resp, tags=req).parse()
            if current_length == 0:
                return

            max_data = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
            encoded_ws = value.encode("utf-16-be")
            bytes_to_write = len(encoded_ws)
            offset = 0
            while offset < bytes_to_write:
                chunk_size = min(max_data, bytes_to_write - offset)
                if chunk_size % 2 != 0:
                    chunk_size -= 1
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.BYTE,
                    start=tag.start + 4 + offset,
                    bit_offset=0,
                    length=chunk_size,
                )
                chunk_bytes = encoded_ws[offset : offset + chunk_size]
                reqs, reqs_vals = prepare_write_requests_and_values(
                    tags=[chunk_tag], values=[tuple(b for b in chunk_bytes)],
                    max_pdu=self.pdu_size,
                )
                for i, req in enumerate(reqs):
                    resp = await send_fn(WriteRequest(tags=req, values=reqs_vals[i]))
                    WriteResponse(response=resp, tags=req).parse()
                offset += chunk_size
        else:
            raise ValueError(
                f"Unsupported data type for large string write: {tag.data_type}"
            )

    # -- Internal: unlocked send (caller already holds _io_lock) ---------------

    async def _send_unlocked(self, request: Request) -> bytes:
        """Send/receive without acquiring _io_lock (caller must hold it)."""
        if not isinstance(request, Request):
            raise ValueError(f"Request type {type(request).__name__} not supported")

        try:
            if self._writer is None or self._reader is None:
                raise S7CommunicationError(
                    "Stream is not initialized. Call connect() first."
                )
            data = request.serialize()
            self.logger.debug(f"TX -> PLC: {len(data)} bytes [TPKT+COTP+S7]")
            self._writer.write(data)
            await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)

            header = await self._recv_exact(TPKT_SIZE)
            if len(header) < 4:
                raise S7CommunicationError(
                    "Incomplete TPKT header received from the PLC."
                )
            tpkt_length = int.from_bytes(header[2:4], byteorder="big")
            if tpkt_length < 4:
                raise S7CommunicationError(
                    "Invalid TPKT length received from the PLC."
                )
            body = await self._recv_exact(tpkt_length - 4)
            return header + body

        except asyncio.TimeoutError as e:
            msg = f"Communication timeout after {self.timeout}s"
            self.logger.error(msg)
            self._set_connection_state(ConnectionState.ERROR, msg)
            # Cleanup without acquiring the lock (caller already holds it)
            self._cleanup_streams()
            self._set_connection_state(ConnectionState.DISCONNECTED)
            raise S7TimeoutError(msg) from e
        except OSError as e:
            msg = f"Socket error during communication: {e}"
            self.logger.error(msg)
            self._set_connection_state(ConnectionState.ERROR, msg)
            self._cleanup_streams()
            self._set_connection_state(ConnectionState.DISCONNECTED)
            raise S7CommunicationError(msg) from e
