# Metrics and Telemetry

Comprehensive guide to pyS7's built-in metrics collection system for monitoring PLC communication performance, diagnostics, and health.

## Table of Contents
- [Overview](#overview)
- [Quick Start](#quick-start)
- [Metrics Reference](#metrics-reference)
- [Usage Examples](#usage-examples)
- [Integration Patterns](#integration-patterns)
- [Best Practices](#best-practices)
- [Thread Safety](#thread-safety)

## Overview

pyS7 includes a lightweight, zero-dependency metrics collection system that tracks:

- **Connection status** - Uptime, connection/disconnection counts
- **Operation counts** - Read/write operations, successes, failures
- **Performance metrics** - Average durations, throughput, operations per minute
- **Error tracking** - Error rates, timeout counts, failure analysis

### Key Features

✅ **Property-based API** - Access metrics as simple properties  
✅ **Thread-safe** - Concurrent access protected by locks  
✅ **Zero dependencies** - Pure Python implementation  
✅ **Optional** - Enable/disable via parameter (enabled by default)  
✅ **Export-friendly** - Convert to dict for logging/monitoring systems  
✅ **Home Assistant ready** - Direct integration with HA sensors  

## Quick Start

### Basic Usage

```python
from pyS7 import S7Client

# Metrics enabled by default
client = S7Client("192.168.1.10", 0, 1)
client.connect()

# Perform some operations
client.read(["DB1,I0", "DB1,R4"])
client.write(["DB1,I0"], [100])

# Access metrics
print(f"Connected: {client.metrics.connected}")
print(f"Uptime: {client.metrics.connection_uptime:.1f} seconds")
print(f"Total operations: {client.metrics.total_operations}")
print(f"Success rate: {client.metrics.success_rate}%")
print(f"Avg read time: {client.metrics.avg_read_duration*1000:.1f}ms")
```

### Disable Metrics

```python
# Disable metrics collection (saves minimal overhead)
client = S7Client("192.168.1.10", 0, 1, enable_metrics=False)
# client.metrics will be None
```

## Metrics Reference

### Connection Metrics

| Property | Type | Description |
|----------|------|-------------|
| `connected` | `bool` | Current connection status |
| `connection_start_time` | `float` | Timestamp when connected (or None) |
| `connection_count` | `int` | Total successful connections |
| `disconnection_count` | `int` | Total disconnections |
| `connection_uptime` | `float` | Seconds since connection (0 if disconnected) |

**Example:**
```python
if client.metrics.connected:
    print(f"Connected for {client.metrics.connection_uptime:.1f}s")
    print(f"Reconnections: {client.metrics.connection_count - 1}")
```

### Operation Metrics

| Property | Type | Description |
|----------|------|-------------|
| `read_count` | `int` | Total read operations attempted |
| `write_count` | `int` | Total write operations attempted |
| `total_operations` | `int` | Sum of read + write operations |
| `read_errors` | `int` | Failed read operations |
| `write_errors` | `int` | Failed write operations |
| `timeout_errors` | `int` | Operations that timed out |
| `total_errors` | `int` | Sum of all errors |

**Example:**
```python
print(f"Operations: {client.metrics.total_operations}")
print(f"Reads: {client.metrics.read_count} ({client.metrics.read_errors} errors)")
print(f"Writes: {client.metrics.write_count} ({client.metrics.write_errors} errors)")
```

### Performance Metrics

| Property | Type | Description |
|----------|------|-------------|
| `last_read_duration` | `float` | Duration of last read (seconds) |
| `last_write_duration` | `float` | Duration of last write (seconds) |
| `avg_read_duration` | `float` | Average read duration (seconds) |
| `avg_write_duration` | `float` | Average write duration (seconds) |
| `operations_per_minute` | `float` | Operations/minute since connection |

**Example:**
```python
print(f"Avg read: {client.metrics.avg_read_duration*1000:.1f}ms")
print(f"Avg write: {client.metrics.avg_write_duration*1000:.1f}ms")
print(f"Throughput: {client.metrics.operations_per_minute:.1f} ops/min")
```

### Data Transfer Metrics

| Property | Type | Description |
|----------|------|-------------|
| `total_bytes_read` | `int` | Total bytes read from PLC |
| `total_bytes_written` | `int` | Total bytes written to PLC |
| `avg_bytes_per_read` | `float` | Average bytes per read operation |
| `avg_bytes_per_write` | `float` | Average bytes per write operation |

**Example:**
```python
total_mb = (client.metrics.total_bytes_read + client.metrics.total_bytes_written) / 1_000_000
print(f"Total data transferred: {total_mb:.2f} MB")
print(f"Avg read size: {client.metrics.avg_bytes_per_read:.0f} bytes")
```

### Quality Metrics

| Property | Type | Description |
|----------|------|-------------|
| `error_rate` | `float` | Percentage of failed operations (0-100) |
| `success_rate` | `float` | Percentage of successful operations (0-100) |

**Example:**
```python
if client.metrics.error_rate > 10.0:
    print(f"⚠️ High error rate: {client.metrics.error_rate:.1f}%")
else:
    print(f"✅ Healthy: {client.metrics.success_rate:.1f}% success rate")
```

## Usage Examples

### 1. Real-time Monitoring

```python
import time
from pyS7 import S7Client

client = S7Client("192.168.1.10", 0, 1)
client.connect()

# Monitor loop
while True:
    try:
        data = client.read(["DB1,I0", "DB1,R4"])
        
        # Print metrics every 10 operations
        if client.metrics.total_operations % 10 == 0:
            print(f"\n=== Metrics Report ===")
            print(f"Uptime: {client.metrics.connection_uptime:.1f}s")
            print(f"Operations: {client.metrics.total_operations}")
            print(f"Success rate: {client.metrics.success_rate:.1f}%")
            print(f"Avg read time: {client.metrics.avg_read_duration*1000:.1f}ms")
            print(f"Throughput: {client.metrics.operations_per_minute:.1f} ops/min")
        
        time.sleep(1)
    
    except KeyboardInterrupt:
        break

client.disconnect()
```

### 2. Export to JSON

```python
import json
from pyS7 import S7Client

client = S7Client("192.168.1.10", 0, 1)
client.connect()

# Perform operations
client.read(["DB1,I0"])
client.write(["DB1,I0"], [100])

# Export metrics to JSON
metrics_dict = client.metrics.as_dict()
print(json.dumps(metrics_dict, indent=2))

# Save to file
with open("metrics.json", "w") as f:
    json.dumps(metrics_dict, f, indent=2)
```

### 3. Logging Integration

```python
import logging
from pyS7 import S7Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = S7Client("192.168.1.10", 0, 1)
client.connect()

# Periodic logging
def log_metrics():
    logger.info(
        "PLC Metrics - Uptime: %.1fs, Operations: %d, Success: %.1f%%, "
        "Avg read: %.1fms, Errors: %d",
        client.metrics.connection_uptime,
        client.metrics.total_operations,
        client.metrics.success_rate,
        client.metrics.avg_read_duration * 1000,
        client.metrics.total_errors
    )

# Call periodically
log_metrics()
```

### 4. Health Check

```python
from pyS7 import S7Client

def check_plc_health(client: S7Client) -> bool:
    """Check if PLC connection is healthy."""
    if not client.metrics:
        return True  # Metrics disabled, can't check
    
    metrics = client.metrics
    
    # Check connection
    if not metrics.connected:
        print("❌ Not connected")
        return False
    
    # Check error rate (allow up to 5%)
    if metrics.error_rate > 5.0:
        print(f"⚠️ High error rate: {metrics.error_rate:.1f}%")
        return False
    
    # Check response time (under 100ms average)
    avg_duration = (metrics.avg_read_duration + metrics.avg_write_duration) / 2
    if avg_duration > 0.1:
        print(f"⚠️ Slow response: {avg_duration*1000:.1f}ms average")
        return False
    
    print(f"✅ Healthy - {metrics.success_rate:.1f}% success, "
          f"{avg_duration*1000:.1f}ms avg response")
    return True

# Usage
client = S7Client("192.168.1.10", 0, 1)
client.connect()

# ... perform operations ...

if not check_plc_health(client):
    # Handle unhealthy connection
    client.disconnect()
    client.connect()  # Attempt reconnection
```

### 5. Performance Analysis

```python
from pyS7 import S7Client
import time

client = S7Client("192.168.1.10", 0, 1)
client.connect()

# Benchmark read performance
print("Benchmarking read operations...")
start = time.time()

for i in range(100):
    client.read(["DB1,I0", "DB1,R4", "DB1,X0.0"])

duration = time.time() - start

print(f"\n=== Benchmark Results ===")
print(f"Total operations: {client.metrics.read_count}")
print(f"Total time: {duration:.2f}s")
print(f"Operations/sec: {client.metrics.read_count/duration:.1f}")
print(f"Avg duration: {client.metrics.avg_read_duration*1000:.2f}ms")
print(f"Total bytes read: {client.metrics.total_bytes_read}")
print(f"Throughput: {client.metrics.total_bytes_read/duration:.1f} bytes/sec")
```

### 6. Reset Metrics

```python
from pyS7 import S7Client

client = S7Client("192.168.1.10", 0, 1)
client.connect()

# Perform operations
client.read(["DB1,I0"])

# Reset metrics (e.g., after maintenance window)
client.metrics.reset()

# Metrics are cleared
assert client.metrics.total_operations == 0
assert client.metrics.connected is False
```

## Integration Patterns

### Home Assistant Integration

```python
from homeassistant.components.sensor import SensorEntity
from pyS7 import S7Client

class PLCMetricsSensor(SensorEntity):
    """Home Assistant sensor for PLC metrics."""
    
    def __init__(self, client: S7Client, metric_name: str):
        self._client = client
        self._metric_name = metric_name
        self._attr_name = f"PLC {metric_name}"
    
    @property
    def state(self):
        """Return the state of the sensor."""
        if not self._client.metrics:
            return None
        
        metric_map = {
            "uptime": self._client.metrics.connection_uptime,
            "success_rate": self._client.metrics.success_rate,
            "error_rate": self._client.metrics.error_rate,
            "operations": self._client.metrics.total_operations,
            "avg_read_ms": self._client.metrics.avg_read_duration * 1000,
        }
        
        return metric_map.get(self._metric_name)
    
    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        units = {
            "uptime": "s",
            "success_rate": "%",
            "error_rate": "%",
            "operations": "ops",
            "avg_read_ms": "ms",
        }
        return units.get(self._metric_name)

# Usage in Home Assistant
client = S7Client("192.168.1.10", 0, 1)
sensors = [
    PLCMetricsSensor(client, "uptime"),
    PLCMetricsSensor(client, "success_rate"),
    PLCMetricsSensor(client, "avg_read_ms"),
]
```

### Prometheus Integration

```python
from prometheus_client import Gauge, Counter
from pyS7 import S7Client

# Define Prometheus metrics
plc_uptime = Gauge('plc_connection_uptime_seconds', 'PLC connection uptime')
plc_operations = Counter('plc_operations_total', 'Total PLC operations', ['type'])
plc_errors = Counter('plc_errors_total', 'Total PLC errors', ['type'])
plc_success_rate = Gauge('plc_success_rate_percent', 'PLC operation success rate')
plc_avg_duration = Gauge('plc_operation_duration_seconds', 'Average operation duration', ['type'])

def update_prometheus_metrics(client: S7Client):
    """Update Prometheus metrics from pyS7 client."""
    if not client.metrics:
        return
    
    metrics = client.metrics
    
    # Update gauges
    plc_uptime.set(metrics.connection_uptime)
    plc_success_rate.set(metrics.success_rate)
    plc_avg_duration.labels(type='read').set(metrics.avg_read_duration)
    plc_avg_duration.labels(type='write').set(metrics.avg_write_duration)
    
    # Note: Counters should only increase, so track the delta
    # You'd need to store previous values and update with the difference

# Call periodically
client = S7Client("192.168.1.10", 0, 1)
client.connect()

# In your monitoring loop
update_prometheus_metrics(client)
```

### Grafana Dashboard

Example metrics query for visualization:

```python
# Export metrics periodically to time-series database
import time
from pyS7 import S7Client

client = S7Client("192.168.1.10", 0, 1)
client.connect()

while True:
    metrics = client.metrics.as_dict()
    
    # Add timestamp
    metrics['timestamp'] = time.time()
    
    # Send to your time-series DB (InfluxDB, TimescaleDB, etc.)
    # influxdb_client.write_point("plc_metrics", metrics)
    
    time.sleep(10)  # Collect every 10 seconds
```

## Best Practices

### 1. Monitor Key Metrics

Focus on metrics that indicate health and performance:

```python
def get_health_summary(client: S7Client) -> dict:
    """Get key health indicators."""
    m = client.metrics
    
    return {
        "connected": m.connected,
        "uptime_minutes": m.connection_uptime / 60,
        "success_rate": m.success_rate,
        "avg_response_ms": (m.avg_read_duration + m.avg_write_duration) * 500,
        "operations_per_min": m.operations_per_minute,
        "total_errors": m.total_errors,
    }
```

### 2. Set Alerting Thresholds

Define thresholds for automated alerting:

```python
THRESHOLDS = {
    "min_success_rate": 95.0,  # Alert if below 95%
    "max_error_rate": 5.0,      # Alert if above 5%
    "max_avg_duration": 0.1,    # Alert if above 100ms
    "max_timeout_rate": 1.0,    # Alert if timeouts > 1%
}

def check_thresholds(metrics, thresholds):
    """Check if any thresholds are exceeded."""
    alerts = []
    
    if metrics.success_rate < thresholds["min_success_rate"]:
        alerts.append(f"Low success rate: {metrics.success_rate:.1f}%")
    
    if metrics.error_rate > thresholds["max_error_rate"]:
        alerts.append(f"High error rate: {metrics.error_rate:.1f}%")
    
    avg_duration = (metrics.avg_read_duration + metrics.avg_write_duration) / 2
    if avg_duration > thresholds["max_avg_duration"]:
        alerts.append(f"Slow response: {avg_duration*1000:.1f}ms")
    
    return alerts
```

### 3. Periodic Reporting

Generate periodic reports for analysis:

```python
import time
from datetime import datetime

def generate_report(client: S7Client, filename: str):
    """Generate metrics report."""
    m = client.metrics
    
    report = f"""
    PLC Metrics Report
    Generated: {datetime.now().isoformat()}
    
    Connection:
    - Status: {'Connected' if m.connected else 'Disconnected'}
    - Uptime: {m.connection_uptime:.1f}s
    - Connections: {m.connection_count}
    - Disconnections: {m.disconnection_count}
    
    Operations:
    - Total: {m.total_operations}
    - Reads: {m.read_count} ({m.read_errors} errors)
    - Writes: {m.write_count} ({m.write_errors} errors)
    - Timeouts: {m.timeout_errors}
    
    Performance:
    - Success rate: {m.success_rate:.2f}%
    - Error rate: {m.error_rate:.2f}%
    - Avg read time: {m.avg_read_duration*1000:.2f}ms
    - Avg write time: {m.avg_write_duration*1000:.2f}ms
    - Throughput: {m.operations_per_minute:.1f} ops/min
    
    Data Transfer:
    - Bytes read: {m.total_bytes_read:,}
    - Bytes written: {m.total_bytes_written:,}
    - Avg read size: {m.avg_bytes_per_read:.0f} bytes
    - Avg write size: {m.avg_bytes_per_write:.0f} bytes
    """
    
    with open(filename, 'w') as f:
        f.write(report)
    
    print(f"Report saved to {filename}")
```

### 4. Disable When Not Needed

For maximum performance where metrics aren't needed:

```python
# Production environment without monitoring
client = S7Client("192.168.1.10", 0, 1, enable_metrics=False)

# Development/testing with metrics
client = S7Client("192.168.1.10", 0, 1, enable_metrics=True)
```

## Thread Safety

All metrics operations are thread-safe and can be accessed from multiple threads:

```python
import threading
from pyS7 import S7Client

client = S7Client("192.168.1.10", 0, 1)
client.connect()

def worker():
    """Worker thread performing operations."""
    for _ in range(100):
        client.read(["DB1,I0"])

def monitor():
    """Monitor thread reading metrics."""
    while True:
        print(f"Operations: {client.metrics.total_operations}")
        time.sleep(1)

# Safe to run concurrently
t1 = threading.Thread(target=worker)
t2 = threading.Thread(target=monitor)

t1.start()
t2.start()
```

Internal locking ensures:
- ✅ Safe concurrent reads from multiple threads
- ✅ Safe concurrent writes (operations) from multiple threads
- ✅ Consistent snapshots when calling `as_dict()`
- ✅ No data races or corruption

## See Also

- [API Reference](API_REFERENCE.md) - Complete API documentation
- [Best Practices](BEST_PRACTICES.md) - Development guidelines
- [Examples](../examples/metrics_demo.py) - Complete usage examples
- [Home Assistant Integration](../examples/homeassistant_metrics_integration.py) - HA sensor patterns
