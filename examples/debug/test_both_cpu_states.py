"""
Interactive test to determine correct CPU status bit mapping.
Run this script with CPU in RUN mode, then again with CPU in STOP mode.
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client
from pyS7.constants import SZLId
from pyS7.requests import SZLRequest
from pyS7.responses import SZLResponse

if __name__ == "__main__":
    print("="*70)
    print("CPU STATUS BIT MAPPING TEST")
    print("="*70)
    print("\nBEFORE RUNNING THIS SCRIPT:")
    print("Please check your PLC and note the ACTUAL CPU status (RUN or STOP)")
    print("="*70)
    
    actual_status = input("\nWhat is the ACTUAL CPU status on the PLC? (RUN/STOP): ").strip().upper()
    
    if actual_status not in ["RUN", "STOP"]:
        print("Invalid input. Please enter RUN or STOP")
        sys.exit(1)
    
    client = S7Client(address="192.168.100.230", rack=0, slot=1)

    try:
        print("\nConnecting to PLC...")
        client.connect()
        print("✓ Connected successfully!")

        # Get raw SZL data
        print("\nReading SZL 0x0424 (CPU Diagnostic Status)...")
        szl_request = SZLRequest(szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000)
        response_bytes = client._S7Client__send(szl_request)
        
        # Parse the response
        szl_response = SZLResponse(response=response_bytes)
        szl_data = szl_response.parse()
        
        print(f"\n{'='*70}")
        print(f"ACTUAL CPU STATUS: {actual_status}")
        print(f"{'='*70}")
        print(f"\nFull data (hex): {szl_data['data'].hex()}")
        
        # Analyze relevant bytes
        print(f"\nKey bytes analysis:")
        for i in range(min(5, len(szl_data['data']))):
            byte_val = szl_data['data'][i]
            print(f"  Byte {i}: 0x{byte_val:02X} ({byte_val:3d}) = {bin(byte_val):>10s}")
            if i == 1:
                print(f"          Bit 3 (0x08): {'SET' if byte_val & 0x08 else 'NOT SET'} <- Currently used for detection")
        
        # Show current library interpretation
        detected_status = szl_response.parse_cpu_status()
        print(f"\n{'='*70}")
        print(f"Library Detection: {detected_status}")
        print(f"Actual Status:     {actual_status}")
        print(f"Match: {'✓ CORRECT' if detected_status == actual_status else '✗ INCORRECT'}")
        print(f"{'='*70}")
        
        if detected_status != actual_status:
            print("\n⚠ MISMATCH DETECTED!")
            print("The bit logic needs to be inverted.")
            print(f"When actual status is {actual_status}, byte 1 bit 3 is {'SET' if szl_data['data'][1] & 0x08 else 'NOT SET'}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        client.disconnect()
        print("\n✓ Disconnected from PLC")
