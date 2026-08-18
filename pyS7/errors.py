"""Custom exceptions for the pyS7 package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .results import WriteResult
    from .tag import S7Tag


class S7Error(Exception):
    """Base class for all pyS7 specific exceptions."""

    def __init__(self, message: Optional[str] = None) -> None:  # noqa: D401
        """Initialize the exception with an optional *message*."""
        super().__init__(message)


class BatchWriteError(S7Error):
    """Raised when a strict batch write cannot complete successfully.

    ``results`` contains the per-tag write responses, and is empty when the
    operation was aborted before writing (for example, if its rollback
    snapshot failed). Rollback metadata describes a best-effort restoration;
    it does not imply PLC-level atomicity.
    """

    def __init__(
        self,
        message: str,
        results: list[WriteResult] | None = None,
        *,
        rollback_attempted: bool = False,
        rollback_succeeded: bool | None = None,
        rollback_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.results = list(results or [])
        self.rollback_attempted = rollback_attempted
        self.rollback_succeeded = rollback_succeeded
        self.rollback_error = rollback_error


class S7ConnectionError(S7Error):
    """Raised when a connection to a S7 PLC could not be established."""

    pass


class S7CommunicationError(S7Error):
    """Raised when an error occurs during communication with a S7 PLC (reading or writing)."""

    pass


class S7AddressError(S7Error):
    """Raised when a string address cannot be parsed in a S7Tag."""

    pass


class S7ReadResponseError(S7Error):
    """Raised when the PLC rejects a read item."""

    def __init__(
        self,
        message: str | None = None,
        *,
        tag: S7Tag | None = None,
        error_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.tag = tag
        self.error_code = error_code
        self.operation = "read"


class S7WriteResponseError(S7Error):
    """Raised when the PLC rejects a write item."""

    def __init__(
        self,
        message: str | None = None,
        *,
        tag: S7Tag | None = None,
        error_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.tag = tag
        self.error_code = error_code
        self.operation = "write"


class S7TimeoutError(S7CommunicationError):
    """Raised when a communication timeout occurs."""

    pass


class S7ProtocolError(S7CommunicationError):
    """Raised when an invalid protocol response is received."""

    pass


class S7PDUError(S7Error):
    """Raised when PDU size limits are exceeded."""

    pass
