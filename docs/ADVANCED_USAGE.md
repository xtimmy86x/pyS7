# Advanced Usage Guide

This guide covers advanced features and configurations for pyS7.

## Table of Contents
- [TSAP Connection](#tsap-connection)
- [PDU Size Management](#pdu-size-management)
- [Automatic String Chunking](#automatic-string-chunking)
- [Connection Types](#connection-types)
- [Multi-threaded Usage](#multi-threaded-usage)

## TSAP Connection

In addition to the traditional rack/slot connection method, pyS7 supports direct TSAP (Transport Service Access Point) specification. This is useful for:
- Non-standard PLC configurations
- Third-party S7-compatible devices
- Custom communication setups where rack/slot values don't apply

### Using TIA Portal TSAP notation

The easiest way to use TSAP is with Siemens TIA Portal notation (e.g., "03.00", "03.01"):

```python
from pyS7 import S7Client

# Connect using TIA Portal TSAP format
client = S7Client(
    address="192.168.5.100",
    local_tsap="03.00",   # PG/PC connection (standard)
    remote_tsap="03.01"   # Rack 0, Slot 1
)

client.connect()
```

Common TIA Portal TSAP values:
- **PG/PC connection**: local `"03.00"`, remote `"03.01"` (Rack 0, Slot 1)
- **OP connection**: local `"22.00"`, remote `"03.01"`
- **HMI connection**: local `"10.00"`, remote `"03.01"`

### Using hexadecimal TSAP values

You can also use integer hex values directly:

```python
from pyS7 import S7Client

# Connect using hex TSAP values
client = S7Client(
    address="192.168.5.100",
    local_tsap=0x0300,   # Equivalent to "03.00"
    remote_tsap=0x0301   # Equivalent to "03.01"
)

client.connect()
```

### Converting between formats

```python
from pyS7 import S7Client

# Convert TIA Portal string to integer
local_tsap = S7Client.tsap_from_string("03.00")
print(f"0x{local_tsap:04X}")  # Output: 0x0300

# Convert integer to TIA Portal string
tsap_str = S7Client.tsap_to_string(0x0301)
print(tsap_str)  # Output: "03.01"
```

### TSAP calculation helper

If you know the rack and slot but want to use TSAP, use the `tsap_from_rack_slot()` helper:

```python
from pyS7 import S7Client

# Calculate remote TSAP from rack and slot
remote_tsap = S7Client.tsap_from_rack_slot(rack=0, slot=1)
remote_tsap_str = S7Client.tsap_to_string(remote_tsap)
print(f"Rack 0, Slot 1 -> {remote_tsap_str}")  # Output: "03.01"

# Use the calculated TSAP
client = S7Client(
    address="192.168.5.100",
    local_tsap="03.00",
    remote_tsap=remote_tsap_str
)

client.connect()
```

### TSAP formula

The remote TSAP is calculated from rack and slot using:
```
remote_tsap = 0x0100 | (rack × 32 + slot)
```

Examples:
- Rack 0, Slot 1: `0x0101` = `"01.01"`
- Rack 0, Slot 2: `0x0102` = `"01.02"`
- Rack 1, Slot 0: `0x0120` = `"01.32"`
- Rack 1, Slot 1: `0x0121` = `"01.33"`

### TSAP validation

The library automatically validates TSAP values:
- Both `local_tsap` and `remote_tsap` must be provided together
- Values must be in the range 0x0000 to 0xFFFF (0-65535)
- Values must be integers

```python
# This will raise ValueError: both TSAP values required
client = S7Client(address="192.168.5.100", local_tsap=0x0100)

# This will raise ValueError: TSAP out of range
client = S7Client(address="192.168.5.100", local_tsap=0x10000, remote_tsap=0x0101)
```

## PDU Size Management

### Understanding PDU size

The PDU (Protocol Data Unit) size is the maximum amount of data that can be exchanged in a single request/response. It's negotiated during connection and affects performance:

```python
from pyS7 import S7Client

client = S7Client(
    address="192.168.5.100",
    rack=0,
    slot=1,
    pdu_size=960  # Request PDU 960 (default is 960)
)

client.connect()
print(f"Negotiated PDU: {client.pdu_size} bytes")  # Actual PDU may be lower
```

**Common PDU sizes:**
- **S7-300/400**: Typically 240 bytes (can be configured up to 960)
- **S7-1200/1500**: Usually 480 or 960 bytes
- **Protocol overhead**: ~26 bytes per request (TPKT + COTP + S7 headers)

### Performance optimization

1. **Use optimized reads** (enabled by default):
```python
# Automatically groups contiguous tags into fewer requests
data = client.read(tags, optimize=True)  # Default
```

2. **Group related tags in the same DB**:
```python
# Good: Contiguous addresses can be read in one request
tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,I6"]

# Less efficient: Each tag requires separate request
tags = ["DB1,I0", "DB5,I0", "DB10,I0", "DB15,I0"]
```

3. **Read arrays instead of individual values**:
```python
from pyS7 import S7Tag, DataType, MemoryArea

# Efficient: Read 10 INTs in one tag
tags = [S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 10)]

# Less efficient: Read 10 individual INTs
tags = [f"DB1,I{i*2}" for i in range(10)]
```

4. **Consider PDU limits for large data**:
```python
# For BYTE arrays exceeding PDU, split manually
max_bytes = client.pdu_size - 26  # Account for overhead
if data_size > max_bytes:
    # Read in chunks
    chunk1 = client.read([S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, max_bytes)])
    chunk2 = client.read([S7Tag(MemoryArea.DB, 1, DataType.BYTE, max_bytes, 0, remaining)])
```

### Handling PDU size errors

If a tag exceeds the PDU size, pyS7 will raise a clear error:

```python
from pyS7 import S7AddressError

try:
    # BYTE[300] exceeds PDU 240
    data = client.read([S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 300)])
except S7AddressError as e:
    print(e)
    # "S7Tag(...) requires 326 bytes but PDU size is 240 bytes.
    #  Maximum data size for this PDU: 214 bytes (current tag needs 300 bytes).
    #  For BYTE arrays, read in smaller chunks.
    #  For STRING/WSTRING, automatic chunking is supported."
```

**Solutions:**
1. Increase PDU size if PLC supports it
2. Split reads into smaller chunks
3. For STRING/WSTRING, automatic chunking handles this automatically (see next section)

## Automatic String Chunking

When a STRING or WSTRING exceeds the negotiated PDU size, pyS7 automatically splits the read into multiple smaller chunks and reassembles the complete string.

### How it works

```python
# STRING[254] with PDU 240 - automatically chunked
tags = ["DB1,S100.254"]  # Declared as STRING[254] in PLC
values = client.read(tags)
print(values[0])  # Complete string, transparently chunked

# Works with WSTRING too
tags = ["DB1,WS200.254"]  # WSTRING[254]
values = client.read(tags)
print(values[0])  # Complete Unicode string, automatically chunked
```

### Behind the scenes

1. pyS7 detects if STRING/WSTRING response would exceed PDU size
2. Reads the 2-byte (STRING) or 4-byte (WSTRING) header to get actual length
3. Splits data into chunks that fit within PDU limits
4. Reassembles chunks and returns complete string
5. All done transparently - you just get the string!

### PDU size considerations

- PDU size is negotiated during connection (typically 240-960 bytes)
- Maximum data per chunk = PDU size - 26 bytes (protocol overhead)
- For PDU 240: max chunk = 214 bytes
- STRING[254] = 256 bytes → automatically split into 214 + 42 byte chunks
- WSTRING[254] = 512 bytes → split into 214 + 214 + 84 byte chunks

### Technical details

**STRING chunking:**
```
Header: 2 bytes (max_length, current_length)
Data: N bytes (actual string content)
Chunks: Read as CHAR arrays of max 214 bytes each
```

**WSTRING chunking:**
```
Header: 4 bytes (2 bytes max_length, 2 bytes current_length)
Data: N × 2 bytes (UTF-16 encoded content)
Chunks: Read as BYTE arrays of max 214 bytes each (even boundaries)
```

### Important notes

- **Only STRING and WSTRING support automatic chunking**
- For other data types (BYTE, WORD, INT, etc.) that exceed PDU size, you must manually split the read
- Chunking is logged at DEBUG level: `"Tag ... exceeds PDU size, will be read in chunks automatically"`
- Empty strings are handled efficiently without chunking

### Example with logging

```python
import logging
from pyS7 import S7Client

# Enable debug logging to see chunking activity
logging.basicConfig(level=logging.DEBUG)

client = S7Client("192.168.5.100", 0, 1)
client.connect()

# This will log chunking activity if string exceeds PDU
data = client.read(["DB1,S100.254"])
```

## Connection Types

pyS7 supports different S7 connection types:

```python
from pyS7 import S7Client, ConnectionType

# S7Basic (default) - Most common for S7-300/400/1200/1500
client = S7Client(
    address="192.168.5.100",
    rack=0,
    slot=1,
    connection_type=ConnectionType.S7Basic
)

# PG connection
client = S7Client(
    address="192.168.5.100",
    rack=0,
    slot=1,
    connection_type=ConnectionType.PG
)

# OP connection (for operator panels)
client = S7Client(
    address="192.168.5.100",
    rack=0,
    slot=1,
    connection_type=ConnectionType.OP
)
```

**When to use each:**
- **S7Basic**: Standard for most applications (default)
- **PG**: Programming device connection (TIA Portal, STEP 7)
- **OP**: Operator panel / HMI connection

## Multi-threaded Usage

Each S7Client instance should be used by a single thread. For multi-threaded applications, create separate client instances:

```python
import threading
from pyS7 import S7Client

def worker(thread_id, plc_ip):
    # Each thread gets its own client instance
    client = S7Client(plc_ip, 0, 1)
    
    try:
        client.connect()
        
        # Read data specific to this thread
        data = client.read([f"DB{thread_id},I0"])
        print(f"Thread {thread_id}: {data}")
        
    finally:
        client.disconnect()

# Create multiple threads
threads = []
for i in range(5):
    t = threading.Thread(target=worker, args=(i, "192.168.5.100"))
    threads.append(t)
    t.start()

# Wait for all threads to complete
for t in threads:
    t.join()
```

### Best practices for threading

1. **One client per thread**: Don't share S7Client instances across threads
2. **Connection pooling**: Reuse connections within the same thread
3. **Error handling**: Each thread should handle its own errors
4. **Timeout management**: Set appropriate timeouts for each client

```python
import queue
import threading
from pyS7 import S7Client, S7CommunicationError

class S7WorkerPool:
    def __init__(self, plc_ip, num_workers=4):
        self.plc_ip = plc_ip
        self.task_queue = queue.Queue()
        self.workers = []
        
        for i in range(num_workers):
            worker = threading.Thread(target=self._worker, args=(i,))
            worker.daemon = True
            worker.start()
            self.workers.append(worker)
    
    def _worker(self, worker_id):
        client = S7Client(self.plc_ip, 0, 1)
        client.connect()
        
        try:
            while True:
                task = self.task_queue.get()
                if task is None:  # Shutdown signal
                    break
                
                try:
                    result = client.read(task['tags'])
                    task['callback'](result)
                except S7CommunicationError as e:
                    print(f"Worker {worker_id} error: {e}")
                finally:
                    self.task_queue.task_done()
        finally:
            client.disconnect()
    
    def submit(self, tags, callback):
        self.task_queue.put({'tags': tags, 'callback': callback})
    
    def shutdown(self):
        for _ in self.workers:
            self.task_queue.put(None)
        for worker in self.workers:
            worker.join()

# Usage
pool = S7WorkerPool("192.168.5.100", num_workers=4)

def handle_result(data):
    print(f"Received: {data}")

# Submit multiple read tasks
for i in range(100):
    pool.submit([f"DB1,I{i*2}"], handle_result)

# Wait for completion and cleanup
pool.task_queue.join()
pool.shutdown()
```

## Timeout Configuration

Configure timeouts for different scenarios:

```python
from pyS7 import S7Client

# Short timeout for fast networks
client = S7Client(
    address="192.168.5.100",
    rack=0,
    slot=1,
    timeout=2.0  # 2 seconds
)

# Long timeout for slow/unreliable networks
client = S7Client(
    address="192.168.5.100",
    rack=0,
    slot=1,
    timeout=10.0  # 10 seconds
)

# For PLCsim or local connections
client = S7Client(
    address="127.0.0.1",
    rack=0,
    slot=1,
    timeout=1.0  # 1 second is usually enough
)
```

**Timeout recommendations:**
- **Local network (< 1ms latency)**: 2-5 seconds
- **Remote network (10-50ms latency)**: 5-10 seconds
- **Unstable network**: 10-15 seconds
- **PLCsim**: 1-2 seconds

The timeout applies to:
- Socket connection establishment
- Data send operations
- Data receive operations
