# Experimental S7CommPlus symbolic access

S7CommPlus is an explicitly selected backend for optimized S7-1200/1500 data.
Classic `S7Client` remains the S7Comm/S7ANY byte-addressed client; importing it
does not import this package and there is no fallback or automatic protocol
switch. `S7CommPlusClient` addresses a value by a known AccessArea and LID path.

## Implemented transport/session subset

The supported path is:

```
DISCONNECTED -> TCP_CONNECTED -> COTP_CONNECTED -> INITSSL_COMPLETE (V1)
 -> TLS_ACTIVE -> SESSION_CREATED -> SETUP_SESSION -> SESSION_READY_V2
```

TLS uses the standard-library `ssl.SSLObject` and two `ssl.MemoryBIO` objects.
TLS records are COTP Data payloads: the TCP socket itself is **not** wrapped.
Partial TLS input, multiple records, partial decrypted S7CommPlus frames, and
BIO output draining are handled with bounded buffers. TLS 1.2 is the minimum;
OpenSSL may negotiate TLS 1.3. The legacy TLS 1.2 cipher list is deliberately
narrow, and the advertised EC group is restricted to X25519 with prime256v1 as
a fallback because Siemens peers reject some broader ClientHello profiles.
An environment supporting neither group raises `S7CommPlusTLSError`.

Siemens device certificates frequently are not rooted in the host public-PKI
store. Consequently certificate verification is a visible choice:
`tls_verify=False` (the current default, and emitted as a warning) encrypts the
channel but does **not** authenticate the PLC. For authenticated TLS, supply a
PLC CA with `tls_ca=...` and set `tls_verify=True`; hostname verification is
then enabled. The API never claims an unverified connection is verified.
No third-party crypto dependency is required.

After CreateObject the raw ServerSessionVersion is boundedly parsed and echoed
in the V2 SetupSession request. V2 read/write IntegrityIds are inserted and
advanced centrally by the connection request layer, and are reset with every
disconnect, failed connect, RST, and reconnect. A best-effort protection-level
query follows setup; failure leaves the otherwise valid session usable and
`protection_level` remains `None`.

## Low-level symbolic access

```python
from pyS7.s7commplus import S7CommPlusClient

client = S7CommPlusClient("192.168.0.1")
client.connect(use_tls=True)  # encrypted, but not certificate-verified
try:
    raw = client.read_symbolic(0x8A0E0064, [0x22], symbol_crc=0)
finally:
    client.disconnect()
```

Reads use GetMultiVariables and writes use SetMultiVariables; neither operation
is converted to a classic DB byte-offset request. Returned data is raw. Existing
pyS7 STRING decoding can consume the observed `max/current/data` representation.
WSTRING has a four-byte big-endian max/current prefix followed by UTF-16BE, so
callers must pass its data portion (or use the existing WSTRING item decoder
where an `S7Tag` supplies the declared length).

The async facade uses `asyncio.to_thread()`. Every blocking operation is off the
event loop and one `asyncio.Lock` serializes the complete session, including its
MemoryBIO and IntegrityId state. Cancellation retains that lock until the worker
has stopped.

## Support matrix

| Mode | Connect | Read symbolic | Write symbolic |
|---|---|---|---|
| V1 plaintext | unsupported | unsupported | unsupported |
| V1 + SessionKey | unsupported | unsupported | unsupported |
| V2 + TLS | implemented | implemented | implemented |
| V3 plaintext | unsupported | unsupported | unsupported |
| V3 + TLS | unverified | unverified | unverified |

Manual validation reported for this phase is limited to Siemens S7-1200 CPU
1212 (6ES7 212-1AE40-0XB0), firmware V4.6: TLS, a V2 session, protection level
1, and a low-level symbolic read using a known LID. This is not a broad hardware
support claim.

Discovery is deliberately limited to raw EXPLORE, DB enumeration, metadata LID 1
RID resolution, and raw type-info-container capture. There is no `browse()`,
type-info parser, symbol tree, tag cache, symbolic-name lookup, or `read_tag()`.
No Siemens assets, protocol dictionaries, or LGPL source are included; current
python-snap7 was consulted only as a behavioral protocol reference.

## Provenance-safe discovery captures

The experimental discovery API deliberately stops before type-info interpretation.
`list_datablocks()` performs a PLC-program EXPLORE, and
`retrieve_type_info_raw()` resolves metadata LID 1 before capturing the complete,
unparsed OMS type-info container. This phase exists so an independent parser can be
developed from metadata captured from our own devices. It contains no Siemens/TIA
preset dictionary, third-party type-info table, decompressor dictionary, or copied
binary metadata.

Use `examples/s7commplus_discovery_dump.py` to inspect DB identity and response size.
A raw file is written only when `--output` is supplied.
