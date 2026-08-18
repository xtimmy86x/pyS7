"""Shared result structures returned by synchronous and asynchronous clients."""

from dataclasses import dataclass

from .requests import Value
from .tag import S7Tag


@dataclass
class WriteResult:
    """Result of a single write operation."""

    tag: S7Tag
    success: bool
    error: str | None = None
    error_code: int | None = None


@dataclass
class ReadResult:
    """Result of a single read operation."""

    tag: S7Tag
    success: bool
    value: Value | None = None
    error: str | None = None
    error_code: int | None = None
