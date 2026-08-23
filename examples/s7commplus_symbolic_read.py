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
with S7CommPlusClient(args.host, args.port, args.timeout) as client:
    value = client.read_symbolic(args.access_area, args.lid, args.symbol_crc)
print(f"{len(value)} byte(s): {value.hex(' ')}")
