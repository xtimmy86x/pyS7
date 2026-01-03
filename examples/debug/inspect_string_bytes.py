"""
Debug script to analyze the raw bytes of STRING storage in DB1.
This will help understand the actual memory layout.
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client, ConnectionType

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

        # Read raw bytes around the STRING locations
        print("\n" + "="*80)
        print("Reading raw BYTE data from DB1 to inspect STRING structure")
        print("="*80)

        # test_string at offset 52
        print("\ntest_string (offset 52):")
        print("-" * 40)
        try:
            # Read as BYTE array to see raw data
            result = client.read(["DB1,B52"], optimize=False)
            byte_val = result[0]
            print(f"  Byte at offset 52: 0x{byte_val:02x} ({byte_val}) - Should be max_length")
            
            result = client.read(["DB1,B53"], optimize=False)
            byte_val = result[0]
            print(f"  Byte at offset 53: 0x{byte_val:02x} ({byte_val}) - Should be current_length")
            
            # Read next 20 bytes as string content
            print(f"  First 20 bytes starting at offset 54:")
            for i in range(54, 74):
                result = client.read([f"DB1,B{i}"], optimize=False)
                byte_val = result[0]
                char = chr(byte_val) if 32 <= byte_val < 127 else '.'
                print(f"    Byte {i:3d}: 0x{byte_val:02x} ({byte_val:3d}) '{char}'")
        except Exception as e:
            print(f"  Error: {e}")

        # test_string2 at offset 308
        print("\ntest_string2 (offset 308) - should contain 'test':")
        print("-" * 40)
        try:
            result = client.read(["DB1,B308"], optimize=False)
            byte_val = result[0]
            print(f"  Byte at offset 308: 0x{byte_val:02x} ({byte_val}) - Should be max_length")
            
            result = client.read(["DB1,B309"], optimize=False)
            byte_val = result[0]
            print(f"  Byte at offset 309: 0x{byte_val:02x} ({byte_val}) - Should be current_length")
            
            # Read next 20 bytes as string content
            print(f"  First 20 bytes starting at offset 310:")
            for i in range(310, 330):
                result = client.read([f"DB1,B{i}"], optimize=False)
                byte_val = result[0]
                char = chr(byte_val) if 32 <= byte_val < 127 else '.'
                print(f"    Byte {i:3d}: 0x{byte_val:02x} ({byte_val:3d}) '{char}'")
        except Exception as e:
            print(f"  Error: {e}")

        # Now try reading as STRING to see what happens
        print("\n" + "="*80)
        print("Attempting to read as STRING with length=10")
        print("="*80)
        
        for offset, name in [(52, "test_string"), (308, "test_string2")]:
            print(f"\n{name} at offset {offset}:")
            try:
                result = client.read([f"DB1,S{offset}.10"], optimize=False)
                print(f"  ✓ Success: {repr(result[0])}")
            except Exception as e:
                print(f"  ✗ Failed: {e}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()
        print("\nDisconnected from PLC.")


if __name__ == "__main__":
    main()
