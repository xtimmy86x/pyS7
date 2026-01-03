"""
Debug script to analyze STRING read issues.
Specifically for the error: response too short while reading return code
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
        print(f"PDU Size: {client.pdu_size}")

        # Create the problematic STRING tag
        string_tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=1,
            data_type=DataType.STRING,
            start=308,
            bit_offset=0,
            length=150
        )

        print(f"\nTag: {string_tag}")
        print(f"Tag size: {string_tag.size()} bytes")
        print(f"Expected response size: {21 + 5 + string_tag.size()} bytes minimum")

        # Try non-optimized read first
        print("\n" + "="*70)
        print("Attempting NON-OPTIMIZED read...")
        print("="*70)
        try:
            result = client.read([string_tag], optimize=False)
            print(f"✓ Success!")
            print(f"Result: {repr(result[0])}")
            print(f"Length: {len(result[0]) if isinstance(result[0], str) else 'N/A'}")
        except Exception as e:
            print(f"✗ Failed: {e}")
            import traceback
            traceback.print_exc()

        # Try optimized read
        print("\n" + "="*70)
        print("Attempting OPTIMIZED read...")
        print("="*70)
        try:
            result = client.read([string_tag], optimize=True)
            print(f"✓ Success!")
            print(f"Result: {repr(result[0])}")
            print(f"Length: {len(result[0]) if isinstance(result[0], str) else 'N/A'}")
        except Exception as e:
            print(f"✗ Failed: {e}")
            import traceback
            traceback.print_exc()

        # Try reading with smaller length
        print("\n" + "="*70)
        print("Attempting read with smaller STRING length (50)...")
        print("="*70)
        smaller_tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=1,
            data_type=DataType.STRING,
            start=308,
            bit_offset=0,
            length=50
        )
        try:
            result = client.read([smaller_tag], optimize=True)
            print(f"✓ Success!")
            print(f"Result: {repr(result[0])}")
            print(f"Length: {len(result[0]) if isinstance(result[0], str) else 'N/A'}")
        except Exception as e:
            print(f"✗ Failed: {e}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()
        print("\nDisconnected from PLC.")


if __name__ == "__main__":
    main()
