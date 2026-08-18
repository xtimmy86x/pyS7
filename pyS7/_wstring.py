"""Internal helpers for Siemens WSTRING storage semantics."""

from .errors import S7AddressError
from .tag import S7Tag


def encode_wstring(value: str, max_length: int, tag: S7Tag) -> bytes:
    """Encode *value* and validate its UTF-16 storage requirement."""
    if not isinstance(value, str):
        raise S7AddressError(f"WSTRING data must be str, got {type(value).__name__}")
    encoded = value.encode("utf-16-be")
    utf16_units = len(encoded) // 2
    if utf16_units > max_length:
        raise S7AddressError(
            f"WSTRING data too long for {tag}: requires {utf16_units} UTF-16 "
            f"code units, capacity is {max_length}"
        )
    return encoded