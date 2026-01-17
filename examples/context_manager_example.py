"""
Example demonstrating the use of S7Client as a context manager.

The context manager automatically handles connection and disconnection,
ensuring proper cleanup even if errors occur during communication.
"""

from pyS7 import S7Client

if __name__ == "__main__":
    # Using S7Client as a context manager
    # Connection is established automatically when entering the context
    # Disconnection is guaranteed when exiting, even if an exception occurs
    
    with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
        # Connection is now established
        print(f"Connected to PLC: {client.is_connected}")
        
        # Perform operations
        tags = ["DB1,X0.0", "DB1,I10", "DB1,R14"]
        values = client.read(tags)
        print(f"Read values: {values}")
        
        # Write data
        client.write(["DB1,X0.0"], [True])
        print("Write successful")
        
        # Get CPU status
        status = client.get_cpu_status()
        print(f"CPU status: {status}")
    
    # Connection is automatically closed here
    print(f"Disconnected from PLC: {client.is_connected}")
    
    # Example using is_connected property for conditional logic
    client = S7Client(address="192.168.5.100", rack=0, slot=1)
    
    print(f"Before connect: {client.is_connected}")  # False
    
    try:
        client.connect()
        print(f"After connect: {client.is_connected}")  # True
        
        # Only perform operations if connected
        if client.is_connected:
            values = client.read(["DB1,X0.0"])
            print(f"Values: {values}")
    finally:
        if client.is_connected:
            client.disconnect()
            print(f"After disconnect: {client.is_connected}")  # False
    
    # Compare with the old style (still supported):
    # client = S7Client(address="192.168.5.100", rack=0, slot=1)
    # try:
    #     client.connect()
    #     values = client.read(["DB1,X0.0"])
    # finally:
    #     client.disconnect()
