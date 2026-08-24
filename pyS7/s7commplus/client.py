"""Experimental synchronous low-level symbolic client."""

from collections.abc import Sequence
from types import TracebackType
from typing import Type

from ..errors import S7CommPlusProtocolError
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


class S7CommPlusClient:
    """Explicit S7CommPlus backend; it never replaces or falls back from S7Client."""

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0
    ) -> None:
        self._connection = S7CommPlusConnection(host, port, timeout)

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
        self._connection.connect(
            use_tls=use_tls,
            tls_ca=tls_ca,
            tls_cert=tls_cert,
            tls_key=tls_key,
            tls_verify=tls_verify,
        )

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

    def explore_raw(self, rid: int, attribute_ids: Sequence[int] = ()) -> bytes:
        """Return a complete EXPLORE application payload without interpreting types."""
        payload = build_explore_request(rid, tuple(attribute_ids))
        return self._connection.request(FunctionCode.EXPLORE, payload, integrity_tail=5)

    def list_datablocks(self) -> list[S7DataBlockInfo]:
        """Enumerate DB objects in the order supplied by PLC metadata."""
        raw = self.explore_raw(
            PLC_PROGRAM_RID,
            (OBJECT_VARIABLE_TYPE_NAME_AID, BLOCK_NUMBER_AID),
        )
        return parse_datablocks(raw)

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
        return tags

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
