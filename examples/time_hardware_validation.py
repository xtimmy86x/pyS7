"""Maintainer-run TIME hardware validation (never run automatically)."""

import argparse
from datetime import timedelta

from pyS7 import S7Client


def print_case(label: str, ok: bool) -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"{label:<42} {status}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--rack", type=int, required=True)
    parser.add_argument("--slot", type=int, required=True)
    parser.add_argument("--time-address", required=True, help="For example DB1,TIME100")
    parser.add_argument("--dint-address", required=True, help="Adjacent DINT guard")
    args = parser.parse_args()

    client = S7Client(args.host, args.rack, args.slot)
    all_ok = True

    try:
        client.connect()
        all_ok = print_case("connect", True) and all_ok

        original_time, original_dint = client.read(
            [args.time_address, args.dint_address], optimize=False
        )

        cases = [
            (timedelta(0), "TIME = 0 ms"),
            (timedelta(milliseconds=1), "TIME = 1 ms"),
            (timedelta(seconds=1), "TIME = +1 s"),
            (timedelta(seconds=-1), "TIME = -1 s"),
            (timedelta(days=1, seconds=2, milliseconds=3), "TIME positivo complesso"),
            (-timedelta(days=1, seconds=2, milliseconds=3), "TIME negativo complesso"),
        ]

        for value, label in cases:
            client.write([args.time_address], [value])
            read_time = client.read([args.time_address], optimize=False)[0]
            read_dint = client.read([args.dint_address], optimize=False)[0]
            ok = read_time == value and read_dint == original_dint
            all_ok = print_case(label, ok) and all_ok
            if not ok:
                raise AssertionError(
                    f"TIME write/read mismatch for {value!r}: read_time={read_time!r}, "
                    f"guard={read_dint!r}, expected_guard={original_dint!r}"
                )

        adjacent_ok = (
            client.read([args.dint_address], optimize=False)[0] == original_dint
        )
        all_ok = print_case("adjacent DINT unchanged", adjacent_ok) and all_ok
        if not adjacent_ok:
            raise AssertionError("Adjacent DINT changed unexpectedly")

        for optimize in (True, False):
            expected = [cases[-1][0], original_dint]
            read_back = client.read(
                [args.time_address, args.dint_address], optimize=optimize
            )
            ok = read_back == expected
            all_ok = print_case(f"mixed TIME + DINT optimize={optimize}", ok) and all_ok
            if not ok:
                raise AssertionError(
                    f"Mixed TIME + DINT read mismatch with optimize={optimize}: "
                    f"got {read_back!r}, expected {expected!r}"
                )

        client.write([args.time_address], [original_time])
        restored = client.read([args.time_address], optimize=False)[0]
        all_ok = (
            print_case("original TIME restored", restored == original_time) and all_ok
        )
        if restored != original_time:
            raise AssertionError(
                f"TIME restore mismatch: got {restored!r}, expected {original_time!r}"
            )
    except Exception as exc:  # pragma: no cover - hardware validation only
        print(f"ERROR: {exc}")
        all_ok = False
    finally:
        try:
            client.disconnect()
            all_ok = print_case("disconnect", True) and all_ok
        except Exception as exc:  # pragma: no cover - hardware validation only
            print(f"ERROR on disconnect: {exc}")
            all_ok = False

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
