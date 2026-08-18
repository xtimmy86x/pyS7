# Compatibility

This matrix records evidence for the upcoming pyS7 3.0 release. Protocol
support does not by itself prove compatibility with every CPU, firmware,
security setting, or DB layout.

## Legend

- ✅ **Hardware tested** — exercised against an actual PLC; scope is stated.
- 🧪 **Protocol/unit tested** — automated packet or logic tests, without
  confirmed hardware evidence for that family.
- ⚠️ **Expected / limited / configuration-dependent** — implemented or
  historically documented, but not currently hardware-verified here.
- ❌ **Unsupported** — not implemented by pyS7.

> The symbols in feature columns primarily indicate the level of validation for
> that PLC family. `⚠️` can therefore mean that a feature is implemented by
> pyS7 but has not been hardware-verified for that family. `❌` specifically
> means that the feature is not supported for that family.

## PLC families

| PLC family | Basic read | Basic write | BIT | STRING | WSTRING | SZL / CPU info | Hardware validation and notes |
|---|---|---|---|---|---|---|---|
| S7-200 | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ | Historically documented as compatible; no family-specific hardware record was found. Connection/address capabilities can differ by CPU. |
| S7-200 Smart | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ | Expected S7 protocol compatibility, but not currently hardware-verified in this repository. |
| S7-300 | ✅ | ✅ | 🧪 | ⚠️ | ❌ | 🧪 | Maintainer hardware use confirms basic reads and writes; feature-level coverage remains conservative. |
| S7-400 | ⚠️ | ⚠️ | 🧪 | ⚠️ | ❌ | 🧪 | Packet/logic tests cover the common protocol paths, not a recorded S7-400 hardware run. |
| S7-1200 | ✅ | ✅ | 🧪 | ⚠️ | ⚠️ | ✅ | Maintainer hardware use confirms basic reads and writes, and repository notes record CPU-information testing. Absolute DB access is configuration-dependent. |
| S7-1500 | ✅ | ✅ | 🧪 | ⚠️ | ⚠️ | 🧪 | Maintainer hardware use confirms basic reads and writes; feature-level coverage remains conservative and configuration-dependent. |
| LOGO! 0BA7 | ✅ | ✅ | 🧪 | ❌ | ❌ | ❌ | Maintainer hardware use confirms basic reads and writes; limited/legacy addressing and TSAP configuration are device-dependent. |
| LOGO! 0BA8 | ✅ | ✅ | 🧪 | ❌ | ❌ | ❌ | Maintainer hardware use confirms basic reads and writes; limited/legacy addressing and TSAP configuration are device-dependent. |

Hardware use confirms the basic read/write scope shown for S7-300, S7-1200,
S7-1500, LOGO! 0BA7, and LOGO! 0BA8. Feature-column evidence is intentionally
separate and conservative: automated tests exercise shared read/write, BIT,
STRING/WSTRING, PDU, TSAP, and SZL protocol logic without identifying a
physical PLC family.

## WSTRING hardware evidence

During pyS7 3.0 development, WSTRING behavior was verified against real Siemens
S7 hardware with a negotiated PDU of 240. The checks covered both normal and
large/chunked paths, ASCII, BMP and non-BMP Unicode/emoji, a multi-item WSTRING
plus following USINT write, and small-PDU chunking. For `"🌍"`, the PLC was
observed with `max_length = 254`, logical `current_length = 1`, and payload
bytes `D8 3C DF 0D`.

The CPU model and firmware were not recorded in the available evidence, so this
validation is deliberately not assigned to a family in the table and is not a
claim about every Siemens CPU or firmware.

## PLC-side prerequisites

pyS7 uses classic S7 communication and absolute addresses such as `DB1,I0`,
`DB1,R4`, and `DB1,X0.0`. For S7-1200/1500, absolute DB addressing generally
requires a DB layout compatible with absolute offsets. Depending on CPU and
security configuration, PUT/GET-style communication access may also need to be
enabled. Consult the Siemens documentation for the specific CPU, firmware, and
TIA Portal version.

Siemens optimized block access can make absolute DB offsets unavailable or
unstable. It is unrelated to pyS7 read optimization: `optimize=True` groups
requests and reads BITs through containing BYTEs; it does not enable Siemens
optimized DB access.

## Connections and PDU negotiation

Both `S7Client` and `AsyncS7Client` accept rack/slot configuration or explicit
local and remote TSAP values. Rack/slot connections support `ConnectionType.PG`,
`ConnectionType.OP`, and `ConnectionType.S7Basic`. Exact rack, slot, TSAP, and
access settings remain PLC/configuration-dependent.

pyS7 requests a configured PDU size and uses the size negotiated by the PLC for
operations. STRING and WSTRING values are transparently chunked where needed.
Do not assume every oversized data type is chunked; split other large arrays or
values at the caller when they cannot fit the negotiated PDU.

## Python

| Python | Upcoming pyS7 3.0 |
|---|---|
| 3.8 | ❌ unsupported; use pyS7 2.x or upgrade Python |
| 3.9 | ❌ unsupported; use pyS7 2.x or upgrade Python |
| 3.10 | ❌ unsupported; use pyS7 2.x or upgrade Python |
| 3.11 | ✅ supported and targeted by CI |
| 3.12 | ✅ supported and targeted by CI |
| 3.13 | ✅ supported and targeted by CI |
| 3.14 | ✅ supported and targeted by CI |

The package metadata declares `requires-python = ">=3.11"`.
