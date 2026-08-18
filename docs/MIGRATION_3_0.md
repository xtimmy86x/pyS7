# Migrating from pyS7 2.x to 3.0

This guide describes the user-visible contract for the upcoming pyS7 3.0
release. It is a migration guide, not an announcement that 3.0 has been
released.

## At a glance

| Change | Action required |
|---|---|
| Python 3.8, 3.9, or 3.10 | Upgrade to Python 3.11 or newer |
| Batch commit failures | Catch `BatchWriteError` |
| Optimized BIT reads | Usually none; keep `optimize=True` unless diagnosing native reads |
| WSTRING Unicode behavior | Usually none; check UTF-16 code-unit capacity assumptions |
| Structured read/write exceptions | None; optional metadata was added |
| `ReadResult` / `WriteResult` | None; the existing result fields remain available |
| `AsyncS7Client` | None for the major existing operations; retain `await`/`async with` |

## Breaking change: Python 3.11 or newer

pyS7 3.0 intentionally declares `requires-python = ">=3.11"`. Python 3.8,
3.9, and 3.10 users must upgrade Python before installing pyS7 3.0. If an
application cannot move to Python 3.11 or newer, pyS7 2.x is the appropriate
version; this document makes no promise about a support timeline for 2.x.

The project CI exercises Python 3.11, 3.12, 3.13, and 3.14. See the
[compatibility matrix](COMPATIBILITY.md#python).

## Breaking change: strict batch failures

In 2.x, a batch commit could return `WriteResult` objects containing failures
without necessarily raising. In 3.0:

- a successful commit returns an ordered `list[WriteResult]`; and
- any failed write raises `BatchWriteError`.

This is also true with `rollback_on_error=False`. That option controls whether
restoration is attempted, not whether a failure is raised.

Conceptual 2.x handling:

```python
results = batch.commit()
if not all(result.success for result in results):
    print("one or more writes failed")
```

3.0 handling:

```python
from pyS7 import BatchWriteError

try:
    results = batch.commit()
except BatchWriteError as exc:
    for result in exc.results:
        print(result.tag, result.success, result.error, result.error_code)
    print(exc.rollback_attempted)
    print(exc.rollback_succeeded)
    print(exc.rollback_error)
```

`BatchWriteError.results` preserves the ordered per-tag write results (and can
be empty when the operation failed before writing). `rollback_attempted`,
`rollback_succeeded`, and `rollback_error` describe restoration. Rollback is
best effort, not PLC-level atomicity: PLC logic or another client can observe
or change values between writes, and restoration itself can fail. A successful
write response is not read-back verification. The async batch returned by
`AsyncS7Client.batch_write()` follows the same failure rule with
`await batch.commit()`.

See [Batch writes](API_REFERENCE.md#batch-writes).

## BIT reads and writes

`client.read(tags, optimize=True)` (the default) reads each requested BIT
through its containing BYTE and extracts the bit locally. This avoids native
individual BIT-read compatibility problems seen with some PLC/configuration
combinations. `optimize=False` sends native S7 BIT reads. There is no
separate optimized-read method.

BIT writes continue to use native S7 BIT writes; they are not byte-level
read-modify-write operations. See [BIT read troubleshooting](TROUBLESHOOTING_BIT_READ.md).

## WSTRING Unicode and capacity

WSTRING uses UTF-16-BE and has `max_length * 2` payload bytes. Its header's
logical `current_length` is the Python Unicode character count, while capacity
is measured in UTF-16 code units. A non-BMP character such as `🌍` consumes two
code units even though `len("🌍") == 1`.

For `WSTRING[254]`:

| Value | Result | UTF-16 code units |
|---|---|---:|
| `"A" * 254` | valid | 254 |
| `"🌍" * 127` | valid | 254 |
| `"A" * 252 + "🌍"` | valid | 254 |
| `"🌍" * 128` | invalid | 256 |
| `"A" * 253 + "🌍"` | invalid | 255 |

The total declared storage remains `4 + max_length * 2` bytes. Both normal and
chunked WSTRING paths support non-BMP characters. See
[WSTRING](API_REFERENCE.md#wstring-unicode) and the hardware-evidence notes in
the [compatibility matrix](COMPATIBILITY.md#wstring-hardware-evidence).

## Structured exceptions and detailed results

`S7ReadResponseError` and `S7WriteResponseError` remain available and now expose
`tag`, `error_code`, and `operation`. `error_code` is the raw integer PLC item
return code when one is available. Existing code that catches these exceptions
or uses `str(exc)` continues to work.

```python
from pyS7 import S7Client, S7ReadResponseError

with S7Client(address="192.168.1.10", rack=0, slot=1) as client:
    try:
        client.read(["DB99,I0"])
    except S7ReadResponseError as exc:
        print(exc.tag)
        print(exc.error_code)
        print(exc.operation)
```

`read_detailed()` and `write_detailed()` continue to return per-tag
`ReadResult` and `WriteResult` objects rather than raising for normal PLC item
failures. Their `tag`, `success`, `error`, and `error_code` fields are unchanged
by structured exceptions (`ReadResult` additionally has `value`). See
[Error handling](API_REFERENCE.md#error-handling).

## PLC configuration check

pyS7 addresses memory by absolute offsets, for example `DB1,I0`, `DB1,R4`, and
`DB1,X0.0`. For S7-1200/1500, absolute DB addressing generally requires a DB
layout compatible with absolute offsets. Depending on CPU and security
configuration, PUT/GET-style communication access may also need to be enabled.
Consult the documentation for the exact CPU, firmware, and engineering tool.

Siemens **optimized block access** is a PLC DB-layout feature. It is unrelated
to pyS7's `read(..., optimize=True)` request grouping and BYTE-based BIT reads.

## Migration checklist

- [ ] Python is 3.11 or newer.
- [ ] Batch callers catch `BatchWriteError` (including async callers).
- [ ] No code relies on mixed/silent batch failure results.
- [ ] Application tests pass with the upcoming pyS7 3.0 release.
- [ ] PLC configuration and DB layouts support absolute addressing.
- [ ] WSTRING-heavy code tests its UTF-16 code-unit capacity assumptions.
- [ ] Hardware-dependent behavior is validated on the application's CPUs and firmware.

The public sync and async client imports and detailed result types remain
available. This is not a claim that a particular downstream integration has
already completed its own pyS7 3.0 validation.