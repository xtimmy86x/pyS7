"""
Debug the exact optimized read path with real PLC data
"""

import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client
from pyS7.constants import DataType, MemoryArea
from pyS7.tag import S7Tag
import socket
from unittest.mock import patch

def debug_optimized_path():
    client = S7Client(address="192.168.100.230", rack=0, slot=1)
    client.connect()
    
    # First, read the byte to see what the actual value is
    byte_result = client.read(["DB1,B0"])
    byte_value = byte_result[0]
    print(f"Actual DB1.DBB0 value: {byte_value} (binary: {bin(byte_value)})")
    
    # Test what extract_bit_from_byte returns for this actual byte
    from pyS7.responses import extract_bit_from_byte
    expected_bit_7 = extract_bit_from_byte(byte_value, 7)
    print(f"extract_bit_from_byte({byte_value}, 7) = {expected_bit_7}")
    
    # Now let's capture the actual raw response from the optimized read
    original_recv = socket.socket.recv
    captured_response = []
    
    def capture_recv(self, bufsize):
        data = original_recv(self, bufsize)
        captured_response.append(data)
        print(f"Captured response data: {data.hex() if data else 'None'}")
        return data
    
    with patch.object(socket.socket, 'recv', capture_recv):
        # Try the optimized read
        print("\n=== Optimized read with capture ===")
        optimized_result = client.read(["DB1,X0.7"], optimize=True)
        print(f"Optimized result: {optimized_result}")
    
    # Now let's try non-optimized for comparison
    print("\n=== Non-optimized read ===")
    non_opt_result = client.read(["DB1,X0.7"], optimize=False)
    print(f"Non-optimized result: {non_opt_result}")
    
    print(f"\nExpected: {expected_bit_7}")
    print(f"Optimized matches expected: {optimized_result[0] == expected_bit_7}")
    print(f"Non-optimized matches expected: {non_opt_result[0] == expected_bit_7}")
    
    client.disconnect()

if __name__ == "__main__":
    debug_optimized_path()