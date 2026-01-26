"""Example demonstrating batch write transactions with atomic operations.

This example shows how to use batch write transactions for:
1. Automatic commit with rollback on error
2. Manual commit without rollback
3. Method chaining for fluent API
4. Handling partial failures
5. Manual rollback control
"""

from pyS7 import S7Client


def example_1_auto_commit_with_rollback():
    """Example 1: Automatic commit with rollback on error.
    
    This is the recommended approach for most use cases. The batch
    automatically commits when the context exits, and rolls back
    all changes if any write fails.
    """
    print("=" * 60)
    print("Example 1: Auto-commit with rollback on error")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        print(f"Connected to PLC, PDU size: {client.pdu_size}")
        
        # Batch write with automatic commit and rollback
        with client.batch_write() as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            batch.add("DB1,I4", 300)
            # Automatically commits when context exits
        
        print("✓ Batch write completed successfully")
        
        # Verify writes
        values = client.read(["DB1,I0", "DB1,I2", "DB1,I4"])
        print(f"Values after batch write: {values}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


def example_2_manual_commit_no_rollback():
    """Example 2: Manual commit without rollback.
    
    Use this when you want explicit control over commit timing
    and don't need automatic rollback functionality.
    """
    print("\n" + "=" * 60)
    print("Example 2: Manual commit without rollback")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        with client.batch_write(auto_commit=False, rollback_on_error=False) as batch:
            batch.add("DB1,I0", 111)
            batch.add("DB1,I2", 222)
            batch.add("DB1,I4", 333)
            
            # Manual commit
            results = batch.commit()
            
            # Check results
            for i, result in enumerate(results):
                if result.success:
                    print(f"✓ Tag {i}: Write succeeded")
                else:
                    print(f"✗ Tag {i}: Write failed - {result.error}")
        
        print("Batch write processed")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


def example_3_method_chaining():
    """Example 3: Method chaining for fluent API.
    
    The add() method returns self, allowing for method chaining
    to build batch writes in a single expression.
    """
    print("\n" + "=" * 60)
    print("Example 3: Method chaining")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        # Method chaining for compact syntax
        with client.batch_write(auto_commit=False) as batch:
            results = (
                batch
                .add("DB1,I0", 10)
                .add("DB1,I2", 20)
                .add("DB1,I4", 30)
                .add("DB1,I6", 40)
                .add("DB1,I8", 50)
                .commit()
            )
        
        success_count = sum(1 for r in results if r.success)
        print(f"✓ {success_count}/{len(results)} writes succeeded")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


def example_4_handling_partial_failures():
    """Example 4: Handling partial failures with rollback.
    
    Demonstrates automatic rollback when some writes fail,
    restoring original values for all tags.
    """
    print("\n" + "=" * 60)
    print("Example 4: Handling partial failures with rollback")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        # Set initial values
        print("Setting initial values...")
        client.write(["DB1,I0", "DB1,I2", "DB1,I4"], [1, 2, 3])
        
        print("Initial values:", client.read(["DB1,I0", "DB1,I2", "DB1,I4"]))
        
        # Attempt batch write (may partially fail)
        with client.batch_write(auto_commit=False, rollback_on_error=True) as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB99,I2", 200)  # This might fail (DB99 may not exist)
            batch.add("DB1,I4", 300)
            
            results = batch.commit()
        
        # Check results
        failures = [r for r in results if not r.success]
        if failures:
            print(f"\n⚠ {len(failures)} writes failed:")
            for r in failures:
                print(f"  - {r.tag}: {r.error}")
            print("✓ Original values have been restored (rollback)")
        
        print("Final values:", client.read(["DB1,I0", "DB1,I2", "DB1,I4"]))
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


def example_5_manual_rollback():
    """Example 5: Manual rollback control.
    
    Shows how to manually trigger a rollback after reviewing
    the write results.
    """
    print("\n" + "=" * 60)
    print("Example 5: Manual rollback control")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        # Set initial values
        client.write(["DB1,I0", "DB1,I2"], [50, 60])
        print("Initial values:", client.read(["DB1,I0", "DB1,I2"]))
        
        with client.batch_write(auto_commit=False, rollback_on_error=False) as batch:
            batch.add("DB1,I0", 555)
            batch.add("DB1,I2", 666)
            
            results = batch.commit()
            print("After commit:", client.read(["DB1,I0", "DB1,I2"]))
            
            # Decide to rollback based on some condition
            should_rollback = True  # Your logic here
            
            if should_rollback:
                print("Deciding to rollback...")
                batch.rollback()
                print("After rollback:", client.read(["DB1,I0", "DB1,I2"]))
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


def example_6_batch_write_different_datatypes():
    """Example 6: Batch write with different data types.
    
    Demonstrates writing multiple data types in a single batch.
    """
    print("\n" + "=" * 60)
    print("Example 6: Batch write with mixed data types")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        with client.batch_write() as batch:
            batch.add("DB1,X0.0", True)      # Boolean
            batch.add("DB1,B2", 255)         # Byte
            batch.add("DB1,I4", 32000)       # Integer
            batch.add("DB1,DI6", 100000)     # Double Integer
            batch.add("DB1,R10", 3.14159)    # Real (Float)
            batch.add("DB1,S14.20", "Hello") # String
        
        print("✓ Mixed data types batch write completed")
        
        # Read back values
        values = client.read([
            "DB1,X0.0", "DB1,B2", "DB1,I4",
            "DB1,DI6", "DB1,R10", "DB1,S14.20"
        ])
        print(f"Values: {values}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


def example_7_performance_comparison():
    """Example 7: Performance comparison batch vs individual writes.
    
    Compares batch write performance against individual write operations.
    """
    print("\n" + "=" * 60)
    print("Example 7: Performance comparison")
    print("=" * 60)
    
    import time
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    try:
        client.connect()
        
        tags = [f"DB1,I{i*2}" for i in range(10)]
        values = list(range(100, 200, 10))
        
        # Individual writes
        start = time.time()
        for tag, value in zip(tags, values):
            client.write([tag], [value])
        individual_time = time.time() - start
        
        # Batch write
        start = time.time()
        with client.batch_write() as batch:
            for tag, value in zip(tags, values):
                batch.add(tag, value)
        batch_time = time.time() - start
        
        print(f"Individual writes: {individual_time:.3f}s")
        print(f"Batch write: {batch_time:.3f}s")
        print(f"Speedup: {individual_time/batch_time:.1f}x faster")
        
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Batch Write Transaction Examples")
    print("=" * 60)
    print("\nNOTE: These examples require a PLC at 192.168.100.10")
    print("Modify the IP address to match your setup.\n")
    
    # Run examples
    try:
        example_1_auto_commit_with_rollback()
        example_2_manual_commit_no_rollback()
        example_3_method_chaining()
        example_4_handling_partial_failures()
        example_5_manual_rollback()
        example_6_batch_write_different_datatypes()
        example_7_performance_comparison()
    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
    
    print("\n" + "=" * 60)
    print("Examples completed")
    print("=" * 60)
