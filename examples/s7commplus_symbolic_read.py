"""Manually read a known S7CommPlus symbolic path from a PLC."""

import argparse
import logging

from pyS7.s7commplus import S7CommPlusClient


def integer(value: str) -> int:
    return int(value, 0)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--host", required=True)
parser.add_argument("--port", type=int, default=102)
parser.add_argument("--timeout", type=float, default=5.0)
parser.add_argument("--access-area", type=integer, required=True)
parser.add_argument("--lid", type=integer, action="append", required=True)
parser.add_argument("--symbol-crc", type=integer, default=0)
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
client = S7CommPlusClient(args.host, args.port, args.timeout)
try:
    client.connect()
    if args.debug:
        print(
            "session: "
            f"protocol=V{client.protocol_version} established={client.connected} "
            f"session_id=0x{client.session_id:08x} tls={client.tls_active} "
            f"authentication_supported={client.authentication_supported}"
        )
        print(f"address: AccessArea=0x{args.access_area:08x} LIDs={args.lid!r}")
    value = client.read_symbolic(args.access_area, args.lid, args.symbol_crc)
    if args.debug:
        print(f"raw response: {client.last_response.hex(' ')}")
    print(f"{len(value)} byte(s): {value.hex(' ')}")
except Exception:
    if args.debug and client.last_response:
        print(f"last raw response: {client.last_response.hex(' ')}")
    raise
finally:
    client.disconnect()
