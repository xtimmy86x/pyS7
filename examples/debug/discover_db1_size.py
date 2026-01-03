"""
Debug script to discover what's actually in DB1.
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client, ConnectionType
from pyS7.tag import S7Tag
from pyS7.constants import DataType, MemoryArea

def main():
    plc_address = "192.168.100.230"
    rack = 0
    slot = 1

    client = S7Client(
        address=plc_address,
        rack=rack,
        slot=slot,
        connection_type=ConnectionType.S7Basic,
        timeout=5.0
    )

    try:
        print(f"Connecting to PLC at {plc_address}...")
        client.connect()
        print("Connected successfully!")

        # Try reading from various offsets in DB1 to find valid data
        test_addresses = [
            ('DB1,I0', 'Start of DB1 - INT'),
            ('DB1,B0', 'Start of DB1 - BYTE'),
            ('DB1,R0', 'Start of DB1 - REAL'),
            ('DB1,I10', 'Offset 10 - INT'),
            ('DB1,I100', 'Offset 100 - INT'),
            ('DB1,I200', 'Offset 200 - INT'),
            ('DB1,I300', 'Offset 300 - INT'),
            ('DB1,S0.10', 'Start - STRING[10]'),
            ('DB1,S10.10', 'Offset 10 - STRING[10]'),
            ('DB1,S52.10', 'Offset 52 (test_string) - STRING[10]'),
            ('DB1,S308.10', 'Offset 308 (test_string2) - STRING[10]'),
        ]

        print("\n" + "="*70)
        print("Testing various DB1 addresses...")
        print("="*70)

        for address, description in test_addresses:
            try:
                result = client.read([address], optimize=False)
                print(f"✓ {description:40s} ({address:15s}): {repr(result[0])}")
            except Exception as e:
                error_msg = str(e)
                if "OUT_OF_RANGE" in error_msg:
                    print(f"✗ {description:40s} ({address:15s}): OUT_OF_RANGE")
                elif "response too short" in error_msg:
                    print(f"✗ {description:40s} ({address:15s}): Response too short")
                else:
                    print(f"✗ {description:40s} ({address:15s}): {error_msg[:50]}")

        # Try to determine DB1 size by reading progressively
        print("\n" + "="*70)
        print("Trying to determine DB1 size...")
        print("="*70)
        
        for offset in [0, 50, 100, 150, 200, 250, 300, 350, 400, 500, 550, 600]:
            try:
                tag = S7Tag(
                    memory_area=MemoryArea.DB,
                    db_number=1,
                    data_type=DataType.INT,
                    start=offset,
                    bit_offset=0,
                    length=1
                )
                result = client.read([tag], optimize=False)
                print(f"  Offset {offset:3d}: ✓ Valid (value={result[0]})")
            except Exception as e:
                if "OUT_OF_RANGE" in str(e):
                    print(f"  Offset {offset:3d}: ✗ OUT_OF_RANGE (DB1 ends before this)")
                    break
                else:
                    print(f"  Offset {offset:3d}: ✗ Error: {str(e)[:40]}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()
        print("\nDisconnected from PLC.")


if __name__ == "__main__":
    main()
