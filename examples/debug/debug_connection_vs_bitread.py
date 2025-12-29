"""
Debug script to test bit ordering and identify the correct bit mapping
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client

def test_bit_ordering():
    """Test bit ordering to understand how PLC maps bits vs. library interpretation"""
    
    client = S7Client(address="192.168.100.230", rack=0, slot=1)  
    
    print("Testing bit ordering issue...")
    try:
        client.connect()
        print("✓ Connection successful")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return
    
    # Read the byte value first
    try:
        byte_result = client.read(["DB1,B0"])
        byte_value = byte_result[0]
        print(f"Byte DB1.DBB0 = {byte_value} (binary: {bin(byte_value)})")
    except Exception as e:
        print(f"✗ Byte read failed: {e}")
        client.disconnect()
        return
    
    print("\nTesting all 8 bits to understand the mapping:")
    print("Library bit -> PLC bit mapping:")
    print("-" * 40)
    
    # Test all 8 bits
    for bit_pos in range(8):
        try:
            bit_result = client.read([f"DB1,X0.{bit_pos}"])
            bit_value = bit_result[0]
            
            # Calculate what this bit should be based on LSB and MSB interpretations
            lsb_expected = bool((byte_value >> bit_pos) & 1)  # LSB first (bit 0 = rightmost)
            msb_expected = bool((byte_value >> (7 - bit_pos)) & 1)  # MSB first (bit 0 = leftmost)
            
            print(f"Bit 0.{bit_pos}: {bit_value} | LSB expects: {lsb_expected} | MSB expects: {msb_expected}")
            
            if bit_value == lsb_expected:
                ordering = "LSB"
            elif bit_value == msb_expected:
                ordering = "MSB"
            else:
                ordering = "UNKNOWN"
                
            if bit_pos == 0:  # Only print for first bit to avoid spam
                if ordering != "UNKNOWN":
                    print(f"→ PLC appears to use {ordering} bit ordering")
                    
        except Exception as e:
            print(f"Bit 0.{bit_pos}: ERROR - {e}")
    
    client.disconnect()
    print("\nTest completed.")
if __name__ == "__main__":
    test_bit_ordering()