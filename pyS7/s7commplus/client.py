"""Experimental synchronous low-level symbolic client."""

import logging
import struct
from collections.abc import Sequence
from types import TracebackType
from typing import Any, Type, cast

from ..constants import DataType
from ..errors import S7CommPlusProtocolError, S7CommPlusSymbolNotFoundError
from .browse import (
    BLOCK_NUMBER_AID,
    OBJECT_VARIABLE_TYPE_NAME_AID,
    OMS_TYPE_INFO_CONTAINER_RID,
    PLC_PROGRAM_RID,
    S7DataBlockInfo,
    build_explore_request,
    parse_datablocks,
    parse_type_info,
)
from .codec import (
    build_symbolic_read,
    build_symbolic_write,
    encode_object_qualifier,
    parse_symbolic_read,
    parse_symbolic_write,
)
from .connection import S7CommPlusConnection, _RequestContext
from .protocol import DEFAULT_PORT, FunctionCode, ProtocolVersion
from .tag import S7SymbolicTag
from .value import decode_symbolic_value
from .vlq import decode_uint64, encode_uint32

logger = logging.getLogger(__name__)


class S7CommPlusClient:
    """Explicit S7CommPlus backend; it never replaces or falls back from S7Client."""

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0
    ) -> None:
        self._connection = S7CommPlusConnection(host, port, timeout)
        self._symbol_cache: dict[str, S7SymbolicTag] = {}
        self._datablock_cache: list[S7DataBlockInfo] | None = None

    @property
    def connected(self) -> bool:
        return self._connection.connected

    @property
    def protocol_version(self) -> int:
        return self._connection.protocol_version

    @property
    def session_id(self) -> int:
        return self._connection.session_id

    @property
    def tls_active(self) -> bool:
        return self._connection.tls_active

    @property
    def negotiated_initial_version(self) -> int:
        return self._connection.negotiated_initial_version

    @property
    def protection_level(self) -> int | None:
        return self._connection.protection_level

    @property
    def integrity_id_read(self) -> int:
        return self._connection.integrity_id_read

    @property
    def integrity_id_write(self) -> int:
        return self._connection.integrity_id_write

    @property
    def authentication_supported(self) -> bool:
        return False

    @property
    def last_response(self) -> bytes:
        return self._connection.last_response

    def connect(
        self,
        *,
        use_tls: bool = False,
        tls_ca: str | None = None,
        tls_cert: str | None = None,
        tls_key: str | None = None,
        tls_verify: bool = False,
    ) -> None:
        # Reconnecting an already-live public client must first destroy the
        # server-side session object. S7CommPlus sessions are explicit PLC
        # objects; merely replacing the TCP socket can leave them allocated.
        if self._connection.connected:
            self.disconnect()
        else:
            self._clear_session_caches()
        self._connection.connect(
            use_tls=use_tls,
            tls_ca=tls_ca,
            tls_cert=tls_cert,
            tls_key=tls_key,
            tls_verify=tls_verify,
        )

    def _delete_server_session(self) -> None:
        """Best-effort protocol teardown of the current server session object."""
        connection = self._connection
        if not connection.connected or not connection.session_id:
            return

        session_id = connection.session_id
        iid = connection.integrity_id_write
        sequence = connection._sequence
        context = _RequestContext(
            sequence,
            iid if connection._with_integrity else None,
            FunctionCode.DELETE_OBJECT,
            False,
        )

        payload = (
            struct.pack(">I", session_id)
            + b"\x00"
            + encode_object_qualifier(ProtocolVersion.V2)
        )
        if connection._with_integrity:
            payload += encode_uint32(iid)
            connection._integrity_write = (iid + 1) & 0xFFFFFFFF
        payload += struct.pack(">I", 0)

        response = cast(
            bytes,
            connection._exchange(
                FunctionCode.DELETE_OBJECT,
                payload,
                session_id,
                flags=0x34,
                version=connection.protocol_version,
                context=context,
            ),
        )
        # Deleting our own Session Object-ID is a special S7CommPlus case:
        # the V2 request carries the write IntegrityId, but the PLC response
        # does not carry a response IntegrityId because the session object no
        # longer exists. Do not pass this response through generic V2 IID
        # normalization.
        status, _ = decode_uint64(response)
        if status:
            logger.debug(
                "DeleteObject returned status 0x%x for session 0x%08x",
                status,
                session_id,
            )

    def disconnect(self) -> None:
        try:
            if self._connection.connected:
                try:
                    self._delete_server_session()
                except Exception:
                    # Teardown is best-effort. A PLC that already dropped the
                    # transport must never prevent local socket/TLS cleanup.
                    logger.debug(
                        "S7CommPlus DeleteObject teardown failed; closing transport",
                        exc_info=True,
                    )
        finally:
            try:
                self._connection.disconnect()
            finally:
                self._clear_session_caches()

    def _clear_session_caches(self) -> None:
        self._symbol_cache.clear()
        self._datablock_cache = None

    def clear_symbol_cache(self) -> None:
        """Forget symbols discovered during this connection."""
        self._symbol_cache.clear()

    def read_symbolic(
        self, access_area: int, access_sequence: Sequence[int], symbol_crc: int = 0
    ) -> bytes:
        """Read a symbolic address, optionally with an explicit ItemAddress CRC."""
        payload = build_symbolic_read(
            access_area, access_sequence, symbol_crc, self._connection.protocol_version
        )
        return parse_symbolic_read(
            self._connection.request(FunctionCode.GET_MULTI_VARIABLES, payload)
        )

    def read_symbolic_raw(self, tag: S7SymbolicTag) -> bytes:
        return self.read_symbolic(tag.access_area, tag.access_sequence, tag.symbol_crc)

    def explore_raw(self, rid: int, attribute_ids: Sequence[int] = ()) -> bytes:
        """Return a complete EXPLORE application payload without interpreting types."""
        payload = build_explore_request(rid, tuple(attribute_ids))
        return self._connection.request(FunctionCode.EXPLORE, payload, integrity_tail=5)

    def list_datablocks(self) -> list[S7DataBlockInfo]:
        """Enumerate DB objects in the order supplied by PLC metadata."""
        if self._datablock_cache is not None:
            return list(self._datablock_cache)
        raw = self.explore_raw(
            PLC_PROGRAM_RID,
            (OBJECT_VARIABLE_TYPE_NAME_AID, BLOCK_NUMBER_AID),
        )
        datablocks = parse_datablocks(raw)
        self._datablock_cache = datablocks
        return list(datablocks)

    def resolve_type_info_rid(self, access_area: int) -> int:
        """Resolve a DB's type-information RID through symbolic metadata LID 1."""
        raw = self.read_symbolic(access_area, (1,), 0)
        if len(raw) != 4:
            raise S7CommPlusProtocolError("DB type-info RID is not a four-byte RID")
        rid = int.from_bytes(raw, "big")
        if not rid:
            raise S7CommPlusProtocolError("PLC returned a zero DB type-info RID")
        return rid

    def retrieve_type_info_raw(self, access_area: int) -> tuple[int, bytes]:
        """Resolve a DB type RID and capture the unparsed OMS type-info container."""
        rid = self.resolve_type_info_rid(access_area)
        return rid, self.explore_raw(OMS_TYPE_INFO_CONTAINER_RID)

    def browse(self, db_number: int | None = None) -> list[S7SymbolicTag]:
        """Discover supported scalar leaves in one DB, or in every visible DB."""
        datablocks = self.list_datablocks()
        if db_number is not None:
            datablocks = [db for db in datablocks if db.number == db_number]
            if not datablocks:
                raise S7CommPlusProtocolError(f"DB{db_number} was not found")
        tags: list[S7SymbolicTag] = []
        for db in datablocks:
            rid, payload = self.retrieve_type_info_raw(db.access_area)
            tags.extend(
                parse_type_info(
                    payload, rid, db_name=db.name, access_area=db.access_area
                )
            )
        self._cache_symbols(tags)
        return tags

    def _cache_symbols(self, tags: Sequence[S7SymbolicTag]) -> None:
        seen: set[str] = set()
        for tag in tags:
            if tag.name in seen:
                raise S7CommPlusProtocolError(f"ambiguous symbolic name {tag.name!r}")
            seen.add(tag.name)
            cached = self._symbol_cache.get(tag.name)
            if cached is not None and cached != tag:
                raise S7CommPlusProtocolError(f"ambiguous symbolic name {tag.name!r}")
            self._symbol_cache[tag.name] = tag

    def resolve_tag(self, name: str) -> S7SymbolicTag:
        """Resolve an exact, case-sensitive scalar DB symbol, including nested paths."""
        cached = self._symbol_cache.get(name)
        if cached is not None:
            return cached
        db_name, separator, member_path = name.partition(".")
        if (
            not separator
            or not db_name
            or not member_path
            or any(not part for part in member_path.split("."))
        ):
            raise S7CommPlusSymbolNotFoundError(
                f"symbolic tag {name!r} was not found"
            )
        matches = [db for db in self.list_datablocks() if db.name == db_name]
        if not matches:
            raise S7CommPlusSymbolNotFoundError(f"data block {db_name!r} was not found")
        if len(matches) != 1:
            raise S7CommPlusProtocolError(f"ambiguous data block name {db_name!r}")
        self.browse(matches[0].number)
        try:
            return self._symbol_cache[name]
        except KeyError as exc:
            raise S7CommPlusSymbolNotFoundError(
                f"symbolic tag {name!r} was not found"
            ) from exc

    def read_tag(self, name: str) -> Any:
        """Resolve and read one supported symbolic scalar leaf as a Python value."""
        tag = self.resolve_tag(name)
        if not isinstance(tag.data_type, DataType):
            raise S7CommPlusProtocolError(
                f"symbolic tag {name!r} has no supported scalar data type"
            )
        # The PVartypeList CRC is descriptive metadata, not the ItemAddress CRC
        # used by an ordinary GET_MULTI_VARIABLES request.
        raw = self.read_symbolic(tag.access_area, tag.access_sequence, 0)
        return decode_symbolic_value(tag.data_type, raw)

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
        self.connect(use_tls=True)
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()
