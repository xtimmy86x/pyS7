"""Browse flat scalar S7CommPlus DB members."""

import argparse
import logging
import sys

sys.path.insert(0, "/home/ale/pys7/pyS7")

from pyS7.s7commplus import S7CommPlusClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--db", type=int)
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    client = S7CommPlusClient(args.host)
    try:
        client.connect(use_tls=args.tls)
        for tag in client.browse(db_number=args.db):
            datatype = getattr(tag.data_type, "name", str(tag.data_type))
            lids = ".".join(f"{lid:02X}" for lid in tag.access_sequence)
            print(f"{tag.name:<24} {datatype:<8} {tag.access_area:08X}.{lids}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
