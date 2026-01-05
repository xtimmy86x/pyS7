"""
Debug script to analyze the raw SZL response data for CPU status.
This will help identify the correct bit mapping for CPU status.
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client
from pyS7.constants import SZLId
from pyS7.requests import SZLRequest
from pyS7.responses import SZLResponse

if __name__ == "__main__":
    client = S7Client(address="192.168.100.230", rack=0, slot=1)

    try:
        print("Connecting to PLC...")
        client.connect()
        print("Connected successfully!")

        # Get raw SZL data
        print("\nReading SZL 0x0424 (CPU Diagnostic Status)...")
        szl_request = SZLRequest(szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000)
        response_bytes = client._S7Client__send(szl_request)
        
        print(f"\nRaw response length: {len(response_bytes)} bytes")
        print(f"Raw response (hex): {response_bytes.hex()}")
        
        # Parse the response
        szl_response = SZLResponse(response=response_bytes)
        szl_data = szl_response.parse()
        
        print(f"\nParsed SZL data:")
        print(f"  SZL ID: 0x{szl_data['szl_id']:04X}")
        print(f"  SZL Index: 0x{szl_data['szl_index']:04X}")
        print(f"  Length DR: {szl_data['length_dr']} bytes")
        print(f"  N DR: {szl_data['n_dr']} records")
        print(f"  Data length: {len(szl_data['data'])} bytes")
        print(f"  Data (hex): {szl_data['data'].hex()}")
        
        # Analyze each byte
        print(f"\nByte-by-byte analysis:")
        for i, byte_val in enumerate(szl_data['data']):
            print(f"  Byte {i}: 0x{byte_val:02X} ({byte_val:3d}) = {bin(byte_val)}")
            
        # Show what each bit in byte 2 means
        if len(szl_data['data']) >= 3:
            status_byte = szl_data['data'][2]
            print(f"\nStatus byte (byte 2) analysis: 0x{status_byte:02X}")
            print(f"  Bit 0 (0x01): {'SET' if status_byte & 0x01 else 'NOT SET'}")
            print(f"  Bit 1 (0x02): {'SET' if status_byte & 0x02 else 'NOT SET'}")
            print(f"  Bit 2 (0x04): {'SET' if status_byte & 0x04 else 'NOT SET'}")
            print(f"  Bit 3 (0x08): {'SET' if status_byte & 0x08 else 'NOT SET'}")
            print(f"  Bit 4 (0x10): {'SET' if status_byte & 0x10 else 'NOT SET'}")
            print(f"  Bit 5 (0x20): {'SET' if status_byte & 0x20 else 'NOT SET'}")
            print(f"  Bit 6 (0x40): {'SET' if status_byte & 0x40 else 'NOT SET'}")
            print(f"  Bit 7 (0x80): {'SET' if status_byte & 0x80 else 'NOT SET'}")
        
        # Current interpretation
        print(f"\nCurrent interpretation:")
        status = szl_response.parse_cpu_status()
        print(f"  CPU Status: {status}")
        
        print("\n" + "="*60)
        print("PLEASE REPORT:")
        print("1. What is the ACTUAL CPU status shown on the PLC?")
        print("2. The hex data shown above")
        print("="*60)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        client.disconnect()
        print("\nDisconnected from PLC")
