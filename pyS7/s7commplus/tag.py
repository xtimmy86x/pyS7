"""Symbolic addressing model, intentionally separate from classic S7Tag."""

from dataclasses import dataclass
from typing import Any

from .codec import validate_access


@dataclass(frozen=True)
class S7SymbolicTag:
    access_area: int
    access_sequence: tuple[int, ...]
    data_type: Any | None = None
    name: str = ""
    symbol_crc: int = 0

    def __post_init__(self) -> None:
        lids = validate_access(self.access_area, self.access_sequence, self.symbol_crc)
        object.__setattr__(self, "access_sequence", lids)
