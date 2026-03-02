"""Metrics collection for S7Client performance and diagnostics monitoring.

This module provides lightweight metrics tracking for S7 PLC communication,
enabling monitoring of connection status, operation counts, performance,
and error rates without external dependencies.
"""

from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any, Dict, Optional


@dataclass
class ClientMetrics:
    """Metrics collector for S7Client operations.
    
    Tracks connection status, operation counts, performance metrics, and errors.
    All operations are thread-safe. Metrics can be read as properties or exported
    as a dictionary for integration with monitoring systems.
    
    Attributes:
        connected: Current connection status
        connection_start_time: Timestamp when connection was established
        connection_count: Number of successful connections
        disconnection_count: Number of disconnections
        read_count: Total number of read operations
        write_count: Total number of write operations
        read_errors: Number of failed read operations
        write_errors: Number of failed write operations
        timeout_errors: Number of timeout errors
        last_read_duration: Duration of last read operation (seconds)
        last_write_duration: Duration of last write operation (seconds)
        total_read_duration: Cumulative read operation time (seconds)
        total_write_duration: Cumulative write operation time (seconds)
        total_bytes_read: Total bytes read from PLC
        total_bytes_written: Total bytes written to PLC
    
    Example:
        >>> from pyS7 import S7Client
        >>> client = S7Client("192.168.5.100", 0, 1, enable_metrics=True)
        >>> client.connect()
        >>> client.read(["DB1,I0"])
        >>> print(f"Read count: {client.metrics.read_count}")
        >>> print(f"Avg latency: {client.metrics.avg_read_duration * 1000:.2f} ms")
        >>> print(f"Uptime: {client.metrics.connection_uptime / 3600:.2f} hours")
    """
    
    # Connection metrics
    connected: bool = False
    connection_start_time: Optional[float] = None
    connection_count: int = 0
    disconnection_count: int = 0
    
    # Operation counters
    read_count: int = 0
    write_count: int = 0
    read_errors: int = 0
    write_errors: int = 0
    timeout_errors: int = 0
    
    # Performance metrics
    last_read_duration: float = 0.0
    last_write_duration: float = 0.0
    total_read_duration: float = 0.0
    total_write_duration: float = 0.0
    
    # Bandwidth metrics
    total_bytes_read: int = 0
    total_bytes_written: int = 0
    
    # Thread-safe lock (not included in dataclass fields)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)
    
    @property
    def connection_uptime(self) -> float:
        """Return connection uptime in seconds.
        
        Returns 0.0 if not currently connected.
        
        Returns:
            float: Uptime in seconds since last connection
        """
        if not self.connected or self.connection_start_time is None:
            return 0.0
        return time() - self.connection_start_time
    
    @property
    def avg_read_duration(self) -> float:
        """Return average read operation duration in seconds.
        
        Returns 0.0 if no reads have been performed.
        
        Returns:
            float: Average duration in seconds
        """
        if self.read_count == 0:
            return 0.0
        return self.total_read_duration / self.read_count
    
    @property
    def avg_write_duration(self) -> float:
        """Return average write operation duration in seconds.
        
        Returns 0.0 if no writes have been performed.
        
        Returns:
            float: Average duration in seconds
        """
        if self.write_count == 0:
            return 0.0
        return self.total_write_duration / self.write_count
    
    @property
    def total_operations(self) -> int:
        """Return total number of operations (reads + writes).
        
        Returns:
            int: Total operation count
        """
        return self.read_count + self.write_count
    
    @property
    def total_errors(self) -> int:
        """Return total number of errors across all operation types.
        
        Returns:
            int: Total error count
        """
        return self.read_errors + self.write_errors + self.timeout_errors
    
    @property
    def error_rate(self) -> float:
        """Return error rate as a percentage.
        
        Calculated as (total_errors / total_operations) * 100.
        Returns 0.0 if no operations have been performed.
        
        Returns:
            float: Error rate percentage (0.0 to 100.0)
        """
        total_ops = self.total_operations
        if total_ops == 0:
            return 0.0
        return (self.total_errors / total_ops) * 100
    
    @property
    def success_rate(self) -> float:
        """Return success rate as a percentage.
        
        Calculated as 100.0 - error_rate.
        Returns 100.0 if no operations have been performed.
        
        Returns:
            float: Success rate percentage (0.0 to 100.0)
        """
        return 100.0 - self.error_rate
    
    @property
    def operations_per_minute(self) -> float:
        """Return operations per minute since connection.
        
        Returns 0.0 if not currently connected or uptime is 0.
        
        Returns:
            float: Operations per minute
        """
        uptime = self.connection_uptime
        if uptime == 0:
            return 0.0
        return (self.total_operations / uptime) * 60
    
    @property
    def avg_bytes_per_read(self) -> float:
        """Return average bytes per read operation.
        
        Returns 0.0 if no reads have been performed.
        
        Returns:
            float: Average bytes per read
        """
        if self.read_count == 0:
            return 0.0
        return self.total_bytes_read / self.read_count
    
    @property
    def avg_bytes_per_write(self) -> float:
        """Return average bytes per write operation.
        
        Returns 0.0 if no writes have been performed.
        
        Returns:
            float: Average bytes per write
        """
        if self.write_count == 0:
            return 0.0
        return self.total_bytes_written / self.write_count
    
    def record_connection(self) -> None:
        """Record a successful connection.
        
        Thread-safe. Updates connection status, timestamp, and counter.
        """
        with self._lock:
            self.connected = True
            self.connection_start_time = time()
            self.connection_count += 1
    
    def record_disconnection(self) -> None:
        """Record a disconnection.
        
        Thread-safe. Updates connection status and counter.
        """
        with self._lock:
            self.connected = False
            self.connection_start_time = None
            self.disconnection_count += 1
    
    def record_read(
        self,
        duration: float,
        bytes_read: int = 0,
        success: bool = True
    ) -> None:
        """Record a read operation.
        
        Thread-safe. Updates read counters, duration, and bandwidth metrics.
        
        Args:
            duration: Operation duration in seconds
            bytes_read: Number of bytes read (default: 0)
            success: Whether operation succeeded (default: True)
        """
        with self._lock:
            self.read_count += 1
            self.last_read_duration = duration
            self.total_read_duration += duration
            self.total_bytes_read += bytes_read
            if not success:
                self.read_errors += 1
    
    def record_write(
        self,
        duration: float,
        bytes_written: int = 0,
        success: bool = True
    ) -> None:
        """Record a write operation.
        
        Thread-safe. Updates write counters, duration, and bandwidth metrics.
        
        Args:
            duration: Operation duration in seconds
            bytes_written: Number of bytes written (default: 0)
            success: Whether operation succeeded (default: True)
        """
        with self._lock:
            self.write_count += 1
            self.last_write_duration = duration
            self.total_write_duration += duration
            self.total_bytes_written += bytes_written
            if not success:
                self.write_errors += 1
    
    def record_timeout(self) -> None:
        """Record a timeout error.
        
        Thread-safe. Increments timeout error counter.
        """
        with self._lock:
            self.timeout_errors += 1
    
    def reset(self) -> None:
        """Reset all metrics to initial state.
        
        Thread-safe. Clears all counters and state.
        """
        with self._lock:
            self.connected = False
            self.connection_start_time = None
            self.connection_count = 0
            self.disconnection_count = 0
            self.read_count = 0
            self.write_count = 0
            self.read_errors = 0
            self.write_errors = 0
            self.timeout_errors = 0
            self.last_read_duration = 0.0
            self.last_write_duration = 0.0
            self.total_read_duration = 0.0
            self.total_write_duration = 0.0
            self.total_bytes_read = 0
            self.total_bytes_written = 0
    
    def as_dict(self) -> Dict[str, Any]:
        """Export all metrics as a dictionary.
        
        Thread-safe. Includes all base metrics and computed properties.
        Useful for logging, serialization, or integration with monitoring systems.
        
        Returns:
            dict: Dictionary containing all metric values
            
        Example:
            >>> metrics_dict = client.metrics.as_dict()
            >>> print(json.dumps(metrics_dict, indent=2))
            >>> logger.info("Metrics: %s", metrics_dict)
        """
        with self._lock:
            return {
                # Connection metrics
                'connected': self.connected,
                'connection_uptime': self.connection_uptime,
                'connection_count': self.connection_count,
                'disconnection_count': self.disconnection_count,
                
                # Operation counters
                'read_count': self.read_count,
                'write_count': self.write_count,
                'total_operations': self.total_operations,
                
                # Error metrics
                'read_errors': self.read_errors,
                'write_errors': self.write_errors,
                'timeout_errors': self.timeout_errors,
                'total_errors': self.total_errors,
                'error_rate': self.error_rate,
                'success_rate': self.success_rate,
                
                # Performance metrics
                'last_read_duration': self.last_read_duration,
                'last_write_duration': self.last_write_duration,
                'avg_read_duration': self.avg_read_duration,
                'avg_write_duration': self.avg_write_duration,
                'operations_per_minute': self.operations_per_minute,
                
                # Bandwidth metrics
                'total_bytes_read': self.total_bytes_read,
                'total_bytes_written': self.total_bytes_written,
                'avg_bytes_per_read': self.avg_bytes_per_read,
                'avg_bytes_per_write': self.avg_bytes_per_write,
            }
    
    def __str__(self) -> str:
        """Return human-readable string representation of metrics.
        
        Returns:
            str: Formatted metrics summary
        """
        status = "Connected" if self.connected else "Disconnected"
        uptime_hours = self.connection_uptime / 3600
        
        return (
            f"S7Client Metrics:\n"
            f"  Status: {status}\n"
            f"  Uptime: {uptime_hours:.2f} hours\n"
            f"  Operations: {self.total_operations} ({self.read_count} reads, {self.write_count} writes)\n"
            f"  Errors: {self.total_errors} ({self.error_rate:.2f}% error rate)\n"
            f"  Avg Read Latency: {self.avg_read_duration * 1000:.2f} ms\n"
            f"  Avg Write Latency: {self.avg_write_duration * 1000:.2f} ms\n"
            f"  Operations/min: {self.operations_per_minute:.1f}\n"
            f"  Data: {self.total_bytes_read} bytes read, {self.total_bytes_written} bytes written"
        )
