#!/usr/bin/env python3

import socket
from unittest.mock import Mock, patch
from pyS7.pyS7 import S7Client

def debug_optimized_read():
    print("=== Debugging Optimized Read Path ===")
    
    # Create a mock response that represents DB1.DBB0 = 128 (0b10000000)
    # The response format: header + status + length + data
    mock_response = (
        b"\x03\x00\x00\x21"  # ISO header
        b"\x02\xf0\x80"       # Protocol header
        b"\x32\x03\x00\x00\x00\x00\x00\x02\x00\x0c\x00\x00"  # S7 header
        b"\x04\x01"           # Return code + transport size
        b"\xff"               # Status (success)
        b"\x03\x00\x01"       # Length (1 byte)
        b"\x80"               # Data: 128 (0b10000000)
        b"\x00"               # Padding
    )
    
    client = S7Client("192.168.1.1", 0, 1)
    
    # Mock the socket operations
    with patch('socket.socket.sendall'), \
         patch('socket.socket.recv', return_value=mock_response):
        
        client.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Try to read DB1,X0.7 with optimization
        try:
            result = client.read(["DB1,X0.7"], optimize=True)
            print(f"Optimized read result: {result}")
            print(f"Expected: [True]")
            print(f"Correct: {'✓' if result == [True] else '✗'}")
        except Exception as e:
            print(f"Error in optimized read: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_optimized_read()