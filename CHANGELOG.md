# Changelog

All notable changes to pyS7 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.0] - 2026-03-26

### Added
- **AsyncS7Client** – Full asyncio-based S7 PLC client for non-blocking I/O
  - Drop-in async replacement for `S7Client` with identical API
  - Async context manager (`async with AsyncS7Client(...) as client`)
  - `await client.read()` / `await client.write()` – async tag read/write
  - `await client.read_detailed()` / `await client.write_detailed()` – async per-tag error handling
  - `await client.get_cpu_status()` / `await client.get_cpu_info()` – async CPU diagnostics
  - Internal `asyncio.Lock` serialises concurrent coroutines sharing a single client
  - Automatic large STRING/WSTRING chunking (same as sync client)
  - Full metrics integration (`enable_metrics` parameter)
  - Connection state management with `ConnectionState` enum
- **AsyncBatchWriteTransaction** – Async batch write with automatic rollback
  - `async with client.batch_write() as batch` context manager
  - `batch.add(tag, value)` with method chaining
  - `await batch.commit()` / `await batch.rollback()`
  - Automatic rollback on error (configurable)
- New example: `examples/async_client_demo.py`
- Test suite for async client: 331 lines covering all async operations

### Changed
- `__init__.py` now exports `AsyncS7Client` and `AsyncBatchWriteTransaction`

### Migration Guide

**Using AsyncS7Client:**
```python
import asyncio
from pyS7 import AsyncS7Client

async def main():
    async with AsyncS7Client('192.168.0.1', 0, 1) as client:
        values = await client.read(['DB1,I0', 'DB1,R4'])
        print(values)

asyncio.run(main())
```

**No Breaking Changes** – Existing synchronous code continues to work without modification.

## [2.6.0] - 2026-03-03

### Added
- **Metrics and Telemetry System** – Built-in performance monitoring and diagnostics
  - `ClientMetrics` class with 15 computed properties
  - Connection metrics: uptime, connection/disconnection counts
  - Operation metrics: read/write counts, success/failure tracking
  - Performance metrics: average durations, operations per minute, throughput
  - Data transfer metrics: bytes read/written, average sizes
  - Quality metrics: error rate, success rate
  - Thread-safe implementation with `threading.Lock`
  - Property-based API for easy access
  - Export to dictionary for logging and monitoring systems
  - Zero external dependencies
  - Enabled by default via `enable_metrics` parameter
  - Minimal performance overhead (< 0.1%)
- Data type support for SINT and USINT:
  - `SINT`: Signed 8-bit integer (-128 to 127)
  - `USINT`: Unsigned 8-bit integer (0 to 255)
  - Address format: `DB1,SINT20` or `DB1,USINT21`
  - Alias support: `SI` for SINT, `USI` for USINT
- Comprehensive documentation:
  - `METRICS.md`: Complete metrics guide with integration examples
  - Updated `API_REFERENCE.md` with ClientMetrics documentation
  - Updated `README.md` with metrics quick start
- New example files:
  - `examples/metrics_demo.py`: 7 comprehensive usage examples
  - `examples/homeassistant_metrics_integration.py`: Home Assistant integration patterns
- Test coverage:
  - 26 new metrics tests (100% coverage on metrics module)
  - All 281 tests passing
  - Overall coverage maintained at 85%

### Changed
- `S7Client.__init__()` now accepts `enable_metrics: bool = True` parameter
- `S7Client` now has `metrics: Optional[ClientMetrics]` attribute
- Automatic metrics tracking in `connect()`, `disconnect()`, `read()`, `write()`
- Updated documentation for SINT/USINT in README, API_REFERENCE, and examples

### Integration Support
- **Home Assistant**: Direct property access for sensor creation
- **Prometheus**: Gauge/Counter mapping examples
- **Grafana**: Time-series export patterns
- **General logging**: JSON export via `as_dict()`

### Use Cases
- Real-time performance monitoring
- Health checks and alerting
- Diagnostics and troubleshooting
- Production system observability
- Home automation integration
- Performance benchmarking

### Migration Guide

**Enable/Disable Metrics:**
```python
# Metrics enabled by default (recommended)
client = S7Client("192.168.1.10", 0, 1)
print(client.metrics.success_rate)

# Disable for absolute maximum performance
client = S7Client("192.168.1.10", 0, 1, enable_metrics=False)
# client.metrics will be None
```

**Access Metrics:**
```python
# Property access
uptime = client.metrics.connection_uptime
success_rate = client.metrics.success_rate

# Export to dict
metrics_dict = client.metrics.as_dict()

# Reset metrics
client.metrics.reset()
```

**No Breaking Changes** – Existing code continues to work without modification.

## [2.5.0] - 2026-01-23

### Added
- Comprehensive edge case test suite (33 new tests covering boundary conditions)
- Performance benchmark suite with cProfile integration
- Extensive documentation:
  - `PERFORMANCE_ANALYSIS.md`: Detailed profiling and bottleneck analysis
  - `OPTIMIZATION_RESULTS.md`: Before/after optimization comparison
  - `BEST_PRACTICES.md`: Development guidelines
  - `TROUBLESHOOTING_BIT_READ.md`: BIT read workarounds
  - `CPU_STATUS_READING.md`: CPU status documentation

### Changed
- **BREAKING**: Removed all `logger.info()` calls, replaced with `logger.debug()` for cleaner production logs
- Optimized import structure: moved 5 local imports to module level
- Replaced 9 assert statements with explicit validation and proper error messages
- Improved type hints: eliminated all `# type: ignore` comments
- Enhanced error handling with specific exception types:
  - `S7TimeoutError`: For connection/read/write timeouts
  - `S7ProtocolError`: For protocol-level errors
  - `S7PDUError`: For PDU size violations

### Performance
- **+90% average performance improvement** across critical operations
- Tag size calculation: **+155% faster** (0.022s → 0.009s)
- Multiple requests preparation: **+100% faster** (0.103s → 0.051s)
- Single request preparation: **+128% faster** (0.003s → 0.001s)
- Write requests preparation: **+55% faster** (0.037s → 0.024s)
- Function calls reduced by 33-62% in hot paths

### Performance Optimizations
- Pre-computed size lookup table (`_SIZE_CALCULATOR`) eliminates if/elif chain
- Cached `tag.size()` results for immutable tags
- Reduced duplicate `size()` calls in request preparation (from 100k to 50k for 50 tags)
- Removed enum hashing overhead (60% fewer function calls in size calculation)

### Improved
- Extracted 24 magic numbers into named constants in `constants.py`
- Reduced code duplication:
  - 3 new packing helper functions (`_pack_int16`, `_pack_uint16`, `_pack_int32`)
  - Eliminated ~70 lines of duplicate code
- Split large functions into smaller, focused helpers:
  - 6 new helper functions in `client.py`
  - Simplified ~200 lines of complex logic
- Added comprehensive docstrings to all helper functions
- Enhanced logging with structured context (tag details, operation context)
- Test coverage increased from 85% to 86%

### Fixed
- Improved validation error messages with clear context
- Better error handling for edge cases
- More robust boundary condition handling

### Technical Debt Reduction
- Improved code organization and readability
- Better separation of concerns
- Enhanced maintainability through helper functions
- Reduced cyclomatic complexity in large functions

### Developer Experience
- All 187 tests passing (154 existing + 33 new edge cases)
- Mypy strict mode compliance maintained
- Zero breaking changes to public API
- Backward compatible with existing code

## [2.4.0] - Previous Release

### Features
- (Previous features documented here)

---

## Migration Guide 2.4.0 → 2.5.0

### Logging Changes

If you were relying on INFO-level logs, you'll need to adjust your logging configuration:

**Before:**
```python
logging.basicConfig(level=logging.INFO)
# Would see connection and operation logs
```

**After:**
```python
logging.basicConfig(level=logging.DEBUG)
# Now use DEBUG level for operational logs
```

**Rationale:** Production applications typically want minimal logging. Use DEBUG for development/troubleshooting.

### No Other Breaking Changes

All other changes are internal optimizations and improvements. Your existing code will work without modifications.

### Performance Benefits

Your application will automatically benefit from:
- 2x faster request preparation for multi-tag operations
- 50% reduction in latency for prepare_requests operations
- Reduced CPU usage due to optimized hot paths

No code changes needed to gain these benefits!

---

## Contributing

See development documentation in `docs/` for best practices and guidelines.
