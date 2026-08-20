"""Internal conversion helpers for the Siemens TIME datatype."""

from datetime import timedelta


def timedelta_to_milliseconds(value: timedelta) -> int:
    """Convert an exactly millisecond-aligned timedelta to signed int32."""
    if not isinstance(value, timedelta):
        raise TypeError(f"TIME data must be timedelta, got {type(value).__name__}")
    total_microseconds = (
        value.days * 86_400 + value.seconds
    ) * 1_000_000 + value.microseconds
    if total_microseconds % 1_000:
        raise ValueError("TIME data must have exact millisecond precision")
    milliseconds = total_microseconds // 1_000
    if not -(2**31) <= milliseconds <= 2**31 - 1:
        raise ValueError("TIME data is outside the signed 32-bit millisecond range")
    return milliseconds
