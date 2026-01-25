"""
Example demonstrating write_detailed() method for detailed write results.

The write_detailed() method provides per-tag success/failure information,
unlike write() which fails-fast on the first error.

Use write_detailed() when you need to:
- Know which writes succeeded and which failed in a batch operation
- Continue processing all tags even if some fail
- Get detailed error messages for troubleshooting
- Implement retry logic for failed writes only
"""

from pyS7 import S7Client, WriteResult
from pyS7.constants import ConnectionType


def main():
    # Connect to PLC
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        print("Connected to PLC")
        
        # Tags to write
        tags = [
            "DB1,I0",      # Integer at DB1.DBW0
            "DB1,R4",      # Real at DB1.DBD4
            "DB99,I0",     # This might fail if DB99 doesn't exist
            "DB1,X8.0",    # Bit at DB1.DBX8.0
            "DB1,S10.20",  # String at DB1 starting at byte 10, max 20 chars
        ]
        
        # Values to write
        values = [
            42,                    # INT value
            3.14159,              # REAL value
            100,                  # INT value (may fail if DB doesn't exist)
            True,                 # BIT value
            "Hello PLC",          # STRING value
        ]
        
        # Perform write with detailed results
        print(f"\nWriting {len(tags)} tags...")
        results = client.write_detailed(tags, values)
        
        # Process results
        success_count = 0
        failure_count = 0
        
        for i, result in enumerate(results):
            if result.success:
                print(f"✓ Tag {i+1} ({tags[i]}): SUCCESS")
                success_count += 1
            else:
                print(f"✗ Tag {i+1} ({tags[i]}): FAILED")
                print(f"  Error: {result.error}")
                if result.error_code:
                    print(f"  Error code: 0x{result.error_code:02X}")
                failure_count += 1
        
        # Summary
        print(f"\n=== Summary ===")
        print(f"Total tags: {len(results)}")
        print(f"Successful: {success_count}")
        print(f"Failed: {failure_count}")
        
        # Example: Retry only failed writes
        if failure_count > 0:
            print("\n=== Retrying failed writes ===")
            failed_tags = []
            failed_values = []
            
            for i, result in enumerate(results):
                if not result.success:
                    failed_tags.append(tags[i])
                    failed_values.append(values[i])
            
            print(f"Retrying {len(failed_tags)} failed tag(s)...")
            retry_results = client.write_detailed(failed_tags, failed_values)
            
            for i, result in enumerate(retry_results):
                if result.success:
                    print(f"✓ Retry {i+1}: SUCCESS")
                else:
                    print(f"✗ Retry {i+1}: Still failed - {result.error}")
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        if client.is_connected:
            client.disconnect()
            print("\nDisconnected from PLC")


def compare_write_methods():
    """
    Compare write() vs write_detailed() behavior.
    """
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        tags = ["DB1,I0", "DB99,I0", "DB1,I4"]  # DB99 might not exist
        values = [10, 20, 30]
        
        print("=== Using write() (fail-fast) ===")
        try:
            # write() will raise exception on first error
            # Tags after the error point are NOT written
            client.write(tags, values)
            print("All writes succeeded")
        except Exception as e:
            print(f"write() failed: {e}")
            print("Cannot determine which tags succeeded")
        
        print("\n=== Using write_detailed() (continue on error) ===")
        # write_detailed() continues even if some tags fail
        results = client.write_detailed(tags, values)
        
        for i, result in enumerate(results):
            status = "SUCCESS" if result.success else f"FAILED: {result.error}"
            print(f"Tag {i+1} ({tags[i]}): {status}")
        
    finally:
        if client.is_connected:
            client.disconnect()


def batch_write_with_validation():
    """
    Example: Validate results and take action based on error types.
    """
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,I6", "DB1,I8"]
        values = [100, 200, 300, 400, 500]
        
        results = client.write_detailed(tags, values)
        
        # Categorize errors
        access_errors = []
        communication_errors = []
        other_errors = []
        
        for i, result in enumerate(results):
            if not result.success:
                if result.error_code == 0x05:  # Address out of range
                    access_errors.append((tags[i], result.error))
                elif "communication" in result.error.lower():
                    communication_errors.append((tags[i], result.error))
                else:
                    other_errors.append((tags[i], result.error))
        
        # Report by category
        if access_errors:
            print("Access errors (check address configuration):")
            for tag, error in access_errors:
                print(f"  {tag}: {error}")
        
        if communication_errors:
            print("Communication errors (check connection):")
            for tag, error in communication_errors:
                print(f"  {tag}: {error}")
        
        if other_errors:
            print("Other errors:")
            for tag, error in other_errors:
                print(f"  {tag}: {error}")
        
    finally:
        if client.is_connected:
            client.disconnect()


if __name__ == "__main__":
    print("=" * 60)
    print("Example 1: Basic write_detailed() usage")
    print("=" * 60)
    main()
    
    print("\n" + "=" * 60)
    print("Example 2: Comparing write() vs write_detailed()")
    print("=" * 60)
    compare_write_methods()
    
    print("\n" + "=" * 60)
    print("Example 3: Batch write with error categorization")
    print("=" * 60)
    batch_write_with_validation()
