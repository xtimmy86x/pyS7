"""
Debug the exact response parsing for bit reads
"""

import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client
from pyS7.constants import DataType, MemoryArea
from pyS7.tag import S7Tag

def debug_bit_response():
    client = S7Client(address="192.168.100.230", rack=0, slot=1)
    client.connect()
    
    # Read byte first
    byte_result = client.read(["DB1,B0"])
    byte_value = byte_result[0]
    print(f"Byte DB1.DBB0: {byte_value} (binary: {bin(byte_value)})")
    
    # Read bit 7 (which should be True based on the byte)
    print("\n=== Testing bit 0.7 (should be True) ===")
    
    # Let's manually create the tag to see what happens
    bit_tag = S7Tag(
        memory_area=MemoryArea.DB,
        db_number=1,
        data_type=DataType.BIT,
        start=0,
        bit_offset=7,
        length=1
    )
    
    print(f"Tag: {bit_tag}")
    print(f"Tag size: {bit_tag.size()}")
    
    # Try reading with the library (non-optimized)
    print("=== Testing NON-optimized read ===")
    bit_result = client.read(["DB1,X0.7"], optimize=False)
    print(f"Non-optimized result: {bit_result}")
    
    # Try reading with the library (optimized - default)
    print("=== Testing optimized read ===")
    bit_result = client.read(["DB1,X0.7"])
    print(f"Optimized result: {bit_result}")
    
    # Manual calculation
    expected = bool((byte_value >> 7) & 1)
    print(f"Expected result: {expected}")
    
    client.disconnect()

if __name__ == "__main__":
    debug_bit_response()