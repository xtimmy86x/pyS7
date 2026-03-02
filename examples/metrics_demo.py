"""Example demonstrating the metrics/telemetry feature of pyS7.

This example shows how to:
1. Enable metrics tracking on S7Client
2. Access real-time performance metrics
3. Monitor connection status and errors
4. Export metrics for logging or monitoring systems
"""

import json
import time
from pyS7 import S7Client

# Example 1: Basic metrics usage
def basic_metrics_example():
    """Basic example of using metrics with S7Client."""
    print("=" * 60)
    print("Example 1: Basic Metrics Usage")
    print("=" * 60)
    
    # Create client with metrics enabled (default)
    client = S7Client(
        address="192.168.5.100",
        rack=0,
        slot=1,
        enable_metrics=True  # Metrics are enabled by default
    )
    
    try:
        # Connect to PLC
        client.connect()
        
        # Perform some operations
        tags = ["DB1,I0", "DB1,R4", "DB1,X8.0"]
        
        for i in range(5):
            # Read from PLC
            data = client.read(tags)
            print(f"Read {i+1}: {data}")
            
            # Write to PLC
            client.write(["DB1,I10"], [i * 100])
            
            time.sleep(0.5)
        
        # Access metrics properties
        print("\n--- Connection Metrics ---")
        print(f"Connected: {client.metrics.connected}")
        print(f"Uptime: {client.metrics.connection_uptime:.2f} seconds")
        print(f"Connections: {client.metrics.connection_count}")
        
        print("\n--- Operation Metrics ---")
        print(f"Total Reads: {client.metrics.read_count}")
        print(f"Total Writes: {client.metrics.write_count}")
        print(f"Total Operations: {client.metrics.total_operations}")
        
        print("\n--- Performance Metrics ---")
        print(f"Avg Read Latency: {client.metrics.avg_read_duration * 1000:.2f} ms")
        print(f"Avg Write Latency: {client.metrics.avg_write_duration * 1000:.2f} ms")
        print(f"Last Read: {client.metrics.last_read_duration * 1000:.2f} ms")
        print(f"Operations/min: {client.metrics.operations_per_minute:.1f}")
        
        print("\n--- Error Metrics ---")
        print(f"Read Errors: {client.metrics.read_errors}")
        print(f"Write Errors: {client.metrics.write_errors}")
        print(f"Timeouts: {client.metrics.timeout_errors}")
        print(f"Error Rate: {client.metrics.error_rate:.2f}%")
        print(f"Success Rate: {client.metrics.success_rate:.2f}%")
        
        print("\n--- Bandwidth Metrics ---")
        print(f"Bytes Read: {client.metrics.total_bytes_read}")
        print(f"Bytes Written: {client.metrics.total_bytes_written}")
        print(f"Avg Bytes/Read: {client.metrics.avg_bytes_per_read:.1f}")
        print(f"Avg Bytes/Write: {client.metrics.avg_bytes_per_write:.1f}")
        
    finally:
        client.disconnect()
        print(f"\nDisconnected. Total disconnections: {client.metrics.disconnection_count}")


# Example 2: Export metrics as dictionary
def export_metrics_example():
    """Example of exporting metrics for logging or monitoring."""
    print("\n")
    print("=" * 60)
    print("Example 2: Export Metrics as Dictionary")
    print("=" * 60)
    
    client = S7Client("192.168.5.100", 0, 1)
    
    try:
        client.connect()
        
        # Perform some operations
        client.read(["DB1,I0", "DB1,R4"])
        client.write(["DB1,I10"], [42])
        
        # Export all metrics as dictionary
        metrics_dict = client.metrics.as_dict()
        
        # Pretty print as JSON
        print("\nMetrics as JSON:")
        print(json.dumps(metrics_dict, indent=2))
        
        # Use case: Log to file
        # with open('plc_metrics.json', 'w') as f:
        #     json.dump(metrics_dict, f, indent=2)
        
        # Use case: Send to monitoring system
        # send_to_prometheus(metrics_dict)
        # send_to_influxdb(metrics_dict)
        
    finally:
        client.disconnect()


# Example 3: String representation
def string_representation_example():
    """Example of using string representation for quick overview."""
    print("\n")
    print("=" * 60)
    print("Example 3: String Representation")
    print("=" * 60)
    
    client = S7Client("192.168.5.100", 0, 1)
    
    try:
        client.connect()
        
        # Perform operations
        for i in range(10):
            client.read(["DB1,I0", "DB1,R4"])
            time.sleep(0.1)
        
        # Print formatted metrics overview
        print("\n" + str(client.metrics))
        
    finally:
        client.disconnect()


# Example 4: Monitoring with periodic updates
def monitoring_example():
    """Example of continuous monitoring with periodic metric updates."""
    print("\n")
    print("=" * 60)
    print("Example 4: Continuous Monitoring")
    print("=" * 60)
    
    client = S7Client("192.168.5.100", 0, 1)
    
    try:
        client.connect()
        
        # Simulate continuous operation
        for iteration in range(3):
            print(f"\n--- Iteration {iteration + 1} ---")
            
            # Perform multiple operations
            for _ in range(5):
                client.read(["DB1,I0", "DB1,R4", "DB1,X8.0"])
                client.write(["DB1,I10"], [iteration])
                time.sleep(0.2)
            
            # Display current metrics
            print(f"Operations: {client.metrics.total_operations}")
            print(f"Avg Latency: {client.metrics.avg_read_duration * 1000:.2f} ms")
            print(f"Ops/min: {client.metrics.operations_per_minute:.1f}")
            print(f"Error Rate: {client.metrics.error_rate:.2f}%")
            
        # Final summary
        print("\n--- Final Summary ---")
        print(f"Total Uptime: {client.metrics.connection_uptime:.2f} seconds")
        print(f"Total Operations: {client.metrics.total_operations}")
        print(f"Average Performance: {client.metrics.avg_read_duration * 1000:.2f} ms")
        
    finally:
        client.disconnect()


# Example 5: Error tracking
def error_tracking_example():
    """Example showing how metrics track errors."""
    print("\n")
    print("=" * 60)
    print("Example 5: Error Tracking")
    print("=" * 60)
    
    client = S7Client("192.168.5.100", 0, 1)
    
    try:
        client.connect()
        
        # Mix of successful and failed operations
        successful_tags = ["DB1,I0", "DB1,R4"]
        invalid_tags = ["DB999,I0"]  # This DB might not exist
        
        # Successful reads
        for _ in range(5):
            try:
                client.read(successful_tags)
            except Exception as e:
                print(f"Error: {e}")
        
        # Attempt invalid read (will fail and be tracked)
        try:
            client.read(invalid_tags)
        except Exception as e:
            print(f"Expected error: {e}")
        
        # Check error metrics
        print(f"\nTotal Operations: {client.metrics.total_operations}")
        print(f"Successful: {client.metrics.total_operations - client.metrics.total_errors}")
        print(f"Failed: {client.metrics.total_errors}")
        print(f"Error Rate: {client.metrics.error_rate:.2f}%")
        
    finally:
        client.disconnect()


# Example 6: Disable metrics (for minimal overhead)
def disabled_metrics_example():
    """Example showing how to disable metrics."""
    print("\n")
    print("=" * 60)
    print("Example 6: Metrics Disabled")
    print("=" * 60)
    
    # Create client with metrics disabled
    client = S7Client(
        address="192.168.5.100",
        rack=0,
        slot=1,
        enable_metrics=False  # Disable metrics for minimal overhead
    )
    
    print(f"Metrics enabled: {client.metrics is not None}")
    print(f"Metrics object: {client.metrics}")
    
    # Client works normally, just without metrics tracking
    try:
        client.connect()
        data = client.read(["DB1,I0"])
        print(f"Read successful: {data}")
        # client.metrics would be None, so don't access it
    finally:
        client.disconnect()


# Example 7: Reset metrics
def reset_metrics_example():
    """Example showing how to reset metrics."""
    print("\n")
    print("=" * 60)
    print("Example 7: Reset Metrics")
    print("=" * 60)
    
    client = S7Client("192.168.5.100", 0, 1)
    
    try:
        client.connect()
        
        # Perform some operations
        for _ in range(5):
            client.read(["DB1,I0"])
        
        print(f"Operations before reset: {client.metrics.total_operations}")
        print(f"Connection count before reset: {client.metrics.connection_count}")
        
        # Reset all metrics
        client.metrics.reset()
        
        print(f"\nOperations after reset: {client.metrics.total_operations}")
        print(f"Connection count after reset: {client.metrics.connection_count}")
        print(f"Connected after reset: {client.metrics.connected}")
        
    finally:
        client.disconnect()


if __name__ == "__main__":
    print("\n🔍 pyS7 Metrics/Telemetry Examples\n")
    
    # NOTE: These examples require a real PLC connection.
    # Update the IP address and tags for your PLC.
    
    try:
        # Run examples
        basic_metrics_example()
        export_metrics_example()
        string_representation_example()
        monitoring_example()
        error_tracking_example()
        disabled_metrics_example()
        reset_metrics_example()
        
        print("\n" + "=" * 60)
        print("✅ All examples completed successfully!")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        print("\nNote: Make sure PLC is reachable and tags exist.")
        print("Update IP address and tags in the examples for your setup.")
