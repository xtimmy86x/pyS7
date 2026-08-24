"""Experimental synchronous low-level symbolic client."""

from collections.abc import Sequence
from types import TracebackType
from typing import Any, Type

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
    parse_symbolic_read,
    parse_symbolic_write,
)
from .connection import S7CommPlusConnection
from .protocol import DEFAULT_PORT, FunctionCode
from .tag import S7SymbolicTag
from .value import decode_symbolic_value


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
        self._clear_session_caches()
        self._connection.connect(
            use_tls=use_tls,
            tls_ca=tls_ca,
            tls_cert=tls_cert,
            tls_key=tls_key,
            tls_verify=tls_verify,
        )

    def disconnect(self) -> None:
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
        """Discover flat scalar members of one DB, or of every visible DB."""
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
        """Resolve an exact, case-sensitive flat DB scalar name."""
        cached = self._symbol_cache.get(name)
        if cached is not None:
            return cached
        db_name, separator, member_name = name.partition(".")
        if not separator or not db_name or not member_name or "." in member_name:
            raise S7CommPlusSymbolNotFoundError(
                f"flat symbolic tag {name!r} was not found"
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
        """Resolve and read one flat symbolic scalar as a Python value."""
        tag = self.resolve_tag(name)
        if not isinstance(tag.data_type, DataType):
            raise S7CommPlusProtocolError(
                f"symbolic tag {name!r} has no supported scalar data type"
            )
        raw = self.read_symbolic(tag.access_area, tag.access_sequence, tag.symbol_crc)
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
