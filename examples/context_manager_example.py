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
        print("Connected to PLC")
        
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
    print("Disconnected from PLC")
    
    # Compare with the old style (still supported):
    # client = S7Client(address="192.168.5.100", rack=0, slot=1)
    # try:
    #     client.connect()
    #     values = client.read(["DB1,X0.0"])
    # finally:
    #     client.disconnect()
