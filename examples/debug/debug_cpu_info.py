"""
Debug script to explore SZL 0x0011 structure and available data.
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
        print("✓ Connected successfully!\n")

        # Try SZL 0x0011 (Module Identification)
        print("="*70)
        print("Reading SZL 0x0011 (Module Identification)...")
        print("="*70)
        
        szl_request = SZLRequest(szl_id=SZLId.MODULE_IDENTIFICATION, szl_index=0x0000)
        response_bytes = client._S7Client__send(szl_request)
        
        szl_response = SZLResponse(response=response_bytes)
        szl_data = szl_response.parse()
        
        print(f"\nSZL ID: 0x{szl_data['szl_id']:04X}")
        print(f"SZL Index: 0x{szl_data['szl_index']:04X}")
        print(f"Length DR: {szl_data['length_dr']} bytes")
        print(f"N DR: {szl_data['n_dr']} records")
        print(f"Data length: {len(szl_data['data'])} bytes")
        print(f"\nRaw data (hex): {szl_data['data'].hex()}")
        
        # Byte-by-byte analysis
        print(f"\nByte-by-byte analysis:")
        for i in range(min(60, len(szl_data['data']))):
            byte_val = szl_data['data'][i]
            ascii_char = chr(byte_val) if 32 <= byte_val <= 126 else '.'
            print(f"  Byte {i:2d}: 0x{byte_val:02X} ({byte_val:3d}) '{ascii_char}'", end='')
            if (i + 1) % 4 == 0:
                # Show 4-byte chunk as string
                chunk = szl_data['data'][max(0, i-3):i+1]
                text = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
                print(f"  |{text}|")
            else:
                print()
        
        # Parse with our method
        print(f"\n{'='*70}")
        print("Parsed CPU Info:")
        print("="*70)
        info = szl_response.parse_cpu_info()
        for key, value in info.items():
            print(f"{key:20s}: {value}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        client.disconnect()
        print("\n✓ Disconnected from PLC")
