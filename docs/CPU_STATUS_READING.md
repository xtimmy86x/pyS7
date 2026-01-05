# CPU Status Reading

The pyS7 library now supports reading the CPU operating status from Siemens S7 PLCs. This feature allows you to check whether the PLC CPU is in RUN, STOP, or STARTUP mode.

## Overview

The CPU status is read using the System Status List (SZL) protocol, specifically SZL ID 0x0424, which provides the CPU diagnostic status. This is a standard S7 communication protocol supported by S7-300, S7-400, S7-1200, and S7-1500 PLCs.

## Usage

### Basic Example

```python
from pyS7 import S7Client

# Create client and connect
client = S7Client(address="192.168.0.1", rack=0, slot=1)
client.connect()

# Get CPU status
status = client.get_cpu_status()
print(f"CPU Status: {status}")

# Use status in your logic
if status == "RUN":
    # Proceed with operations
    pass
elif status == "STOP":
    # Handle stopped CPU
    pass

client.disconnect()
```

### Return Values

The `get_cpu_status()` method returns one of the following string values:

- **"RUN"**: The CPU is running and executing the user program
- **"STOP"**: The CPU is stopped and not executing the user program

### Error Handling

```python
from pyS7 import S7Client, S7CommunicationError

client = S7Client(address="192.168.0.1", rack=0, slot=1)

try:
    client.connect()
    status = client.get_cpu_status()
    print(f"CPU Status: {status}")
except S7CommunicationError as e:
    print(f"Communication error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
finally:
    client.disconnect()
```

### Integration with Other Operations

You can combine CPU status checking with regular read/write operations:

```python
from pyS7 import S7Client

client = S7Client(address="192.168.0.1", rack=0, slot=1)
client.connect()

# Check CPU status before performing operations
status = client.get_cpu_status()

if status == "RUN":
    # Safe to perform read/write operations
    data = client.read(["DB1,I0", "DB1,R4"])
    print(f"Data: {data}")
    
    client.write(["DB1,I0"], [42])
    print("Write successful")
else:
    print(f"Cannot perform operations - CPU is {status}")

client.disconnect()
```

## Technical Details

### SZL Protocol

The implementation uses the System Status List (SZL) protocol:
- **SZL ID**: 0x0424 (CPU Diagnostic Status)
- **Message Type**: USERDATA (0x07)
- **Function**: CPU_FUNCTIONS (0x04)
- **Subfunction**: READ_SZL (0x01)

### Response Structure

The SZL response contains:
- SZL ID and Index
- Length of data record (length_dr) - typically 20 bytes
- Number of data records (n_dr)
- Raw data bytes

The CPU status is extracted from byte 3 of the data:
- 0x08: RUN mode
- 0x03: STOP mode
- Other values: Unknown/special states

## Advanced Usage

### Custom SZL Queries

While `get_cpu_status()` is a convenience method, you can also access the SZL functionality directly:

```python
from pyS7 import S7Client
from pyS7.constants import SZLId
from pyS7.requests import SZLRequest
from pyS7.responses import SZLResponse

client = S7Client(address="192.168.0.1", rack=0, slot=1)
client.connect()

# Request CPU diagnostic status
szl_request = SZLRequest(szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000)
response_bytes = client._S7Client__send(szl_request)

# Parse response
szl_response = SZLResponse(response=response_bytes)
szl_data = szl_response.parse()

print(f"SZL ID: 0x{szl_data['szl_id']:04X}")
print(f"Data: {szl_data['data'].hex()}")

# Get status
status = szl_response.parse_cpu_status()
print(f"Status: {status}")

client.disconnect()
```

### Other SZL IDs

The implementation supports other SZL IDs defined in the `SZLId` enum:

- `MODULE_IDENTIFICATION` (0x0011): Module identification
- `CPU_CHARACTERISTICS` (0x0131): CPU characteristics
- `USER_MEMORY_AREAS` (0x0132): User memory areas
- `SYSTEM_AREAS` (0x0174): System areas
- `CPU_LED_STATUS` (0x0119): LED status
- And more...

## Requirements

- Connection to a Siemens S7 PLC (S7-300/400/1200/1500)
- Network connectivity to the PLC
- Appropriate TSAP configuration (if using custom TSAP values)

## Compatibility

This feature has been tested with:
- S7-300 series PLCs
- S7-400 series PLCs
- S7-1200 series PLCs
- S7-1500 series PLCs

## Examples

See the `examples/get_cpu_status.py` file for a complete working example.

## Troubleshooting

### Connection Issues

If you get connection errors:
1. Verify the PLC IP address is correct
2. Check rack and slot numbers match your PLC configuration
3. Ensure network connectivity to the PLC
4. Verify no firewall is blocking port 102

### Invalid Response

If you get "Invalid SZL ID" or parsing errors:
1. Ensure the PLC supports SZL queries (most modern S7 PLCs do)
2. Check that the CPU is not in a fault state
3. Verify the PLC firmware is up to date

### Unknown Status

If you get `UNKNOWN (0xXX)` status:
1. The PLC may be in a special diagnostic mode
2. Check the PLC's front panel LEDs for error indicators
3. Review the raw byte value to diagnose the specific state
