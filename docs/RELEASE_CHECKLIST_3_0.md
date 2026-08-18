# pyS7 3.0 maintainer hardware sign-off

Run this checklist only against an authorized PLC and maintainer-configured,
non-destructive test addresses. Record the CPU model, firmware, connection
mode, negotiated PDU, and which checks were not supported. Do not commit PLC
addresses or network details.

Repeat the applicable checks on S7-300, S7-1200, S7-1500, LOGO! 0BA7, and
LOGO! 0BA8:

- [ ] Connect, disconnect, and reconnect using the deployment connection mode.
- [ ] Read known-safe BIT, BYTE/USINT, INT, REAL, and STRING values.
- [ ] Write and restore known-safe BIT, INT, REAL, and STRING values.
- [ ] Read a BIT with `optimize=True` and confirm the expected value.
- [ ] Where safe, repeat that BIT read with `optimize=False` as a diagnostic.
- [ ] Perform one multi-tag read and verify value ordering.
- [ ] Perform one multi-tag write to safe addresses, verify the PLC response,
      and restore the original values. Do not treat this as PLC-atomic.
- [ ] Read CPU/SZL information where the device supports it.

On Siemens hardware that supports WSTRING, rerun the Step 5 external hardware
regressions with a maintainer-configured safe DB:

- [ ] Chunked WSTRING test reports `ALL HARDWARE TESTS PASSED`.
- [ ] Non-chunked WSTRING plus following USINT test reports
      `ALL HARDWARE TESTS PASSED`.
- [ ] Include ASCII, BMP text, and non-BMP Unicode/emoji in both normal and
      chunked paths, and restore original values after the test.

Any failure should record the CPU/firmware, operation, tag type, connection
configuration, negotiated PDU, exception type/message, and a minimal
reproduction without private addresses.