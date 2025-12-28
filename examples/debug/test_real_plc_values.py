"""
Real PLC test script using the actual configured values from the PLC
This script reads all the test values shown in the PLC configuration
and verifies they match the expected values.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyS7.pyS7 import S7Client

def test_real_plc_values():
    """Test reading all configured PLC values and verify they match expectations"""
    
    # Expected values from the PLC configuration
    expected_values = {
        # Bool values - all false except test_bool_8
        'test_bool_1': False,    # DB1,X0.0
        'test_bool_2': False,    # DB1,X0.1  
        'test_bool_3': False,    # DB1,X0.2
        'test_bool_4': False,    # DB1,X0.3
        'test_bool_5': False,    # DB1,X0.4
        'test_bool_6': False,    # DB1,X0.5
        'test_bool_7': False,    # DB1,X0.6
        'test_bool_8': True,     # DB1,X0.7
        
        # Integer values
        'test_int': 0,           # DB1,I2.0
        'test_int2': 133,        # DB1,I4.0
        
        # Byte values  
        'test_byte': 16,         # DB1,B6.0 (16#10)
        'test_byte2': 18,        # DB1,B7.0 (16#12)
        
        # Word values
        'test_word': 16,         # DB1,W8.0 (16#10)
        'test_word2': 1075,      # DB1,W10.0 (16#433)
        
        # Real values
        'test_real': 0.0,        # DB1,R12.0
        'test_real2': 4567.9,    # DB1,R16.0
        
        # DInt values
        'test_dint': 4567,       # DB1,DI20.0
        'test_din2': 45667,      # DB1,DI24.0
        
        # DWord values
        'test_dword': 16,        # DB1,DW28.0 (16#10)
        'test_dword2': 305441844, # DB1,DW32.0 (16#1234_1234)
        
        # LReal values  
        'test_lreal': 0.0,       # DB1,LR36.0
        'test_lreal2': 13478389745, # DB1,LR44.0
        
        # String values
        'test_string': '',       # DB1,S52.0
        'test_string2': 'test',  # DB1,S308.0
        
        # Char values
        'test_char': '',         # DB1,C564.0
        'test_char2': '',        # DB1,C565.0
    }
    
    # PLC connection details
    PLC_IP = "192.168.100.230"
    RACK = 0
    SLOT = 1
    
    print("=== Real PLC Test - Configured Values ===")
    print(f"Connecting to PLC at {PLC_IP}...")
    
    try:
        # Connect to PLC
        client = S7Client(address=PLC_IP, rack=RACK, slot=SLOT)
        client.connect()
        print("✓ Connected successfully")
        
        # Test results
        passed = 0
        failed = 0
        errors = 0
        
        print("\n=== Testing Boolean Values ===")
        bool_addresses = [
            "DB1,X0.0", "DB1,X0.1", "DB1,X0.2", "DB1,X0.3",
            "DB1,X0.4", "DB1,X0.5", "DB1,X0.6", "DB1,X0.7"
        ]
        bool_names = [f"test_bool_{i+1}" for i in range(8)]
        
        # Test individual bool reads (non-optimized)
        print("  Individual reads (non-optimized):")
        for addr, name in zip(bool_addresses, bool_names):
            try:
                result = client.read([addr], optimize=False)
                expected = expected_values[name]
                if result[0] == expected:
                    print(f"    ✓ {name} ({addr}): {result[0]} (expected: {expected})")
                    passed += 1
                else:
                    print(f"    ✗ {name} ({addr}): {result[0]} (expected: {expected})")
                    failed += 1
            except Exception as e:
                print(f"    ⚠ {name} ({addr}): ERROR - {e}")
                errors += 1
        
        # Test batch bool reads (optimized)
        print("  Batch read (optimized):")
        try:
            results = client.read(bool_addresses, optimize=True)
            for i, (addr, name) in enumerate(zip(bool_addresses, bool_names)):
                expected = expected_values[name]
                if results[i] == expected:
                    print(f"    ✓ {name} ({addr}): {results[i]} (expected: {expected})")
                    passed += 1
                else:
                    print(f"    ✗ {name} ({addr}): {results[i]} (expected: {expected})")
                    failed += 1
        except Exception as e:
            print(f"    ⚠ Batch bool read: ERROR - {e}")
            errors += 8
        
        print("\n=== Testing Numeric Values ===")
        numeric_tests = [
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
        ]
        
        for addr, name, data_type in numeric_tests:
            try:
                result = client.read([addr])
                expected = expected_values[name]
                if result[0] == expected:
                    print(f"  ✓ {name} ({addr}, {data_type}): {result[0]} (expected: {expected})")
                    passed += 1
                else:
                    print(f"  ✗ {name} ({addr}, {data_type}): {result[0]} (expected: {expected})")
                    failed += 1
            except Exception as e:
                print(f"  ⚠ {name} ({addr}, {data_type}): ERROR - {e}")
                errors += 1
        
        print("\n=== Testing Large Numeric Values ===")
        large_numeric_tests = [
            ("DB1,LR36", "test_lreal", "LREAL"),
            ("DB1,LR44", "test_lreal2", "LREAL"),
        ]
        
        for addr, name, data_type in large_numeric_tests:
            try:
                result = client.read([addr])
                expected = expected_values[name]
                # For large numbers, allow some tolerance
                if abs(result[0] - expected) < 0.01 if isinstance(expected, float) else result[0] == expected:
                    print(f"  ✓ {name} ({addr}, {data_type}): {result[0]} (expected: {expected})")
                    passed += 1
                else:
                    print(f"  ✗ {name} ({addr}, {data_type}): {result[0]} (expected: {expected})")
                    failed += 1
            except Exception as e:
                print(f"  ⚠ {name} ({addr}, {data_type}): ERROR - {e}")
                errors += 1
        
        print("\n=== Testing String Values ===")
        string_tests = [
            ("DB1,S52.10", "test_string", "STRING"),     # String with max length 10
            ("DB1,S308.10", "test_string2", "STRING"),   # String with max length 10  
        ]
        
        for addr, name, data_type in string_tests:
            try:
                result = client.read([addr])
                expected = expected_values[name]
                if result[0].strip() == expected:  # Strip whitespace for string comparison
                    print(f"  ✓ {name} ({addr}, {data_type}): '{result[0]}' (expected: '{expected}')")
                    passed += 1
                else:
                    print(f"  ✗ {name} ({addr}, {data_type}): '{result[0]}' (expected: '{expected}')")
                    failed += 1
            except Exception as e:
                print(f"  ⚠ {name} ({addr}, {data_type}): ERROR - {e}")
                errors += 1
        
        print("\n=== Testing Character Values ===")
        char_tests = [
            ("DB1,C564", "test_char", "CHAR"),
            ("DB1,C565", "test_char2", "CHAR"),
        ]
        
        for addr, name, data_type in char_tests:
            try:
                result = client.read([addr])
                expected = expected_values[name]
                # Char might come back as empty string or null character
                result_char = result[0] if result[0] != '\x00' else ''
                if result_char == expected:
                    print(f"  ✓ {name} ({addr}, {data_type}): '{result_char}' (expected: '{expected}')")
                    passed += 1
                else:
                    print(f"  ✗ {name} ({addr}, {data_type}): '{result_char}' (expected: '{expected}')")
                    failed += 1
            except Exception as e:
                print(f"  ⚠ {name} ({addr}, {data_type}): ERROR - {e}")
                errors += 1
        
        print("\n=== Mixed Batch Read Test ===")
        # Test reading different data types in one optimized call
        mixed_addresses = [
            "DB1,X0.7",   # bool (true)
            "DB1,I4",     # int (133) 
            "DB1,B6",     # byte (16)
            "DB1,W10",    # word (1075)
            "DB1,R16",    # real (4567.9)
        ]
        expected_mixed = [True, 133, 16, 1075, 4567.9]
        
        try:
            results = client.read(mixed_addresses, optimize=True)
            all_correct = True
            for i, (addr, result, expected) in enumerate(zip(mixed_addresses, results, expected_mixed)):
                tolerance = 0.01 if isinstance(expected, float) else 0
                if abs(result - expected) <= tolerance if isinstance(expected, (int, float)) else result == expected:
                    print(f"  ✓ {addr}: {result} (expected: {expected})")
                else:
                    print(f"  ✗ {addr}: {result} (expected: {expected})")
                    all_correct = False
            
            if all_correct:
                print("  ✓ Mixed batch read successful")
                passed += 1
            else:
                print("  ✗ Mixed batch read failed")
                failed += 1
                
        except Exception as e:
            print(f"  ⚠ Mixed batch read: ERROR - {e}")
            errors += 1
        
        # Disconnect
        client.disconnect()
        print("\n✓ Disconnected from PLC")
        
        # Summary
        total = passed + failed + errors
        print(f"\n=== Test Summary ===")
        print(f"Total tests: {total}")
        print(f"✓ Passed: {passed}")
        print(f"✗ Failed: {failed}")
        print(f"⚠ Errors: {errors}")
        print(f"Success rate: {(passed/total)*100:.1f}%" if total > 0 else "N/A")
        
        if failed == 0 and errors == 0:
            print("\n🎉 All tests passed! PLC communication is working perfectly.")
            return True
        else:
            print(f"\n⚠ Some tests failed. Please check the PLC configuration.")
            return False
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_real_plc_values()