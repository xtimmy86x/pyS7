# pyS7 3.0.0 release notes

These notes describe pyS7 3.0.0.

## Highlights

- Python 3.11+ baseline and CI coverage through Python 3.14.
- Shared sync/async protocol internals for more consistent behavior and
  maintainability; this refactor is not a user migration requirement.
- More compatible optimized BIT reads using the containing BYTE and a local mask.
- Strict batch-write failure reporting with `BatchWriteError` and optional
  best-effort rollback.
- Correct UTF-16-BE WSTRING sizing, non-BMP Unicode support, and safe chunking.
- Structured PLC item errors with tag, raw return code, and operation metadata.
- Modernized packaging, type, formatting, lint, test, and CI checks.

## Breaking changes

### Python support

pyS7 3.0 requires Python 3.11 or newer. Python 3.8, 3.9, and 3.10 users must
upgrade Python or remain on a suitable pyS7 2.x version.

### Batch failures raise

Successful sync and async commits return ordered `WriteResult` lists. Any
failed write raises `BatchWriteError`, including when
`rollback_on_error=False`. Rollback controls best-effort restoration only; it
does not provide PLC-level atomicity or read-back verification.

## Improvements and correctness fixes

- With `optimize=True`, BIT reads use the containing BYTE and local extraction;
  `optimize=False` retains native BIT reads. BIT writes remain native bit-level
  S7 writes rather than read-modify-write.
- WSTRING payloads are UTF-16-BE with `max_length * 2` bytes of capacity.
  Logical current length counts Python Unicode characters, while capacity is
  measured in UTF-16 code units. Normal and chunked reads/writes preserve
  surrogate pairs.
- `S7ReadResponseError` and `S7WriteResponseError` expose `tag`, `error_code`,
  and `operation`; their existing string form remains usable.
- `read_detailed()` and `write_detailed()` retain per-tag `ReadResult` and
  `WriteResult` reporting for ordinary PLC item failures.

## Compatibility

Python 3.11, 3.12, 3.13, and 3.14 are CI targets. PLC compatibility remains
dependent on family, firmware, security, connection, and DB configuration. The
[compatibility matrix](COMPATIBILITY.md) separates actual hardware observations
from protocol/unit tests and expected behavior.
Hardware validation includes S7-300, S7-1200, S7-1500,
LOGO! 0BA7, and LOGO! 0BA8. Feature-specific validation
is documented separately in the compatibility matrix.

## Migration checklist

- [ ] Run on Python 3.11 or newer.
- [ ] Catch `BatchWriteError` around sync and async batch commits.
- [ ] Remove assumptions that a mixed batch result can be returned silently.
- [ ] Verify absolute-address DB configuration and PLC communication access.
- [ ] Test Unicode-heavy WSTRING values against UTF-16 code-unit capacity.
- [ ] Run application and hardware tests on the deployed CPU/firmware.

For examples and full guidance, see
[Migrating from pyS7 2.x to 3.0](MIGRATION_3_0.md).
