"""
Example: Working around INVALID_DATA_SIZE errors when reading individual bits

Some S7 PLCs may not support reading individual bits directly and will return
INVALID_DATA_SIZE errors. This example shows how to work around this limitation
by reading the entire byte and extracting the specific bit.
"""

from pyS7 import S7Client, extract_bit_from_byte

def read_bit_with_workaround(client, db_number, byte_address, bit_offset):
    """
    Read a specific bit by reading the entire byte and extracting the bit.
    
    Args:
        client: S7Client instance
        db_number: Database number
        byte_address: Byte address in the database
        bit_offset: Bit position (0-7)
        
    Returns:
        bool: Value of the specific bit
    """
    try:
        # First, try the direct bit read
        bit_tag = f"DB{db_number},X{byte_address}.{bit_offset}"
        result = client.read([bit_tag])
        return result[0]
        
    except Exception as e:
        if "INVALID_DATA_SIZE" in str(e):
            print(f"Direct bit read failed: {e}")
            print("Using byte read workaround...")
            
            # Read the entire byte instead
            byte_tag = f"DB{db_number},B{byte_address}"
            byte_result = client.read([byte_tag])
            byte_value = byte_result[0]
            
            # Extract the specific bit
            bit_value = extract_bit_from_byte(byte_value, bit_offset)
            print(f"Read byte value {byte_value}, extracted bit {bit_offset}: {bit_value}")
            return bit_value
        else:
            # Re-raise other exceptions
            raise

if __name__ == "__main__":
    # Example usage (commented out since we don't have a real PLC connection)
    # client = S7Client(address="192.168.1.100", rack=0, slot=1)
    # client.connect()
    
    # # Try to read DB1.DBX0.2 (the bit that was causing the error)
    # bit_value = read_bit_with_workaround(client, 1, 0, 2)
    # print(f"Final result: {bit_value}")
    
    # client.disconnect()
    
    # Demonstrate the bit extraction function with some examples
    print("Examples of bit extraction from bytes:")
    print("=====================================")
    
    test_cases = [
        (0b00000001, 0, "Bit 0 set"),           # Bit 0 = True
        (0b00000100, 2, "Bit 2 set"),           # Bit 2 = True (your error case)
        (0b10000000, 7, "Bit 7 set"),           # Bit 7 = True
        (0b11111111, 4, "All bits set"),        # All bits = True
        (0b00000000, 3, "No bits set"),         # All bits = False
    ]
    
    for byte_val, bit_pos, description in test_cases:
        result = extract_bit_from_byte(byte_val, bit_pos)
        print(f"{description}: byte={byte_val:08b} ({byte_val:3d}), bit[{bit_pos}]={result}")