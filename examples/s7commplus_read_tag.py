"""Read one flat scalar through its S7CommPlus symbolic name."""

import argparse
import logging
import sys

sys.path.insert(0, "/home/ale/pys7/pyS7")

from pyS7.s7commplus import S7CommPlusClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    client = S7CommPlusClient(args.host)
    client.connect(use_tls=args.tls)
    try:
        print(f"{args.tag} = {client.read_tag(args.tag)}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
