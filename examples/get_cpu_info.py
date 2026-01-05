"""
Example demonstrating how to read CPU information from an S7 PLC.

This example shows how to use the get_cpu_info() method to retrieve
detailed information about the PLC CPU including model, serial number,
and other identification data.
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
        print("Connected successfully!\n")

        # Get the CPU information
        print("="*70)
        print("Reading CPU Information...")
        print("="*70)
        
        info = client.get_cpu_info()
        
        # Display the CPU information
        print(f"\nCPU Module Type:      {info.get('module_type_name', 'N/A')}")
        print(f"Hardware Version:     {info.get('hardware_version', 'N/A')}")
        print(f"Firmware Version:     {info.get('firmware_version', 'N/A')}")
        print(f"Index:                {info.get('index', 'N/A')}")
        
        # Show additional modules if available
        if 'modules' in info and len(info['modules']) > 1:
            print(f"\nAdditional Modules Found: {len(info['modules'])}")
            for idx, module in enumerate(info['modules'], 1):
                print(f"\n  Module {idx}:")
                print(f"    Type:     {module.get('module_type_name', 'N/A')}")
                print(f"    Index:    {module.get('index', 'N/A')}")
                print(f"    HW Ver:   {module.get('hardware_version', 'N/A')}")
                print(f"    FW Ver:   {module.get('firmware_version', 'N/A')}")
        
        # Also get the CPU status
        print(f"\n{'='*70}")
        print("CPU Status...")
        print("="*70)
        status = client.get_cpu_status()
        print(f"\nCPU Operating Mode:   {status}")
        
        print(f"\n{'='*70}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Always disconnect when done
        client.disconnect()
        print("\nDisconnected from PLC")
