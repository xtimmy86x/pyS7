"""
Test reading the actual STRING values from DB1 based on the PLC configuration.
According to the screenshot:
- test_string at offset 52.0 (String type)
- test_string2 at offset 308.0 (String type) with value 'test'
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
        print(f"PDU Size: {client.pdu_size}")
        print(f"Max string size that fits: {client.pdu_size - 21 - 5 - 2} characters")

        # S7 STRING default maximum length is 254 characters
        # But we need to stay within PDU limits
        # PDU 240 - 21 (overhead) - 5 (param) - 2 (string header) = 212 max chars
        
        test_cases = [
            ("DB1,S52.254", "test_string (full 254 length)", 254),
            ("DB1,S308.254", "test_string2 (full 254 length)", 254),
            ("DB1,S52.100", "test_string (100 length)", 100),
            ("DB1,S308.100", "test_string2 (100 length)", 100),
            ("DB1,S52.50", "test_string (50 length)", 50),
            ("DB1,S308.50", "test_string2 (50 length)", 50),
            ("DB1,S52.10", "test_string (10 length)", 10),
            ("DB1,S308.10", "test_string2 (10 length)", 10),
        ]

        print("\n" + "="*80)
        print("Testing STRING reads with various lengths...")
        print("="*80)

        for address, description, expected_len in test_cases:
            str_size = expected_len + 2  # +2 for STRING header
            total_size = 21 + 5 + str_size
            fits = "✓" if total_size <= client.pdu_size else "✗"
            
            print(f"\n{fits} {description:35s} ({address:15s})")
            print(f"   String size: {str_size} bytes, Total: {total_size} bytes")
            
            try:
                result = client.read([address], optimize=False)
                print(f"   Result: {repr(result[0])}")
                print(f"   Actual length: {len(result[0])} chars")
            except Exception as e:
                error_msg = str(e)
                if "response too short" in error_msg:
                    print(f"   ERROR: Request too large for PDU!")
                elif "OUT_OF_RANGE" in error_msg:
                    print(f"   ERROR: Address out of range")
                elif "decode" in error_msg:
                    print(f"   ERROR: Invalid string data (non-ASCII bytes)")
                else:
                    print(f"   ERROR: {error_msg[:60]}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()
        print("\nDisconnected from PLC.")


if __name__ == "__main__":
    main()
