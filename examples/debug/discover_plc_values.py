"""
PLC Value Discovery Script
This script reads current values from the PLC to understand what's actually stored,
then creates accurate test expectations based on real data.
"""

import sys
import os
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client

def discover_plc_values():
    """Read actual values from PLC and create test data"""
    
    # PLC connection details
    PLC_IP = "192.168.100.230"
    RACK = 0
    SLOT = 1
    
    print("=== PLC Value Discovery ===")
    print(f"Connecting to PLC at {PLC_IP}...")
    
    try:
        client = S7Client(address=PLC_IP, rack=RACK, slot=SLOT)
        client.connect()
        print("✓ Connected successfully")
        
        print("\n=== Current PLC Values ===")
        
        # Read Boolean values
        print("\nBoolean Values (DB1.DBB0):")
        bool_addresses = [f"DB1,X0.{i}" for i in range(8)]
        bool_results = client.read(bool_addresses, optimize=True)
        
        for i, (addr, value) in enumerate(zip(bool_addresses, bool_results)):
            print(f"  test_bool_{i+1} ({addr}): {value}")
        
        # Read the raw byte to verify bit interpretation
        byte_result = client.read(["DB1,B0"])
        print(f"  Raw byte DB1,B0: {byte_result[0]} (0x{byte_result[0]:02x}, 0b{byte_result[0]:08b})")
        
        # Read Numeric values
        print("\nNumeric Values:")
        numeric_addresses = [
            ("DB1,I2", "test_int", "INT"),
            ("DB1,I4", "test_int2", "INT"), 
            ("DB1,B6", "test_byte", "BYTE"),
            ("DB1,B7", "test_byte2", "BYTE"),
            ("DB1,W8", "test_word", "WORD"),
            ("DB1,W10", "test_word2", "WORD"),
            ("DB1,R12", "test_real", "REAL"),
            ("DB1,R16", "test_real2", "REAL"),
            ("DB1,DI20", "test_dint", "DINT"),
            ("DB1,DI24", "test_din2", "DINT"),
            ("DB1,DW28", "test_dword", "DWORD"),
            ("DB1,DW32", "test_dword2", "DWORD"),
            ("DB1,LR36", "test_lreal", "LREAL"),
            ("DB1,LR44", "test_lreal2", "LREAL"),
        ]
        
        for addr, name, data_type in numeric_addresses:
            try:
                result = client.read([addr])
                print(f"  {name} ({addr}, {data_type}): {result[0]}")
            except Exception as e:
                print(f"  {name} ({addr}, {data_type}): ERROR - {e}")
        
        # Read String values with error handling
        print("\nString Values:")
        string_addresses = [
            ("DB1,S52.10", "test_string", "STRING"),
            ("DB1,S308.10", "test_string2", "STRING"),
        ]
        
        for addr, name, data_type in string_addresses:
            try:
                result = client.read([addr])
                print(f"  {name} ({addr}, {data_type}): '{result[0]}'")
            except Exception as e:
                print(f"  {name} ({addr}, {data_type}): ERROR - {e}")
                # Try reading as raw bytes to see what's there
                try:
                    # Extract byte address from string address
                    if ",S" in addr:
                        byte_addr = addr.split(",S")[0] + ",B" + addr.split(",S")[1].split(".")[0]
                        raw_result = client.read([byte_addr])
                        print(f"    Raw bytes at {byte_addr}: {raw_result}")
                except:
                    pass
        
        # Read Character values
        print("\nCharacter Values:")
        char_addresses = [
            ("DB1,C564", "test_char", "CHAR"),
            ("DB1,C565", "test_char2", "CHAR"),
        ]
        
        for addr, name, data_type in char_addresses:
            try:
                result = client.read([addr])
                char_val = result[0]
                char_code = ord(char_val) if len(char_val) > 0 else 0
                print(f"  {name} ({addr}, {data_type}): '{char_val}' (ASCII: {char_code})")
            except Exception as e:
                print(f"  {name} ({addr}, {data_type}): ERROR - {e}")
        
        print("\n=== Raw Memory Inspection ===")
        # Let's read some raw bytes to understand the memory layout
        raw_addresses = ["DB1,B0", "DB1,B1", "DB1,B2", "DB1,B3", "DB1,B4", "DB1,B5"]
        try:
            raw_results = client.read(raw_addresses)
            print("First 6 bytes of DB1:")
            for i, (addr, value) in enumerate(zip(raw_addresses, raw_results)):
                print(f"  {addr}: {value} (0x{value:02x}, 0b{value:08b})")
        except Exception as e:
            print(f"Raw memory read failed: {e}")
        
        # Generate Python test code based on actual values
        print("\n=== Generated Test Code ===")
        print("# Expected values based on current PLC state:")
        print("expected_values = {")
        
        # Boolean values
        for i, value in enumerate(bool_results):
            print(f"    'test_bool_{i+1}': {value},    # DB1,X0.{i}")
        
        # Add other values that we successfully read
        print("    # Add other values here after inspection")
        print("}")
        
        client.disconnect()
        print("\n✓ Disconnected from PLC")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def test_bit_consistency():
    """Specific test to verify bit reading consistency after our fix"""
    PLC_IP = "192.168.100.230"
    RACK = 0 
    SLOT = 1
    
    print("\n=== Bit Reading Consistency Test ===")
    
    try:
        client = S7Client(address=PLC_IP, rack=RACK, slot=SLOT)
        client.connect()
        
        # Read the byte first to know what bits should be
        byte_result = client.read(["DB1,B0"])[0]
        print(f"DB1.DBB0 = {byte_result} (0x{byte_result:02x}, 0b{byte_result:08b})")
        
        # Calculate expected bit values
        expected_bits = [(byte_result >> i) & 1 for i in range(8)]
        print("Expected bits (LSB first):", [bool(b) for b in expected_bits])
        
        print("\nTesting individual bit reads:")
        for i in range(8):
            addr = f"DB1,X0.{i}"
            
            # Non-optimized read
            result_non_opt = client.read([addr], optimize=False)[0]
            
            # Optimized read
            result_opt = client.read([addr], optimize=True)[0]
            
            expected = bool(expected_bits[i])
            
            status_non = "✓" if result_non_opt == expected else "✗"
            status_opt = "✓" if result_opt == expected else "✗"
            consistency = "✓" if result_non_opt == result_opt else "✗"
            
            print(f"  Bit {i} ({addr}): Non-opt={result_non_opt} {status_non}, Opt={result_opt} {status_opt}, Consistent={consistency}")
        
        print("\nTesting batch optimized read:")
        batch_addresses = [f"DB1,X0.{i}" for i in range(8)]
        batch_results = client.read(batch_addresses, optimize=True)
        
        all_correct = True
        for i, result in enumerate(batch_results):
            expected = bool(expected_bits[i])
            status = "✓" if result == expected else "✗"
            if result != expected:
                all_correct = False
            print(f"  Bit {i}: {result} {status} (expected: {expected})")
        
        print(f"\nBatch consistency: {'✓ PASSED' if all_correct else '✗ FAILED'}")
        
        client.disconnect()
        
    except Exception as e:
        print(f"❌ Bit test error: {e}")

if __name__ == "__main__":
    discover_plc_values()
    test_bit_consistency()