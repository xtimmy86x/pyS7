# Best Practices Guide

This guide provides recommended patterns and practices for using pyS7 in production applications.

## Table of Contents
- [Connection Management](#connection-management)
- [Error Handling](#error-handling)
- [Type Safety](#type-safety)
- [Performance Optimization](#performance-optimization)
- [Production Deployment](#production-deployment)

## Connection Management

### Use context managers

The cleanest way to manage connections is with the context manager:

```python
from pyS7 import S7Client

# Recommended: Automatic cleanup
with S7Client("192.168.5.100", 0, 1) as client:
    data = client.read(["DB1,I0"])
    client.write(["DB1,I2"], [100])
    # Connection automatically closed on exit (even with errors)

# Also works with exceptions
try:
    with S7Client("192.168.5.100", 0, 1) as client:
        data = client.read(["DB1,I0"])
except Exception as e:
    print(f"Error: {e}")
    # Connection still properly closed
```

### Manual connection management

If you need manual control:

```python
from pyS7 import S7Client

client = S7Client("192.168.5.100", 0, 1)

try:
    client.connect()
    
    # Your operations
    data = client.read(["DB1,I0"])
    
finally:
    # Always disconnect, even if errors occur
    if client.is_connected:
        client.disconnect()
```

### Reuse connections

Creating connections is expensive. Reuse when possible:

```python
# Good: Reuse connection for multiple operations
with S7Client("192.168.5.100", 0, 1) as client:
    for i in range(100):
        data = client.read(["DB1,I0"])
        # Process data
        time.sleep(0.1)

# Bad: New connection each iteration (slow!)
for i in range(100):
    with S7Client("192.168.5.100", 0, 1) as client:
        data = client.read(["DB1,I0"])
    time.sleep(0.1)
```

### Check connection status

Before critical operations, verify connection:

```python
from pyS7 import S7Client, S7CommunicationError

client = S7Client("192.168.5.100", 0, 1)
client.connect()

# Before important operation
if not client.is_connected:
    print("Warning: Not connected to PLC")
    client.connect()  # Reconnect

try:
    data = client.read(["DB1,I0"])
except S7CommunicationError:
    # Connection lost during operation
    client.connect()  # Reconnect
    data = client.read(["DB1,I0"])  # Retry
```

### Connection pooling pattern

For high-throughput applications:

```python
from pyS7 import S7Client
import queue
import threading

class S7ConnectionPool:
    def __init__(self, plc_ip, rack, slot, pool_size=5):
        self.pool = queue.Queue(maxsize=pool_size)
        
        # Create pool of connections
        for _ in range(pool_size):
            client = S7Client(plc_ip, rack, slot)
            client.connect()
            self.pool.put(client)
    
    def get_client(self, timeout=5):
        """Get a client from the pool."""
        try:
            return self.pool.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("No available connections in pool")
    
    def return_client(self, client):
        """Return a client to the pool."""
        if client.is_connected:
            self.pool.put(client)
        else:
            # Reconnect before returning
            client.connect()
            self.pool.put(client)
    
    def close_all(self):
        """Close all connections in pool."""
        while not self.pool.empty():
            client = self.pool.get_nowait()
            client.disconnect()

# Usage
pool = S7ConnectionPool("192.168.5.100", 0, 1, pool_size=5)

def read_data(tag):
    client = pool.get_client()
    try:
        return client.read([tag])
    finally:
        pool.return_client(client)

# Multiple threads can use the pool
data = read_data("DB1,I0")

# Cleanup
pool.close_all()
```

## Error Handling

### Handle specific exceptions

```python
from pyS7 import (
    S7Client,
    S7ConnectionError,
    S7CommunicationError,
    S7AddressError
)

try:
    client = S7Client("192.168.5.100", 0, 1)
    client.connect()
    
    data = client.read(["DB1,I0"])
    
except S7ConnectionError as e:
    # Connection failed (network issues, wrong IP, etc.)
    print(f"Cannot connect to PLC: {e}")
    # Maybe try backup PLC?
    
except S7CommunicationError as e:
    # Communication error after connection (timeout, disconnect)
    print(f"Communication lost: {e}")
    # Maybe reconnect and retry?
    
except S7AddressError as e:
    # Invalid address or tag configuration
    print(f"Invalid tag: {e}")
    # Fix the address in code
    
except Exception as e:
    # Catch-all for unexpected errors
    print(f"Unexpected error: {e}")
    
finally:
    # Always cleanup
    if 'client' in locals() and client.is_connected:
        client.disconnect()
```

### Implement retry logic

For unreliable networks:

```python
import time
from pyS7 import S7Client, S7CommunicationError

def robust_read(plc_ip, rack, slot, tags, max_retries=3, backoff=2):
    """Read with exponential backoff retry."""
    
    for attempt in range(max_retries):
        client = None
        try:
            client = S7Client(plc_ip, rack, slot)
            client.connect()
            return client.read(tags)
            
        except S7CommunicationError as e:
            if attempt == max_retries - 1:
                # Last attempt failed
                raise RuntimeError(f"Failed after {max_retries} attempts") from e
            
            # Wait with exponential backoff
            wait_time = backoff ** attempt
            print(f"Attempt {attempt + 1} failed. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
        finally:
            if client and client.is_connected:
                client.disconnect()

# Usage
try:
    data = robust_read("192.168.5.100", 0, 1, ["DB1,I0"], max_retries=3)
    print(f"Data: {data}")
except RuntimeError as e:
    print(f"All retries failed: {e}")
```

### Validation before operations

```python
from pyS7 import S7Client

def safe_write(client, tags, values):
    """Write with validation."""
    
    # Validate inputs
    if len(tags) != len(values):
        raise ValueError(f"Tag count ({len(tags)}) != value count ({len(values)})")
    
    # Validate connection
    if not client.is_connected:
        raise RuntimeError("Client not connected")
    
    # Perform write
    client.write(tags, values)
```

### Choose the right method for error handling

pyS7 provides three approaches to batch operations, each suited for different scenarios:

#### Use `read()` / `write()` when:
- **All tags must succeed** or the operation is meaningless
- You want **fail-fast behavior** (stop on first error)
- Tags are known to be valid and accessible
- Simplified error handling is acceptable

```python
from pyS7 import S7Client

with S7Client("192.168.5.100", 0, 1) as client:
    try:
        # All or nothing - raises exception on first failure
        data = client.read(["DB1,I0", "DB1,I2", "DB1,R4"])
        print(f"All reads succeeded: {data}")
    except Exception as e:
        print(f"One or more reads failed: {e}")
        # Cannot determine which specific tag failed
```

#### Use `read_detailed()` / `write_detailed()` when:
- **Partial success is acceptable** (some tags may fail)
- You need to **know which specific tags failed**
- Working with potentially inaccessible areas
- Implementing **custom retry logic** for failed tags
- **Collecting diagnostic data** from multiple sources
- Need detailed error information per tag

```python
from pyS7 import S7Client

with S7Client("192.168.5.100", 0, 1) as client:
    # Continue even if some tags fail
    tags = ["DB1,I0", "DB99,I0", "DB1,R4"]  # DB99 may not exist
    results = client.read_detailed(tags)
    
    # Process each result individually
    successful_data = {}
    failed_tags = []
    
    for result in results:
        if result.success:
            successful_data[str(result.tag)] = result.value
        else:
            failed_tags.append((str(result.tag), result.error))
            print(f"Failed: {result.tag} - {result.error}")
    
    # Retry only failed tags
    if failed_tags:
        retry_tags = [tag for tag, _ in failed_tags]
        retry_results = client.read_detailed(retry_tags)
        for result in retry_results:
            if result.success:
                successful_data[str(result.tag)] = result.value
    
    print(f"Collected {len(successful_data)} values from {len(tags)} tags")
```

**read_detailed() / write_detailed() use cases:**
- Discovering which data blocks exist in a PLC
- Monitoring system with some sensors offline
- Batch operations where partial data is useful
- Error categorization and reporting
- Resilient data collection in production

#### Use `batch_write()` when:
- **Atomicity is required** (all writes must succeed or all revert)
- Need **automatic rollback** on failure
- Writing related data that must stay consistent
- Testing with automatic cleanup
- Critical operations requiring verification

```python
from pyS7 import S7Client

with S7Client("192.168.5.100", 0, 1) as client:
    # Transactional write with automatic rollback
    try:
        with client.batch_write() as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            batch.add("DB1,R4", 3.14)
            # Auto-commits on exit
            # Rolls back to original values on any error
        print("All writes succeeded and verified")
    
    except Exception as e:
        print(f"Batch write failed and rolled back: {e}")
        # Original values automatically restored
```

**batch_write() use cases:**
- Recipe/parameter changes that must be complete or reverted
- Multi-step processes requiring data consistency
- Critical setpoint updates
- Testing/debugging with automatic cleanup
- Configuration updates that must be atomic

**Comparison table:**

| Scenario | Recommended Method | Why |
|----------|-------------------|-----|
| Read sensor values (all required) | `read()` | Fail-fast, simple |
| Read multiple DBs (some may not exist) | `read_detailed()` | Partial success OK |
| Write production setpoints | `batch_write()` | Atomicity required |
| Write to various PLCs/areas | `write_detailed()` | Individual error handling |
| Update recipe (all values related) | `batch_write()` | Rollback on failure |
| Diagnostic data collection | `read_detailed()` | Continue on errors |
| Single critical value | `write()` | Simple, clear |
| Testing new configuration | `batch_write()` | Auto cleanup on error |

    
    # Check connection
    if not client.is_connected:
        raise RuntimeError("Client not connected")
    
    # Check CPU status for critical operations
    status = client.get_cpu_status()
    if status != "RUN":
        raise RuntimeError(f"PLC not in RUN mode (current: {status})")
    
    # Perform write
    client.write(tags, values)
    
    # Verify write (read back)
    readback = client.read(tags)
    for i, (expected, actual) in enumerate(zip(values, readback)):
        if expected != actual:
            print(f"Warning: Tag {tags[i]} - expected {expected}, got {actual}")

# Usage
with S7Client("192.168.5.100", 0, 1) as client:
    safe_write(client, ["DB1,I0"], [100])
```

## Type Safety

### Use S7Tag for clarity

```python
from pyS7 import S7Tag, DataType, MemoryArea

# Explicit and type-safe
tag = S7Tag(
    memory_area=MemoryArea.DB,
    db_number=1,
    data_type=DataType.INT,
    start=10,
    bit_offset=0,
    length=5  # Read 5 consecutive INTs
)

data = client.read([tag])
# data[0] is Tuple[int, int, int, int, int]
```

### Type hints in your code

```python
from typing import List, Tuple
from pyS7 import S7Client, S7Tag

def read_sensor_data(client: S7Client) -> Tuple[int, float, bool]:
    """Read temperature, pressure, and alarm status."""
    
    tags: List[str] = [
        "DB1,I0",    # Temperature (INT)
        "DB1,R2",    # Pressure (REAL)
        "DB1,X6.0"   # Alarm (BOOL)
    ]
    
    data = client.read(tags)
    
    temperature: int = data[0]
    pressure: float = data[1]
    alarm: bool = data[2]
    
    return temperature, pressure, alarm

# Usage with type checking
with S7Client("192.168.5.100", 0, 1) as client:
    temp, press, alarm = read_sensor_data(client)
    print(f"Temp: {temp}°C, Pressure: {press} bar, Alarm: {alarm}")
```

### Data validation

```python
from pyS7 import S7Client

def read_validated_int(client: S7Client, tag: str, min_val: int, max_val: int) -> int:
    """Read INT with range validation."""
    
    data = client.read([tag])
    value = data[0]
    
    if not isinstance(value, int):
        raise TypeError(f"Expected int, got {type(value)}")
    
    if not (min_val <= value <= max_val):
        raise ValueError(f"Value {value} out of range [{min_val}, {max_val}]")
    
    return value

# Usage
with S7Client("192.168.5.100", 0, 1) as client:
    temperature = read_validated_int(client, "DB1,I0", min_val=-50, max_val=150)
```

## Performance Optimization

### Batch operations

```python
# Good: Read multiple tags at once
tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,R10", "DB1,R14"]
data = client.read(tags)  # Single optimized request

# Bad: Individual reads (5x slower!)
temp = client.read(["DB1,I0"])[0]
pressure = client.read(["DB1,I2"])[0]
flow = client.read(["DB1,I4"])[0]
setpoint1 = client.read(["DB1,R10"])[0]
setpoint2 = client.read(["DB1,R14"])[0]
```

### Use arrays

```python
from pyS7 import S7Tag, DataType, MemoryArea

# Good: Single array read
tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 100)
data = client.read([tag])[0]  # Tuple of 100 INTs

# Bad: 100 individual reads
data = [client.read([f"DB1,I{i*2}"])[0] for i in range(100)]
```

### Optimize tag grouping

```python
# Excellent: Contiguous in same DB
tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,I6"]  # Can be optimized into one read

# Good: Same DB, not contiguous
tags = ["DB1,I0", "DB1,I10", "DB1,I20"]  # Separate reads but efficient

# Less efficient: Different DBs
tags = ["DB1,I0", "DB5,I0", "DB10,I0"]  # Must be separate requests
```

### Selective optimization

```python
# Most operations: use optimization
data = client.read(tags, optimize=True)  # Default

# When you need predictable timing: disable optimization
data = client.read(tags, optimize=False)  # Each tag read separately
```

### Cache static data

```python
from pyS7 import S7Client

class PLCInterface:
    def __init__(self, client: S7Client):
        self.client = client
        self._cpu_info = None  # Cache
    
    def get_cpu_info(self, use_cache=True):
        """Get CPU info (cached)."""
        if use_cache and self._cpu_info is not None:
            return self._cpu_info
        
        self._cpu_info = self.client.get_cpu_info()
        return self._cpu_info
    
    def read_dynamic_data(self):
        """Always read fresh."""
        return self.client.read(["DB1,I0", "DB1,R2"])

# Usage
with S7Client("192.168.5.100", 0, 1) as client:
    plc = PLCInterface(client)
    
    info = plc.get_cpu_info()  # Reads from PLC
    info2 = plc.get_cpu_info()  # Returns cached
    
    data = plc.read_dynamic_data()  # Always fresh
```

## Production Deployment

### Logging configuration

```python
import logging
from pyS7 import S7Client

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,  # INFO for production, DEBUG for troubleshooting
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('plc_communication.log'),
        logging.StreamHandler()
    ]
)

# pyS7 uses 'pyS7.client' logger
logger = logging.getLogger('pyS7.client')
logger.setLevel(logging.INFO)

# Your application logger
app_logger = logging.getLogger(__name__)

with S7Client("192.168.5.100", 0, 1) as client:
    app_logger.info("Connected to PLC")
    data = client.read(["DB1,I0"])
    app_logger.info(f"Read data: {data}")
```

### Configuration management

```python
import json
from pathlib import Path
from pyS7 import S7Client

class PLCConfig:
    def __init__(self, config_file: Path):
        with open(config_file) as f:
            self.config = json.load(f)
    
    def create_client(self):
        """Create client from configuration."""
        return S7Client(
            address=self.config['plc']['address'],
            rack=self.config['plc']['rack'],
            slot=self.config['plc']['slot'],
            timeout=self.config['plc'].get('timeout', 5.0),
            pdu_size=self.config['plc'].get('pdu_size', 960)
        )
    
    def get_tags(self, group: str):
        """Get tag list by group."""
        return self.config['tags'][group]

# config.json:
# {
#   "plc": {
#     "address": "192.168.5.100",
#     "rack": 0,
#     "slot": 1,
#     "timeout": 5.0
#   },
#   "tags": {
#     "sensors": ["DB1,I0", "DB1,R2", "DB1,R6"],
#     "actuators": ["DB2,X0.0", "DB2,X0.1"]
#   }
# }

# Usage
config = PLCConfig(Path("config.json"))
with config.create_client() as client:
    sensor_data = client.read(config.get_tags("sensors"))
```

### Health monitoring

```python
import time
from pyS7 import S7Client, S7CommunicationError

class PLCHealthMonitor:
    def __init__(self, plc_ip, rack, slot):
        self.plc_ip = plc_ip
        self.rack = rack
        self.slot = slot
        self.last_success = None
        self.error_count = 0
    
    def check_health(self) -> dict:
        """Check PLC health status."""
        result = {
            'connected': False,
            'status': None,
            'pdu_size': None,
            'error': None,
            'last_success': self.last_success
        }
        
        client = None
        try:
            client = S7Client(self.plc_ip, self.rack, self.slot, timeout=2.0)
            client.connect()
            
            result['connected'] = True
            result['status'] = client.get_cpu_status()
            result['pdu_size'] = client.pdu_size
            
            self.last_success = time.time()
            self.error_count = 0
            
        except Exception as e:
            result['error'] = str(e)
            self.error_count += 1
            
        finally:
            if client and client.is_connected:
                client.disconnect()
        
        return result
    
    def is_healthy(self, max_errors=3) -> bool:
        """Check if PLC is considered healthy."""
        if self.error_count >= max_errors:
            return False
        
        if self.last_success is None:
            return False
        
        # Consider unhealthy if no success in last 60 seconds
        if time.time() - self.last_success > 60:
            return False
        
        return True

# Usage in monitoring loop
monitor = PLCHealthMonitor("192.168.5.100", 0, 1)

while True:
    health = monitor.check_health()
    print(f"Health: {health}")
    
    if not monitor.is_healthy():
        print("Alert: PLC unhealthy!")
    
    time.sleep(10)  # Check every 10 seconds
```

### Graceful shutdown

```python
import signal
import sys
from pyS7 import S7Client

class PLCApplication:
    def __init__(self):
        self.client = None
        self.running = True
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def run(self):
        """Main application loop."""
        self.client = S7Client("192.168.5.100", 0, 1)
        
        try:
            self.client.connect()
            print("Connected to PLC")
            
            while self.running:
                # Your application logic
                data = self.client.read(["DB1,I0"])
                print(f"Data: {data}")
                time.sleep(1)
                
        finally:
            if self.client and self.client.is_connected:
                print("Disconnecting from PLC...")
                self.client.disconnect()
            print("Shutdown complete")

if __name__ == "__main__":
    app = PLCApplication()
    app.run()
```
