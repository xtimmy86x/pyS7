"""Browse flat scalar S7CommPlus DB members and test symbolic read."""

import argparse
import logging
import struct
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

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO
    )

    client = S7CommPlusClient(args.host)

    try:
        client.connect(use_tls=args.tls)

        tags = client.browse(db_number=args.db)

        print("\nDiscovered tags:\n")

        for tag in tags:
            datatype = getattr(tag.data_type, "name", str(tag.data_type))
            lids = ".".join(f"{lid:02X}" for lid in tag.access_sequence)

            print(
                f"{tag.name:<24} "
                f"{datatype:<8} "
                f"{tag.access_area:08X}.{lids}"
            )

        print("\nSymbolic read test:\n")

        real = next(
            tag
            for tag in tags
            if tag.name == "DB_Test.Real"
        )

        print(f"name:            {real.name}")
        print(f"data_type:       {getattr(real.data_type, 'name', real.data_type)}")
        print(f"access_area:     0x{real.access_area:08X}")
        print(
            "access_sequence:",
            [f"0x{lid:X}" for lid in real.access_sequence],
        )

        raw = client.read_symbolic(
            real.access_area,
            real.access_sequence,
            0,
        )

        print(f"raw:             {raw.hex(' ')}")

        value = struct.unpack(">f", raw)[0]

        print(f"value:           {value}")

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
