#!/usr/bin/env python3
"""Capture raw, provenance-safe S7CommPlus discovery metadata from a PLC."""

import argparse
import logging
from pathlib import Path
import sys

sys.path.insert(0, "/home/ale/pys7/pyS7")

from pyS7.s7commplus import S7CommPlusClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=102)
    parser.add_argument("--db", type=int, required=True)
    parser.add_argument(
        "--tls", action="store_true", help="required for the verified V2 path"
    )
    parser.add_argument("--tls-verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    client = S7CommPlusClient(args.host, args.port)
    try:
        client.connect(use_tls=args.tls, tls_verify=args.tls_verify)
        print(
            f"connected: TLS={client.tls_active} V{client.protocol_version} "
            f"protection_level={client.protection_level}"
        )
        matches = [db for db in client.list_datablocks() if db.number == args.db]
        if not matches:
            raise SystemExit(f"DB{args.db} was not present in PLC discovery metadata")
        db = matches[0]
        print(f"DB{db.number} name: {db.name}")
        print(
            f"relation ID / AccessArea: 0x{db.relation_id:08X} / 0x{db.access_area:08X}"
        )
        type_rid, raw = client.retrieve_type_info_raw(db.access_area)
        print(f"type-info RID: 0x{type_rid:08X}")
        print(f"EXPLORE response length: {len(raw)} bytes")
        if args.output:
            args.output.write_bytes(raw)
            print(f"raw response written to: {args.output}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
