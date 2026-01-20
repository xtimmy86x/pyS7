# Troubleshooting Guide

This guide covers common issues and their solutions when using pyS7.

## Table of Contents
- [Connection Issues](#connection-issues)
- [PDU Size Errors](#pdu-size-errors)
- [Read/Write Errors](#readwrite-errors)
- [Performance Issues](#performance-issues)
- [Data Type Issues](#data-type-issues)
- [FAQ](#faq)

## Connection Issues

### Cannot connect to PLC

**Symptoms:**
```python
S7ConnectionError: Failed to connect to 192.168.1.1:102: [Errno 111] Connection refused
```

**Solutions:**

1. **Check network connectivity:**
   ```bash
   ping 192.168.1.1
   ```

2. **Verify PLC IP address and port:**
   - Default S7 port is 102
   - Check PLC configuration for actual IP

3. **Check firewall rules:**
   - Ensure port 102 is open
   - On Linux: `sudo iptables -L | grep 102`
   - On Windows: Check Windows Firewall settings

4. **Verify PLC is in RUN or accessible in STOP mode:**
   ```python
   status = client.get_cpu_status()
   print(f"PLC is in {status} mode")
   ```

5. **Try different rack/slot values:**
   ```python
   # Common configurations:
   client = S7Client("192.168.1.1", rack=0, slot=1)  # Most common
   client = S7Client("192.168.1.1", rack=0, slot=2)  # Alternative
   ```

6. **Use TSAP if rack/slot doesn't work:**
   ```python
   client = S7Client(
       address="192.168.1.1",
       local_tsap="03.00",
       remote_tsap="03.01"
   )
   ```

### Connection timeout

**Symptoms:**
```python
S7ConnectionError: Socket error during connection setup: timed out
```

**Solutions:**

1. **Increase timeout:**
   ```python
   client = S7Client(
       address="192.168.1.1",
       rack=0,
       slot=1,
       timeout=10.0  # Increase from default 5.0 seconds
   )
   ```

2. **Check network latency:**
   ```bash
   ping -c 10 192.168.1.1
   ```

3. **Verify PLC is not overloaded:**
   - Too many simultaneous connections can cause timeouts
   - Check PLC CPU load in TIA Portal

### Connection drops unexpectedly

**Symptoms:**
```python
S7CommunicationError: The connection has been closed by the peer
```

**Solutions:**

1. **Use connection check before operations:**
   ```python
   if not client.is_connected:
       client.connect()
   
   data = client.read([...])
   ```

2. **Implement reconnection logic:**
   ```python
   def safe_read(client, tags, max_retries=3):
       for attempt in range(max_retries):
           try:
               if not client.is_connected:
                   client.connect()
               return client.read(tags)
           except S7CommunicationError:
               if attempt == max_retries - 1:
                   raise
               time.sleep(1)
   ```

3. **Check PLC connection limits:**
   - S7-300/400: Limited simultaneous connections
   - S7-1200/1500: Check MaxConnections in TIA Portal

## PDU Size Errors

### Tag exceeds PDU size

**Symptoms:**
```python
S7AddressError: S7Tag(...) requires 326 bytes but PDU size is 240 bytes.
Maximum data size for this PDU: 214 bytes (current tag needs 300 bytes).
```

**Solutions:**

1. **For STRING/WSTRING - automatic chunking:**
   ```python
   # No action needed! pyS7 handles this automatically
   data = client.read(["DB1,S100.254"])  # Works even if exceeds PDU
   ```

2. **For BYTE/WORD/INT arrays - manual chunking:**
   ```python
   from pyS7 import S7Tag, DataType, MemoryArea
   
   # Calculate max array size
   max_data = client.pdu_size - 26  # Account for overhead
   max_ints = max_data // 2  # INT is 2 bytes
   
   # Read in chunks
   chunk1 = client.read([S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, max_ints)])
   chunk2 = client.read([S7Tag(MemoryArea.DB, 1, DataType.INT, max_ints*2, 0, remaining)])
   
   # Combine results
   all_data = chunk1[0] + chunk2[0]
   ```

3. **Increase PDU size (if PLC supports):**
   ```python
   client = S7Client(
       address="192.168.1.1",
       rack=0,
       slot=1,
       pdu_size=480  # Try 480 or 960 for S7-1200/1500
   )
   client.connect()
   print(f"Negotiated PDU: {client.pdu_size}")
   ```

4. **Optimize tag grouping:**
   ```python
   # Instead of one large array
   tags = [S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 300)]  # Too large!
   
   # Use multiple smaller arrays
   tags = [
       S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 100),
       S7Tag(MemoryArea.DB, 1, DataType.BYTE, 100, 0, 100),
       S7Tag(MemoryArea.DB, 1, DataType.BYTE, 200, 0, 100),
   ]
   ```

## Read/Write Errors

### Invalid address format

**Symptoms:**
```python
ValueError: Invalid address format: 'DB1,10'
```

**Solutions:**

1. **Check address syntax:**
   ```python
   # Correct formats:
   "DB1,X0.0"    # Bit
   "DB1,I10"     # INT
   "DB1,R20"     # REAL
   "DB1,S30.50"  # STRING with length
   
   # Incorrect formats:
   "DB1,10"      # Missing type
   "DB1,X0"      # Missing bit offset
   "DB1,S30"     # Missing string length
   ```

2. **Use S7Tag for complex addresses:**
   ```python
   from pyS7 import S7Tag, DataType, MemoryArea
   
   tag = S7Tag(
       memory_area=MemoryArea.DB,
       db_number=1,
       data_type=DataType.INT,
       start=10,
       bit_offset=0,
       length=1
   )
   ```

### Data type mismatch

**Symptoms:**
```python
# Writing wrong type
client.write(["DB1,I10"], ["Hello"])  # STRING to INT!
```

**Solutions:**

1. **Verify data types match:**
   ```python
   # Correct type matching
   client.write(["DB1,I10"], [123])           # INT -> int
   client.write(["DB1,R20"], [3.14])          # REAL -> float
   client.write(["DB1,X0.0"], [True])         # BIT -> bool
   client.write(["DB1,S30.10"], ["Hello"])    # STRING -> str
   ```

2. **Check array lengths:**
   ```python
   from pyS7 import S7Tag, DataType, MemoryArea
   
   # Read 5 INTs
   tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 5)
   
   # Write 5 values (as tuple)
   client.write([tag], [(10, 20, 30, 40, 50)])
   ```

### Access denied / Read-only area

**Symptoms:**
```python
S7CommunicationError: Write operation failed - area may be read-only
```

**Solutions:**

1. **Check PLC protection level:**
   - TIA Portal: PLC properties → Protection
   - Some areas may be protected in STOP mode

2. **Verify DB write permissions:**
   - Check if DB is optimized (S7-1200/1500)
   - Optimized DBs have restrictions on symbolic access

3. **Try reading first:**
   ```python
   # Verify you can read before writing
   data = client.read(["DB1,I10"])
   print(f"Current value: {data[0]}")
   
   # Then write
   client.write(["DB1,I10"], [123])
   ```

## Performance Issues

### Slow read operations

**Solutions:**

1. **Enable optimization (default):**
   ```python
   # Optimization groups contiguous tags
   data = client.read(tags, optimize=True)  # Default
   ```

2. **Group tags in same DB:**
   ```python
   # Good: All in DB1, contiguous
   tags = ["DB1,I0", "DB1,I2", "DB1,I4", "DB1,I6"]
   
   # Less efficient: Different DBs
   tags = ["DB1,I0", "DB5,I0", "DB10,I0"]
   ```

3. **Read arrays instead of individual values:**
   ```python
   # Efficient: One tag for 10 values
   tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 10)
   
   # Inefficient: 10 separate tags
   tags = [f"DB1,I{i*2}" for i in range(10)]
   ```

4. **Increase PDU size:**
   ```python
   client = S7Client(
       address="192.168.1.1",
       rack=0,
       slot=1,
       pdu_size=960  # Larger PDU = fewer requests
   )
   ```

### Too many connections

**Solutions:**

1. **Reuse client instance:**
   ```python
   # Good: Reuse connection
   client = S7Client("192.168.1.1", 0, 1)
   client.connect()
   
   for i in range(100):
       data = client.read(["DB1,I0"])
   
   client.disconnect()
   
   # Bad: New connection each time
   for i in range(100):
       client = S7Client("192.168.1.1", 0, 1)
       client.connect()
       data = client.read(["DB1,I0"])
       client.disconnect()
   ```

2. **Use context manager:**
   ```python
   with S7Client("192.168.1.1", 0, 1) as client:
       for i in range(100):
           data = client.read(["DB1,I0"])
   ```

## Data Type Issues

### STRING encoding problems

**Symptoms:**
```python
# Strange characters in strings
print(data[0])  # "Hell▒▒▒World"
```

**Solutions:**

1. **Use correct string type:**
   ```python
   # ASCII strings (S7-300/400/1200/1500)
   data = client.read(["DB1,S10.20"])  # STRING
   
   # Unicode strings (S7-1200/1500 only)
   data = client.read(["DB1,WS10.20"])  # WSTRING
   ```

2. **Check PLC string declaration:**
   - Verify STRING length matches in PLC program
   - S7-300/400: Use STRING data type
   - S7-1200/1500: Can use STRING or WSTRING

3. **Handle partial strings:**
   ```python
   # Read STRING and check actual length
   data = client.read(["DB1,S10.50"])
   actual_string = data[0].rstrip('\x00')  # Remove null padding
   ```

### REAL number precision

**Solutions:**

1. **Use appropriate data type:**
   ```python
   # Single precision (32-bit)
   data = client.read(["DB1,R10"])  # REAL
   
   # Double precision (64-bit)
   data = client.read(["DB1,LR10"])  # LREAL
   ```

2. **Round if needed:**
   ```python
   value = round(data[0], 2)  # Round to 2 decimals
   ```

## FAQ

### Q: Can I use pyS7 with S7-200?

**A:** Yes, but with limitations. S7-200 uses a different protocol variant. Some operations may not work. Consider using S7-200 SMART which has better S7 protocol support.

### Q: Does pyS7 work with S7-1200/1500?

**A:** Yes! pyS7 fully supports S7-1200 and S7-1500 PLCs, including WSTRING and larger PDU sizes.

### Q: Can I use pyS7 in multi-threaded applications?

**A:** Each S7Client instance should be used by a single thread. Create separate client instances for different threads:

```python
import threading
from pyS7 import S7Client

def worker(thread_id):
    client = S7Client("192.168.1.1", 0, 1)
    client.connect()
    data = client.read([f"DB{thread_id},I0"])
    client.disconnect()

threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

### Q: How do I read/write BOOL arrays?

**A:** Use BIT type with length > 1:

```python
from pyS7 import S7Tag, DataType, MemoryArea

# Read 8 consecutive bits
tag = S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, 0, 8)
data = client.read([tag])
print(data[0])  # Tuple of 8 booleans

# Write 8 bits
client.write([tag], [(True, False, True, False, True, False, True, False)])
```

### Q: What's the difference between optimize=True and optimize=False?

**A:** 
- `optimize=True` (default): Groups contiguous tags to minimize requests
- `optimize=False`: Reads each tag separately (slower but more predictable)

```python
# With optimization
tags = ["DB1,I0", "DB1,I2", "DB1,I4"]
data = client.read(tags, optimize=True)  # 1 request for all 3

# Without optimization  
data = client.read(tags, optimize=False)  # 3 separate requests
```

### Q: Can I read/write during PLC STOP mode?

**A:** It depends on the PLC model and configuration:
- S7-300/400: Usually yes, but some areas may be restricted
- S7-1200/1500: Depends on protection level settings
- Always check with `get_cpu_status()` first

```python
status = client.get_cpu_status()
if status == "STOP":
    print("Warning: PLC is in STOP mode")
    # Proceed with caution
```

### Q: How do I handle intermittent network issues?

**A:** Implement retry logic with exponential backoff:

```python
import time
from pyS7 import S7Client, S7CommunicationError

def robust_read(client, tags, max_retries=3):
    for attempt in range(max_retries):
        try:
            if not client.is_connected:
                client.connect()
            return client.read(tags)
        except S7CommunicationError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            print(f"Retry {attempt + 1}/{max_retries} after {wait_time}s...")
            time.sleep(wait_time)
```

### Q: What's the maximum number of tags in one read?

**A:** The protocol limits to 20 tags per request. pyS7 automatically splits larger requests:

```python
# 50 tags will be split into 3 requests (20 + 20 + 10)
tags = [f"DB1,I{i*2}" for i in range(50)]
data = client.read(tags)  # Automatic splitting
```

### Q: Can I use pyS7 with TIA Portal simulation?

**A:** Yes! Use PLCsim (S7-1200/1500) or PLCsim Advanced:

1. Start PLCsim in TIA Portal
2. Note the IP address (usually 127.0.0.1 or virtual adapter IP)
3. Connect as normal:

```python
client = S7Client(address="127.0.0.1", rack=0, slot=1)
client.connect()
```

For PLCsim Advanced, use the configured virtual adapter IP address.
