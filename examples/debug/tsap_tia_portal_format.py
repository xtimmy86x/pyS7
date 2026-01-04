"""
Example demonstrating TSAP connection using Siemens TIA Portal notation.

TIA Portal uses TSAP format like "03.00", "03.01", "22.00" where each part
represents a decimal byte value (0-255).

This is more user-friendly than hexadecimal notation and matches what you
see in TIA Portal's communication settings.
"""
import sys
sys.path.insert(0, '/home/ale/pys7/pyS7')

from pyS7 import S7Client

# PLC connection details
PLC_IP = "192.168.100.230"

# Method 1: Using TIA Portal TSAP notation directly
print("Method 1: TIA Portal TSAP notation")
print("-" * 50)
client = S7Client(
    address=PLC_IP,
    local_tsap="03.00",   # TIA Portal format (equivalent to 0x0300)
    remote_tsap="03.01"   # TIA Portal format (equivalent to 0x0301)
)

try:
    client.connect()
    print(f"✓ Connected using TSAP '03.00' -> '03.01'")
    client.disconnect()
except Exception as e:
    print(f"✗ Connection failed: {e}")

print()

# Method 2: Convert TIA Portal string to integer
print("Method 2: Convert TSAP string to integer")
print("-" * 50)
local_tsap = S7Client.tsap_from_string("03.00")
remote_tsap = S7Client.tsap_from_string("03.01")
print(f"'03.00' converts to: 0x{local_tsap:04X} ({local_tsap})")
print(f"'03.01' converts to: 0x{remote_tsap:04X} ({remote_tsap})")

print()

# Method 3: Convert integer TSAP to TIA Portal string
print("Method 3: Convert integer TSAP to TIA Portal string")
print("-" * 50)
tsap_hex = 0x0301
tsap_str = S7Client.tsap_to_string(tsap_hex)
print(f"0x{tsap_hex:04X} converts to: '{tsap_str}'")

print()

# Method 4: Calculate remote TSAP from rack/slot, then convert to TIA format
print("Method 4: Rack/Slot to TIA Portal TSAP")
print("-" * 50)
rack, slot = 0, 1
remote_tsap_int = S7Client.tsap_from_rack_slot(rack, slot)
remote_tsap_str = S7Client.tsap_to_string(remote_tsap_int)
print(f"Rack {rack}, Slot {slot} -> 0x{remote_tsap_int:04X} -> '{remote_tsap_str}'")

print()

# Common TIA Portal TSAP values
print("Common TIA Portal TSAP Values")
print("-" * 50)
print("Purpose          | Local TSAP | Remote TSAP | Description")
print("-----------------|------------|-------------|---------------------------")
print("PG/PC Standard   | 03.00      | 03.01       | Rack 0, Slot 1 (typical)")
print("PG/PC Standard   | 03.00      | 03.02       | Rack 0, Slot 2")
print("OP Connection    | 22.00      | 03.01       | Operator panel")
print("HMI Connection   | 10.00      | 03.01       | HMI/SCADA")

print()

# Reference table: Rack/Slot to TIA Portal TSAP
print("Rack/Slot to TIA Portal Remote TSAP Reference")
print("-" * 50)
print("Rack | Slot | Remote TSAP | Hex Value")
print("-----|------|-------------|----------")
for rack in range(2):
    for slot in range(4):
        tsap_int = S7Client.tsap_from_rack_slot(rack, slot)
        tsap_str = S7Client.tsap_to_string(tsap_int)
        print(f"  {rack}  |  {slot:2d}  | {tsap_str:11s} | 0x{tsap_int:04X}")
