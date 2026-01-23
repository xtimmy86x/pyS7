"""Performance benchmark for pyS7 operations."""

import cProfile
import pstats
import io
import time
from typing import List, Tuple

from pyS7.tag import S7Tag, MemoryArea, DataType
from pyS7.requests import prepare_requests, prepare_write_requests_and_values
from pyS7.responses import parse_read_response


def benchmark_tag_creation(iterations: int = 10000) -> None:
    """Benchmark S7Tag creation."""
    for _ in range(iterations):
        S7Tag(MemoryArea.DB, 1, DataType.INT, 100, 0, 1)
        S7Tag(MemoryArea.DB, 1, DataType.REAL, 200, 0, 10)
        S7Tag(MemoryArea.DB, 1, DataType.STRING, 300, 0, 50)
        S7Tag(MemoryArea.DB, 1, DataType.BIT, 400, 5, 1)


def benchmark_tag_size_calculation(iterations: int = 10000) -> None:
    """Benchmark tag size() method."""
    tags = [
        S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1),
        S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 10),
        S7Tag(MemoryArea.DB, 1, DataType.STRING, 0, 0, 50),
        S7Tag(MemoryArea.DB, 1, DataType.DINT, 0, 0, 100),
    ]
    
    for _ in range(iterations):
        for tag in tags:
            tag.size()


def benchmark_tag_containment(iterations: int = 10000) -> None:
    """Benchmark tag containment checks."""
    parent = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 100)
    child = S7Tag(MemoryArea.DB, 1, DataType.INT, 10, 0, 1)
    other = S7Tag(MemoryArea.DB, 2, DataType.INT, 10, 0, 1)
    
    for _ in range(iterations):
        _ = child in parent
        _ = other in parent
        _ = parent in child


def benchmark_prepare_single_request(iterations: int = 1000) -> None:
    """Benchmark prepare_requests with single tag."""
    tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
    pdu_size = 480
    
    for _ in range(iterations):
        prepare_requests([tag], pdu_size)


def benchmark_prepare_multiple_requests(iterations: int = 1000) -> None:
    """Benchmark prepare_requests with multiple tags."""
    tags = [
        S7Tag(MemoryArea.DB, 1, DataType.INT, i * 2, 0, 1)
        for i in range(50)
    ]
    pdu_size = 480
    
    for _ in range(iterations):
        prepare_requests(tags, pdu_size)


def benchmark_prepare_write_requests(iterations: int = 1000) -> None:
    """Benchmark prepare_write_requests_and_values."""
    tags = [
        S7Tag(MemoryArea.DB, 1, DataType.INT, i * 2, 0, 1)
        for i in range(20)
    ]
    values = [tuple([100 + i]) for i in range(20)]
    pdu_size = 480
    
    for _ in range(iterations):
        prepare_write_requests_and_values(tags, values, pdu_size)


def benchmark_parse_read_response(iterations: int = 1000) -> None:
    """Benchmark parse_read_response."""
    tags = [
        S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 1),
        S7Tag(MemoryArea.DB, 1, DataType.BYTE, 1, 0, 1),
        S7Tag(MemoryArea.DB, 1, DataType.BYTE, 2, 0, 1),
    ]
    
    # Valid response with 3 BYTE values (return_code 0xFF = success)
    response = (
        b"\x03\x00\x00\x24"  # TPKT: length=36
        b"\x02\xf0\x80"      # COTP
        b"\x32\x03\x00\x00"  # S7 header
        b"\x00\x00"
        b"\x00\x02"          # Parameter length
        b"\x00\x0f"          # Data length = 15 (3*5)
        b"\x00\x03"          # Parameter: item_count=3
        # Tag 1 data
        b"\xff"              # return_code (0xFF = SUCCESS)
        b"\x04\x00\x08"      # transport_size=BYTE, length=8 bits
        b"\x42"              # data: BYTE = 0x42
        # Tag 2 data
        b"\xff"              # return_code (SUCCESS)
        b"\x04\x00\x08"      # transport_size, length=8 bits
        b"\x55"              # data: BYTE = 0x55
        # Tag 3 data
        b"\xff"              # return_code (SUCCESS)
        b"\x04\x00\x08"      # transport_size, length=8 bits
        b"\xaa"              # data: BYTE = 0xAA
    )
    
    for _ in range(iterations):
        parse_read_response(response, tags)


def benchmark_large_array_operations(iterations: int = 100) -> None:
    """Benchmark operations with large arrays."""
    # Large REAL array
    tag = S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 500)
    pdu_size = 480
    
    for _ in range(iterations):
        prepare_requests([tag], pdu_size)


def run_benchmark(name: str, func, *args) -> Tuple[float, pstats.Stats]:
    """Run a benchmark function with profiling."""
    print(f"\n{'='*60}")
    print(f"Benchmark: {name}")
    print(f"{'='*60}")
    
    # Profile the function
    profiler = cProfile.Profile()
    profiler.enable()
    
    start = time.perf_counter()
    func(*args)
    elapsed = time.perf_counter() - start
    
    profiler.disable()
    
    # Get stats
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.strip_dirs()
    stats.sort_stats('cumulative')
    stats.print_stats(15)  # Top 15 functions
    
    print(f"\nTotal time: {elapsed:.4f}s")
    print(f"Operations per second: {args[0]/elapsed:.0f}" if args else "")
    print(s.getvalue())
    
    return elapsed, stats


def main() -> None:
    """Run all benchmarks."""
    print("="*60)
    print("pyS7 Performance Benchmark")
    print("="*60)
    
    results = {}
    
    # Tag operations
    results['tag_creation'] = run_benchmark(
        "Tag Creation (10k iterations)",
        benchmark_tag_creation,
        10000
    )
    
    results['tag_size'] = run_benchmark(
        "Tag Size Calculation (10k iterations)",
        benchmark_tag_size_calculation,
        10000
    )
    
    results['tag_containment'] = run_benchmark(
        "Tag Containment Checks (10k iterations)",
        benchmark_tag_containment,
        10000
    )
    
    # Request preparation
    results['single_request'] = run_benchmark(
        "Prepare Single Request (1k iterations)",
        benchmark_prepare_single_request,
        1000
    )
    
    results['multiple_requests'] = run_benchmark(
        "Prepare Multiple Requests (1k iterations)",
        benchmark_prepare_multiple_requests,
        1000
    )
    
    results['write_requests'] = run_benchmark(
        "Prepare Write Requests (1k iterations)",
        benchmark_prepare_write_requests,
        1000
    )
    
    # Response parsing
    # results['parse_response'] = run_benchmark(
    #     "Parse Read Response (1k iterations)",
    #     benchmark_parse_read_response,
    #     1000
    # )
    
    # Large arrays - disabled, PDU too small for 500 REALs
    # results['large_arrays'] = run_benchmark(
    #     "Large Array Operations (100 iterations)",
    #     benchmark_large_array_operations,
    #     100
    # )
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, (elapsed, _) in results.items():
        print(f"{name:30s}: {elapsed:8.4f}s")
    
    print("\n" + "="*60)
    print("BOTTLENECK ANALYSIS")
    print("="*60)
    print("\nCheck the detailed profiling output above to identify:")
    print("- Functions with highest cumulative time")
    print("- Functions called most frequently")
    print("- Potential optimization opportunities")


if __name__ == "__main__":
    main()
