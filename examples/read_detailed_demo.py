"""
Example demonstrating read_detailed() method for detailed read results.

The read_detailed() method provides per-tag success/failure information,
unlike read() which fails-fast on the first error.

Use read_detailed() when you need to:
- Know which reads succeeded and which failed in a batch operation
- Continue processing all tags even if some fail
- Get detailed error messages for troubleshooting
- Implement retry logic for failed reads only
- Collect partial data from a PLC with some inaccessible areas
"""

from pyS7 import S7Client, ReadResult
from pyS7.constants import ConnectionType


def main():
    # Connect to PLC
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        print("Connected to PLC")
        
        # Tags to read
        tags = [
            "DB1,I0",      # Integer at DB1.DBW0
            "DB1,R4",      # Real at DB1.DBD4
            "DB99,I0",     # This might fail if DB99 doesn't exist
            "DB1,X8.0",    # Bit at DB1.DBX8.0
            "DB1,S10.20",  # String at DB1 starting at byte 10, max 20 chars
        ]
        
        # Perform read with detailed results
        print(f"\nReading {len(tags)} tags...")
        results = client.read_detailed(tags)
        
        # Process results
        success_count = 0
        failure_count = 0
        
        for i, result in enumerate(results):
            if result.success:
                print(f"✓ Tag {i+1} ({tags[i]}): {result.value}")
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
        
        # Example: Collect only successful values
        successful_data = {}
        for i, result in enumerate(results):
            if result.success:
                successful_data[tags[i]] = result.value
        
        print(f"\n=== Collected Data ===")
        for tag, value in successful_data.items():
            print(f"{tag}: {value}")
        
        # Example: Retry only failed reads
        if failure_count > 0:
            print("\n=== Retrying failed reads ===")
            failed_tags = [tags[i] for i, r in enumerate(results) if not r.success]
            
            print(f"Retrying {len(failed_tags)} failed tag(s)...")
            retry_results = client.read_detailed(failed_tags)
            
            for i, result in enumerate(retry_results):
                if result.success:
                    print(f"✓ Retry {i+1}: {result.value}")
                else:
                    print(f"✗ Retry {i+1}: Still failed - {result.error}")
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        if client.is_connected:
            client.disconnect()
            print("\nDisconnected from PLC")


def compare_read_methods():
    """
    Compare read() vs read_detailed() behavior.
    """
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        tags = ["DB1,I0", "DB99,I0", "DB1,I4"]  # DB99 might not exist
        
        print("=== Using read() (fail-fast) ===")
        try:
            # read() will raise exception on first error
            # Tags after the error point are NOT read
            values = client.read(tags)
            print(f"All reads succeeded: {values}")
        except Exception as e:
            print(f"read() failed: {e}")
            print("Cannot determine which tags succeeded")
        
        print("\n=== Using read_detailed() (continue on error) ===")
        # read_detailed() continues even if some tags fail
        results = client.read_detailed(tags)
        
        for i, result in enumerate(results):
            if result.success:
                status = f"SUCCESS: {result.value}"
            else:
                status = f"FAILED: {result.error}"
            print(f"Tag {i+1} ({tags[i]}): {status}")
        
    finally:
        if client.is_connected:
            client.disconnect()


def batch_read_with_validation():
    """
    Example: Read multiple data types and handle different error scenarios.
    """
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        # Mix of different data types
        tags = [
            "DB1,X0.0",     # BIT
            "DB1,B1",       # BYTE
            "DB1,I2",       # INT
            "DB1,DI4",      # DINT
            "DB1,R8",       # REAL
            "DB1,S12.10",   # STRING
            "DB99,I0",      # Invalid DB (will fail)
            "M10.5",        # Merker bit
        ]
        
        results = client.read_detailed(tags)
        
        # Categorize results
        successful_reads = []
        access_errors = []
        communication_errors = []
        other_errors = []
        
        for i, result in enumerate(results):
            if result.success:
                successful_reads.append((tags[i], result.value))
            else:
                if result.error_code == 0x05:  # Address out of range
                    access_errors.append((tags[i], result.error))
                elif result.error_code == 0x0A:  # Object not available
                    access_errors.append((tags[i], result.error))
                elif "communication" in result.error.lower():
                    communication_errors.append((tags[i], result.error))
                else:
                    other_errors.append((tags[i], result.error))
        
        # Report successful reads
        print(f"Successfully read {len(successful_reads)} tag(s):")
        for tag, value in successful_reads:
            print(f"  {tag}: {value}")
        
        # Report errors by category
        if access_errors:
            print("\nAccess errors (check address configuration):")
            for tag, error in access_errors:
                print(f"  {tag}: {error}")
        
        if communication_errors:
            print("\nCommunication errors (check connection):")
            for tag, error in communication_errors:
                print(f"  {tag}: {error}")
        
        if other_errors:
            print("\nOther errors:")
            for tag, error in other_errors:
                print(f"  {tag}: {error}")
        
    finally:
        if client.is_connected:
            client.disconnect()


def partial_data_collection():
    """
    Example: Collect data from multiple DBs, some may not be accessible.
    Useful for diagnostics or monitoring where partial data is acceptable.
    """
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        # Try to read from multiple data blocks
        # Some might not exist or be accessible
        tags = []
        for db_num in [1, 2, 10, 20, 50, 99, 100]:
            tags.append(f"DB{db_num},I0")  # First INT in each DB
        
        print(f"Attempting to read from {len(tags)} data blocks...")
        results = client.read_detailed(tags)
        
        # Create a map of accessible DBs
        accessible_dbs = {}
        inaccessible_dbs = []
        
        for i, result in enumerate(results):
            db_num = int(tags[i].split(',')[0].replace('DB', ''))
            if result.success:
                accessible_dbs[db_num] = result.value
            else:
                inaccessible_dbs.append((db_num, result.error))
        
        print(f"\n=== Accessible Data Blocks: {len(accessible_dbs)} ===")
        for db_num, value in accessible_dbs.items():
            print(f"DB{db_num}: {value}")
        
        print(f"\n=== Inaccessible Data Blocks: {len(inaccessible_dbs)} ===")
        for db_num, error in inaccessible_dbs:
            print(f"DB{db_num}: {error}")
        
        # Now we can focus on reading more data from accessible DBs
        if accessible_dbs:
            print(f"\n=== Reading additional data from accessible DBs ===")
            additional_tags = []
            for db_num in accessible_dbs.keys():
                additional_tags.extend([
                    f"DB{db_num},I2",
                    f"DB{db_num},R4",
                ])
            
            additional_results = client.read_detailed(additional_tags)
            success_count = sum(1 for r in additional_results if r.success)
            print(f"Successfully read {success_count}/{len(additional_tags)} additional tags")
        
    finally:
        if client.is_connected:
            client.disconnect()


def integration_with_write_detailed():
    """
    Example: Read values, modify them, and write back with detailed error handling.
    """
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        tags = ["DB1,I0", "DB1,I2", "DB1,I4"]
        
        # Read current values
        print("=== Reading current values ===")
        read_results = client.read_detailed(tags)
        
        # Prepare values to write (increment by 1)
        write_tags = []
        write_values = []
        
        for i, result in enumerate(read_results):
            if result.success:
                print(f"{tags[i]}: {result.value}")
                write_tags.append(tags[i])
                write_values.append(result.value + 1)
            else:
                print(f"{tags[i]}: Cannot read - {result.error}")
        
        # Write modified values (only for successfully read tags)
        if write_tags:
            print(f"\n=== Writing modified values ===")
            write_results = client.write_detailed(write_tags, write_values)
            
            for i, result in enumerate(write_results):
                if result.success:
                    print(f"✓ {write_tags[i]}: Written successfully")
                else:
                    print(f"✗ {write_tags[i]}: Write failed - {result.error}")
        
    finally:
        if client.is_connected:
            client.disconnect()


if __name__ == "__main__":
    print("=" * 60)
    print("Example 1: Basic read_detailed() usage")
    print("=" * 60)
    main()
    
    print("\n" + "=" * 60)
    print("Example 2: Comparing read() vs read_detailed()")
    print("=" * 60)
    compare_read_methods()
    
    print("\n" + "=" * 60)
    print("Example 3: Batch read with error categorization")
    print("=" * 60)
    batch_read_with_validation()
    
    print("\n" + "=" * 60)
    print("Example 4: Partial data collection (discovering accessible DBs)")
    print("=" * 60)
    partial_data_collection()
    
    print("\n" + "=" * 60)
    print("Example 5: Integration with write_detailed()")
    print("=" * 60)
    integration_with_write_detailed()
