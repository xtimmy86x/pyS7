<div align="center">

# pyS7

<br/>

pyS7 is a lightweight, pure Python library that implements the Siemens S7 communication protocol over ISO-on-TCP (RFC1006). It enables direct communication with Siemens S7-200, S7-300, S7-400, S7-1200, and S7-1500 PLCs from Python applications.

**Production/Stable** • **2x Performance** • **Fully Tested**

> ⚠️ Neither this project nor its authors are affiliated with Siemens. S7-200, S7-300, S7-400, S7-1200, and S7-1500 are registered trademarks of Siemens AG.

</div>

<img src="docs/banner.png" alt="ha-s7plc banner" width="100%"/>

## Features

- **Pure Python** – No external dependencies, easy installation across platforms
- **Intuitive API** – Clean, readable code with full typing support for IDE assistance
- **Async Support** – Full asyncio client (`AsyncS7Client`) for non-blocking I/O
- **High Performance** – Optimized hot paths, 2x faster request preparation (v2.5.0)
- **Graceful error handling** – read_detailed() and write_detailed() provide per-tag success/failure info
- **Transactional writes** – Batch write with automatic rollback on read verification failure
- **Optimized multi-variable reads** – Automatically groups contiguous tags to reduce network requests
- **Automatic chunking** – Transparently splits large STRING/WSTRING reads exceeding PDU size
- **CPU diagnostics** – Read PLC status (RUN/STOP) and information (model, firmware) via SZL protocol
- **Broad compatibility** – Supports S7-200/300/400/1200/1500 series
- **Production Ready** – 253 tests, 85% coverage, strict type checking

## Safety Notice

Industrial safety must always remain your top priority. By using pyS7 you accept full responsibility for any damage, data loss, downtime, or unintended effects. Understand your system and the implications of each operation before interacting with live equipment.

## Installation

Requires Python 3.8 or later.

```bash
pip install pys7
```

Or install from GitHub:

```bash
pip install git+https://github.com/xtimmy86x/pyS7
```

## Quick Start

### Reading data

```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    tags = [
        "DB1,X0.0",     # Bit 0 of DB1
        "DB1,SINT20",   # SINT (signed byte -128 to 127) at byte 20 of DB1
        "DB1,USINT21",  # USINT (unsigned byte 0-255) at byte 21 of DB1
        "DB1,I30",      # INT at byte 30 of DB1
        "M54.4",        # Bit 4 of marker memory
        "IW22",         # WORD at byte 22 of input area
        "QR24",         # REAL at byte 24 of output area
        "DB1,S10.5"     # String of 5 characters at byte 10 of DB1
    ]
    
    data = client.read(tags)
    print(data)  # [True, -50, 200, 123, True, 10, 3.14, 'Hello']
```

### Writing data

```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    tags = ["DB1,X0.0", "DB1,SINT20", "DB1,USINT21", "DB1,I30", "DB1,R40", "DB1,S10.5"]
    values = [True, -50, 200, 25000, 1.2345, "Hello"]
    
    client.write(tags, values)
```

### Graceful error handling

```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    # read_detailed() continues on errors, returns per-tag results
    results = client.read_detailed(["DB1,I0", "DB99,I0", "DB1,R4"])
    
    for result in results:
        if result.success:
            print(f"{result.tag}: {result.value}")
        else:
            print(f"{result.tag} failed: {result.error}")
    
    # write_detailed() provides per-tag success/failure info
    tags = ["DB1,I0", "DB1,I2", "DB99,I0"]
    values = [100, 200, 300]
    write_results = client.write_detailed(tags, values)
    
    for result in write_results:
        if result.success:
            print(f"✓ {result.tag}: Written")
        else:
            print(f"✗ {result.tag}: {result.error}")
```

### Transactional batch writes

```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    # Batch write with automatic rollback on verification failure
    with client.batch_write() as batch:
        batch.add("DB1,I0", 100)
        batch.add("DB1,I2", 200)
        batch.add("DB1,R4", 3.14)
        # Auto-commits on exit, rolls back on error
    
    # Or with explicit control
    batch = client.batch_write(auto_commit=False)
    batch.add("DB1,I0", 100)
    batch.add("DB1,I2", 200)
    
    try:
        batch.commit()  # Write and verify
    except Exception as e:
        batch.rollback()  # Restore original values
        print(f"Write failed: {e}")
```

### Reading CPU status

```python
from pyS7 import S7Client

with S7Client(address="192.168.5.100", rack=0, slot=1) as client:
    # Get CPU status
    status = client.get_cpu_status()
    print(f"CPU Status: {status}")  # "RUN" or "STOP"

    # Get CPU information
    info = client.get_cpu_info()
    print(f"Model: {info['module_type_name']}")
    print(f"Firmware: {info['firmware_version']}")
    print(f"Hardware: {info['hardware_version']}")
```

See [docs/CPU_STATUS_READING.md](docs/CPU_STATUS_READING.md) for details.

### Async client

For asyncio-based applications (SCADA dashboards, IoT, Home Assistant, FastAPI):

```python
import asyncio
from pyS7 import AsyncS7Client

async def main():
    async with AsyncS7Client(address="192.168.5.100", rack=0, slot=1) as client:
        # Read
        values = await client.read(["DB1,I0", "DB1,R4"])
        print(values)

        # Write
        await client.write(["DB1,I0"], [42])

        # Detailed read with per-tag error handling
        results = await client.read_detailed(["DB1,I0", "DB99,I0"])
        for r in results:
            print(f"{r.tag}: {r.value if r.success else r.error}")

        # Async batch write with rollback
        async with client.batch_write() as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)

        # CPU diagnostics
        status = await client.get_cpu_status()
        print(f"CPU: {status}")

asyncio.run(main())
```

See [docs/ADVANCED_USAGE.md](docs/ADVANCED_USAGE.md#async-client) for concurrent patterns and advanced usage.

### String data types

pyS7 supports both ASCII and Unicode strings:

```python
# STRING (ASCII) - All S7 models
tags = ["DB1,S10.20"]  # STRING at byte 10, max 20 chars
data = client.read(tags)
print(data[0])  # "Hello World"

# WSTRING (Unicode) - S7-1200/1500 only
tags = ["DB1,WS100.30"]  # WSTRING at byte 100, max 30 chars
data = client.read(tags)
print(data[0])  # "Hello 世界! 🌍"

# Large strings automatically chunked if exceeding PDU size
tags = ["DB1,S100.254"]  # STRING[254] - handled transparently
data = client.read(tags)  # Complete string returned
```

### Monitoring and Metrics

Built-in metrics collection for monitoring PLC communication performance and diagnostics:

```python
from pyS7 import S7Client

# Metrics enabled by default
client = S7Client(address="192.168.5.100", rack=0, slot=1)
client.connect()

# Perform operations
client.read(["DB1,I0", "DB1,R4"])
client.write(["DB1,I0"], [100])

# Access real-time metrics
print(f"Connected: {client.metrics.connected}")
print(f"Uptime: {client.metrics.connection_uptime:.1f}s")
print(f"Total operations: {client.metrics.total_operations}")
print(f"Success rate: {client.metrics.success_rate}%")
print(f"Error rate: {client.metrics.error_rate}%")
print(f"Avg read time: {client.metrics.avg_read_duration*1000:.1f}ms")
print(f"Throughput: {client.metrics.operations_per_minute:.1f} ops/min")

# Export to dict for logging/monitoring systems
metrics_dict = client.metrics.as_dict()

# Integration with Home Assistant, Prometheus, Grafana, etc.
```

See [docs/METRICS.md](docs/METRICS.md) for complete metrics documentation and integration examples.

## Documentation

### Guides

- **[API Reference](docs/API_REFERENCE.md)** – Data types, address formats, supported operations
- **[Advanced Usage](docs/ADVANCED_USAGE.md)** – TSAP connections, PDU tuning, chunking, async client, multi-threading
- **[Metrics and Telemetry](docs/METRICS.md)** – Performance monitoring, diagnostics, integration patterns
- **[Best Practices](docs/BEST_PRACTICES.md)** – Connection management, error handling, production deployment
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** – Common issues and solutions

### Technical Documentation

- **[CPU Status Reading](docs/CPU_STATUS_READING.md)** – CPU diagnostics details
- **[CPU Info Technical Notes](docs/CPU_INFO_TECHNICAL_NOTES.md)** – CPU information internals
- **[Bit Read Troubleshooting](docs/TROUBLESHOOTING_BIT_READ.md)** – Bit operation guidance

### Quick Links

- [Supported address formats](docs/API_REFERENCE.md#supported-addresses) – Complete address mapping
- [TSAP connection](docs/ADVANCED_USAGE.md#tsap-connection) – Alternative connection method
- [PDU optimization](docs/ADVANCED_USAGE.md#pdu-size-management) – Performance tuning
- [Error handling](docs/BEST_PRACTICES.md#error-handling) – Robust error patterns
- [Connection issues](docs/TROUBLESHOOTING.md#connection-issues) – Can't connect?

## Examples

Example scripts in the [`examples/`](examples/) directory demonstrate:

- `read_data.py` – Basic reading operations
- `write_data.py` – Basic writing operations
- `read_detailed_demo.py` – Graceful error handling for reads
- `write_detailed_demo.py` – Graceful error handling for writes
- `batch_write_demo.py` – Transactional batch writes with rollback
- `metrics_demo.py` – Metrics collection and monitoring
- `get_cpu_status.py` – CPU status monitoring
- `get_cpu_info.py` – CPU information retrieval
- `read_data_tsap.py` – TSAP connection example
- `bit_read_workaround.py` – Bit operations
- `manage_reconnection.py` – Connection handling
- `connection_state_demo.py` – Connection state management
- `async_client_demo.py` – Async client usage with asyncio
- `homeassistant_metrics_integration.py` – Home Assistant integration patterns

## License

This project is distributed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

Special thanks to [filocara](https://github.com/FiloCara) for the original project that inspired this work.
