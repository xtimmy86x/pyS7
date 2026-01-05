"""Test SZL ID 0x001C (Component Identification) to get firmware version."""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client
from pyS7.requests import SZLRequest
from pyS7.responses import SZLResponse
from pyS7.constants import SZLId

PLC_ADDRESS = "192.168.100.230"
RACK = 0
SLOT = 1

client = S7Client(address=PLC_ADDRESS, rack=RACK, slot=SLOT)

try:
    print("Connecting to PLC...")
    client.connect()
    print("✓ Connected successfully!\n")
    
    print("="*70)
    print("Reading SZL 0x001C (Component Identification)...")
    print("="*70)
    
    # Build raw SZL request manually since 0x001C is not in enum
    packet = bytearray()
    
    # TPKT header
    packet.extend(b"\x03\x00\x00\x21")  # Length will be 33 (0x21)
    
    # COTP header
    packet.extend(b"\x02\xf0\x80")
    
    # S7 Header
    packet.extend(b"\x32\x07")  # Protocol ID + USERDATA message type
    packet.extend(b"\x00\x00\x00\x00")  # Reserved + PDU ref
    packet.extend(b"\x00\x08")  # Parameter length (8 bytes)
    packet.extend(b"\x00\x04")  # Data length (4 bytes)
    
    # Parameter section (8 bytes)
    packet.extend(b"\x00\x01\x12")  # Parameter head
    packet.extend(b"\x04")  # Parameter length
    packet.extend(b"\x11")  # Method: Request
    packet.extend(b"\x44")  # Function: CPU functions
    packet.extend(b"\x01")  # Subfunction: Read SZL
    packet.extend(b"\x01")  # Sequence number
    
    # Data section (4 bytes)
    packet.extend(b"\xff")  # Return code
    packet.extend(b"\x09")  # Transport size
    packet.extend(b"\x00\x04")  # Data unit length
    packet.extend(b"\x00\x1C")  # SZL ID 0x001C
    packet.extend(b"\x00\x01")  # SZL Index 0x0001
    
    # Update TPKT length
    packet[2:4] = len(packet).to_bytes(2, byteorder="big")
    
    print(f"Sending {len(packet)} bytes...")
    print(f"Request packet (hex): {packet.hex()}\n")
    
    client.socket.send(packet)
    response_bytes = client.socket.recv(1024)
    
    print(f"\nReceived {len(response_bytes)} bytes")
    print(f"Raw response (hex): {response_bytes.hex()}\n")
    
    # Try to parse
    response = SZLResponse(response_bytes)
    try:
        data = response.parse()
        print(f"SZL ID: 0x{data['szl_id']:04X}")
        print(f"SZL Index: 0x{data['szl_index']:04X}")
        print(f"Length DR: {data['length_dr']} bytes")
        print(f"N DR: {data['n_dr']} records")
        print(f"Data length: {len(data['data'])} bytes")
        print(f"\nRaw data (hex): {data['data'].hex()}")
        
        # Try to decode as ASCII
        try:
            ascii_str = data['data'].decode('ascii', errors='ignore')
            print(f"ASCII interpretation: {ascii_str}")
        except:
            pass
            
    except Exception as e:
        print(f"Parse error: {e}")
        print("\nByte-by-byte analysis:")
        for i, byte in enumerate(response_bytes):
            print(f"  Byte {i:3d}: 0x{byte:02X} ({byte:3d}) '{chr(byte) if 32 <= byte < 127 else '.'}'")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    client.disconnect()
    print("\n✓ Disconnected from PLC")
