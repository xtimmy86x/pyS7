"""
Example demonstrating TSAP (Transport Service Access Point) connection method.

TSAP allows direct specification of connection endpoints without using rack/slot.
This is useful for:
- Non-standard PLC configurations
- Third-party S7-compatible devices
- Custom communication setups

TSAP format:
- Local TSAP: Usually 0x0100 (default for PG/PC)
- Remote TSAP: Varies by device
  - S7-300/400: 0x0102 (rack 0, slot 2) = (0x01, rack*32+slot)
  - S7-1200/1500: 0x0100 to 0x01FF depending on slot
  - Common values: 0x0100, 0x0102, 0x0103, etc.

TSAP calculation from rack/slot:
  remote_tsap = 0x0100 | (rack * 32 + slot)
  Example: rack=0, slot=1 -> 0x0100 | (0*32+1) = 0x0101
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client, ConnectionType


def main():
    plc_address = "192.168.100.230"

    print("="*80)
    print("TSAP Connection Methods")
    print("="*80)

    # Method 1: Traditional rack/slot (automatic TSAP calculation)
    print("\n1. Traditional Connection (rack=0, slot=1):")
    print("-" * 40)
    client1 = S7Client(
        address=plc_address,
        rack=0,
        slot=1,
        connection_type=ConnectionType.S7Basic,
        timeout=5.0
    )
    try:
        client1.connect()
        print(f"✓ Connected successfully")
        print(f"  PDU Size: {client1.pdu_size}")
        
        # Test read - use a valid address from the PLC
        try:
            result = client1.read(["DB1,I300"], optimize=False)
            print(f"  Test read DB1,I300: {result[0]}")
        except Exception as e:
            print(f"  Test read skipped (DB1 may not exist)")
        
        client1.disconnect()
        print(f"✓ Disconnected")
    except Exception as e:
        print(f"✗ Failed: {e}")

    # Method 2: Direct TSAP specification
    print("\n2. TSAP Connection (local_tsap=0x0100, remote_tsap=0x0101):")
    print("-" * 40)
    # For rack=0, slot=1: remote_tsap = 0x0100 | (0*32+1) = 0x0101
    client2 = S7Client(
        address=plc_address,
        local_tsap=0x0100,
        remote_tsap=0x0101,
        timeout=5.0
    )
    try:
        client2.connect()
        print(f"✓ Connected successfully")
        print(f"  PDU Size: {client2.pdu_size}")
        
        # Test read - use a valid address from the PLC
        try:
            result = client2.read(["DB1,I300"], optimize=False)
            print(f"  Test read DB1,I300: {result[0]}")
        except Exception as e:
            print(f"  Test read skipped (DB1 may not exist)")
        
        client2.disconnect()
        print(f"✓ Disconnected")
    except Exception as e:
        print(f"✗ Failed: {e}")

    # Method 3: Different remote TSAP (e.g., for slot 2)
    print("\n3. TSAP Connection to different slot (remote_tsap=0x0102):")
    print("-" * 40)
    # For rack=0, slot=2: remote_tsap = 0x0100 | (0*32+2) = 0x0102
    client3 = S7Client(
        address=plc_address,
        local_tsap=0x0100,
        remote_tsap=0x0102,
        timeout=5.0
    )
    try:
        client3.connect()
        print(f"✓ Connected successfully")
        print(f"  PDU Size: {client3.pdu_size}")
        
        client3.disconnect()
        print(f"✓ Disconnected")
    except Exception as e:
        print(f"✗ Failed: {e}")

    # Method 4: Using TSAP calculator helper
    print("\n4. Using TSAP calculator (rack=0, slot=1):")
    print("-" * 40)
    try:
        remote_tsap = S7Client.tsap_from_rack_slot(rack=0, slot=1)
        print(f"Calculated remote TSAP: 0x{remote_tsap:04X}")
        
        client4 = S7Client(
            address=plc_address,
            local_tsap=0x0100,
            remote_tsap=remote_tsap,
            timeout=5.0
        )
        client4.connect()
        print(f"✓ Connected successfully")
        print(f"  PDU Size: {client4.pdu_size}")
        
        client4.disconnect()
        print(f"✓ Disconnected")
    except Exception as e:
        print(f"✗ Failed: {e}")

    # TSAP Reference Table
    print("\n" + "="*80)
    print("TSAP Reference Table")
    print("="*80)
    print(f"{'Rack':<6} {'Slot':<6} {'Remote TSAP':<15} {'Hex Value':<12}")
    print("-" * 80)
    for rack in range(0, 3):
        for slot in range(0, 5):
            tsap = 0x0100 | (rack * 32 + slot)
            print(f"{rack:<6} {slot:<6} {tsap:<15} 0x{tsap:04X}")


if __name__ == "__main__":
    main()
