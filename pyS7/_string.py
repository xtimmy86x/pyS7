"""Single-byte encoding shared by STRING and CHAR writes."""

from .errors import S7AddressError
from .tag import S7Tag


def encode_string(value: str, tag: S7Tag, encoding: str = "latin-1") -> bytes:
    """Encode without replacing characters that the PLC cannot represent."""
    if not isinstance(value, str):
        raise S7AddressError(
            f"{tag.data_type.name} data must be str, got {type(value).__name__}"
        )
    try:
        return value.encode(encoding)
    except UnicodeEncodeError as exc:
        raise S7AddressError(
            f"{tag.data_type.name} data for {tag} cannot be encoded as {encoding}"
        ) from exc
