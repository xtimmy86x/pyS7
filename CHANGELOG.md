# Changelog

All notable changes to pyS7 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
