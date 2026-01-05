"""
Example demonstrating how to read CPU status from an S7 PLC.

This example shows how to use the get_cpu_status() method to check
if the PLC CPU is in RUN or STOP mode.
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')
from pyS7 import S7Client

if __name__ == "__main__":
    # Create a new S7Client object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = S7Client(address="192.168.100.230", rack=0, slot=1)

    try:
        # Establish connection with the PLC
        print("Connecting to PLC...")
        client.connect()
        print("Connected successfully!")

        # Get the CPU status
        print("\nReading CPU status...")
        status = client.get_cpu_status()
        print(f"CPU Status: {status}")

        # You can use the status in your application logic
        if status == "RUN":
            print("✓ CPU is running - ready for operations")
        elif status == "STOP":
            print("⚠ CPU is stopped - operations not possible")
        elif status == "STARTUP":
            print("⏳ CPU is starting up - please wait")
        else:
            print(f"⚠ CPU is in an unknown state: {status}")

    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        # Always disconnect when done
        client.disconnect()
        print("\nDisconnected from PLC")
