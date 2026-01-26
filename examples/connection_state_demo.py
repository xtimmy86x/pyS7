"""
Example demonstrating connection state management.

The ConnectionState enum provides visibility into the connection lifecycle,
enabling better error handling and monitoring.

Connection States:
- DISCONNECTED: Not connected to PLC
- CONNECTING: Connection in progress (TCP + COTP + PDU negotiation)
- CONNECTED: Successfully connected and ready for operations
- ERROR: Connection failed or lost due to error
- DISCONNECTING: Disconnection in progress
"""

import time
from pyS7 import S7Client, ConnectionState
from pyS7.errors import S7ConnectionError, S7TimeoutError


def basic_state_monitoring():
    """Basic example of monitoring connection state."""
    print("=" * 60)
    print("Example 1: Basic Connection State Monitoring")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1, timeout=2)
    
    print(f"Initial state: {client.connection_state.value}")
    print(f"Is connected: {client.is_connected}")
    
    try:
        print("\nAttempting to connect...")
        client.connect()
        
        print(f"State after connect: {client.connection_state.value}")
        print(f"Is connected: {client.is_connected}")
        
        # Perform operations...
        if client.is_connected:
            print("\nPerforming read operations...")
            # values = client.read(["DB1,I0", "DB1,I2"])
            # print(f"Read values: {values}")
        
    except S7TimeoutError as e:
        print(f"\nConnection timeout!")
        print(f"State: {client.connection_state.value}")
        print(f"Error: {client.last_error}")
        
    except S7ConnectionError as e:
        print(f"\nConnection error!")
        print(f"State: {client.connection_state.value}")
        print(f"Error: {client.last_error}")
        
    finally:
        if client.connection_state != ConnectionState.DISCONNECTED:
            print("\nDisconnecting...")
            client.disconnect()
        
        print(f"Final state: {client.connection_state.value}")


def retry_with_state_check():
    """Example of connection retry logic using state."""
    print("\n" + "=" * 60)
    print("Example 2: Connection Retry with State Check")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1, timeout=2)
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(1, max_retries + 1):
        print(f"\nConnection attempt {attempt}/{max_retries}")
        print(f"Current state: {client.connection_state.value}")
        
        # Only attempt connection if not already connected
        if client.connection_state == ConnectionState.CONNECTED:
            print("Already connected!")
            break
        
        try:
            client.connect()
            print(f"✓ Connected successfully")
            print(f"State: {client.connection_state.value}")
            break
            
        except (S7ConnectionError, S7TimeoutError) as e:
            print(f"✗ Connection failed: {e}")
            print(f"State: {client.connection_state.value}")
            print(f"Last error: {client.last_error}")
            
            if attempt < max_retries:
                print(f"Waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Giving up.")
    
    if client.is_connected:
        client.disconnect()


def monitor_connection_during_operations():
    """Example of monitoring connection state during operations."""
    print("\n" + "=" * 60)
    print("Example 3: Monitor State During Operations")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1)
    
    def print_state():
        """Helper to print current state."""
        state = client.connection_state
        emoji = {
            ConnectionState.DISCONNECTED: "⚫",
            ConnectionState.CONNECTING: "🟡",
            ConnectionState.CONNECTED: "🟢",
            ConnectionState.ERROR: "🔴",
            ConnectionState.DISCONNECTING: "🟠",
        }
        print(f"Status: {emoji.get(state, '⚪')} {state.value.upper()}")
    
    try:
        print_state()
        
        print("\nConnecting to PLC...")
        client.connect()
        print_state()
        
        if client.is_connected:
            print("\nReading data...")
            # Simulate operations
            tags = ["DB1,I0", "DB1,I2", "DB1,R4"]
            # values = client.read(tags)
            # print(f"Values: {values}")
            
            print("\nWriting data...")
            # client.write(["DB1,I0"], [42])
            print("Write successful")
            print_state()
            
    except Exception as e:
        print(f"\nError occurred: {e}")
        print_state()
        if client.last_error:
            print(f"Error details: {client.last_error}")
            
    finally:
        if client.connection_state != ConnectionState.DISCONNECTED:
            print("\nDisconnecting...")
            client.disconnect()
            print_state()


def state_based_error_handling():
    """Example of error handling based on connection state."""
    print("\n" + "=" * 60)
    print("Example 4: State-Based Error Handling")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1, timeout=2)
    
    def safe_operation(operation_name, operation_func):
        """Execute operation with state-aware error handling."""
        print(f"\n{operation_name}:")
        
        # Check state before operation
        if client.connection_state != ConnectionState.CONNECTED:
            print(f"  ✗ Cannot perform operation - state is {client.connection_state.value}")
            return False
        
        try:
            operation_func()
            print(f"  ✓ Success")
            return True
            
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            
            # Handle based on state
            if client.connection_state == ConnectionState.ERROR:
                print(f"  Connection lost: {client.last_error}")
                print(f"  Attempting reconnection...")
                try:
                    client.disconnect()
                    client.connect()
                    print(f"  ✓ Reconnected")
                except Exception as reconnect_error:
                    print(f"  ✗ Reconnection failed: {reconnect_error}")
            
            return False
    
    try:
        # Initial connection
        print("Establishing connection...")
        client.connect()
        print(f"State: {client.connection_state.value}")
        
        # Perform operations
        safe_operation("Read DB1.DBW0", lambda: None)  # client.read(["DB1,I0"]))
        safe_operation("Write DB1.DBW2", lambda: None)  # client.write(["DB1,I2"], [100]))
        
    except Exception as e:
        print(f"\nFatal error: {e}")
        print(f"State: {client.connection_state.value}")
        print(f"Last error: {client.last_error}")
        
    finally:
        if client.connection_state != ConnectionState.DISCONNECTED:
            client.disconnect()


def context_manager_with_state():
    """Example using context manager with state monitoring."""
    print("\n" + "=" * 60)
    print("Example 5: Context Manager with State Monitoring")
    print("=" * 60)
    
    client = S7Client("192.168.100.10", rack=0, slot=1, timeout=2)
    
    print(f"Before context: {client.connection_state.value}")
    
    try:
        with client:
            print(f"Inside context: {client.connection_state.value}")
            print(f"Is connected: {client.is_connected}")
            
            # Perform operations
            if client.is_connected:
                print("Performing operations...")
                # values = client.read(["DB1,I0"])
                # print(f"Values: {values}")
                
    except Exception as e:
        print(f"Error: {e}")
        print(f"State: {client.connection_state.value}")
        if client.last_error:
            print(f"Details: {client.last_error}")
    
    print(f"After context: {client.connection_state.value}")


def main():
    """Run all examples."""
    examples = [
        basic_state_monitoring,
        retry_with_state_check,
        monitor_connection_during_operations,
        state_based_error_handling,
        context_manager_with_state,
    ]
    
    for example in examples:
        try:
            example()
        except KeyboardInterrupt:
            print("\n\nExamples interrupted by user")
            break
        except Exception as e:
            print(f"\nExample failed with unexpected error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Examples completed")
    print("=" * 60)


if __name__ == "__main__":
    main()
