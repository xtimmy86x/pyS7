"""
Debug the actual S7 request being sent for optimized reads
"""

import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client
import socket
from unittest.mock import patch

def debug_request():
    client = S7Client(address="192.168.100.230", rack=0, slot=1)
    client.connect()
    
    # Capture the actual request being sent
    original_sendall = socket.socket.sendall
    captured_request = []
    
    def capture_sendall(self, data):
        captured_request.append(data)
        print(f"Captured request data: {data.hex()}")
        return original_sendall(self, data)
    
    with patch.object(socket.socket, 'sendall', capture_sendall):
        print("=== Non-optimized request ===")
        result1 = client.read(["DB1,X0.7"], optimize=False)
        print(f"Non-optimized result: {result1}")
        
        print("\n=== Optimized request ===")
        result2 = client.read(["DB1,X0.7"], optimize=True)
        print(f"Optimized result: {result2}")
    
    client.disconnect()
    
    print("\n=== Request Analysis ===")
    if len(captured_request) >= 2:
        print(f"Non-optimized request: {captured_request[0].hex()}")
        print(f"Optimized request:     {captured_request[1].hex()}")
        
        # Compare the relevant parts
        if len(captured_request[0]) > 30 and len(captured_request[1]) > 30:
            print(f"Non-opt address part:  {captured_request[0][-20:].hex()}")
            print(f"Opt address part:      {captured_request[1][-20:].hex()}")

if __name__ == "__main__":
    debug_request()