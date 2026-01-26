import logging
import socket
import struct
import threading
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Dict, List, Optional, Sequence, Type, Union, cast

from .address_parser import map_address_to_tag
from .constants import (
    COTP_SIZE,
    MAX_JOB_CALLED,
    MAX_JOB_CALLING,
    MAX_PDU,
    MAX_PDU_SIZE,
    MIN_PDU_SIZE,
    RECOMMENDED_MIN_PDU,
    TPKT_SIZE,
    ConnectionState,
    ConnectionType,
    DataType,
    READ_RES_OVERHEAD,
    READ_RES_PARAM_SIZE_TAG,
    SZLId,
    WRITE_REQ_OVERHEAD,
    WRITE_REQ_PARAM_SIZE_TAG,
)
from .errors import (
    S7AddressError,
    S7CommunicationError,
    S7ConnectionError,
    S7ProtocolError,
    S7TimeoutError,
)
from .requests import (
    ConnectionRequest,
    PDUNegotiationRequest,
    ReadRequest,
    Request,
    SZLRequest,
    Value,
    WriteRequest,
    prepare_optimized_requests,
    prepare_requests,
    prepare_write_requests_and_values,
)
from .responses import (
    ConnectionResponse,
    PDUNegotiationResponse,
    ReadOptimizedResponse,
    ReadResponse,
    SZLResponse,
    WriteResponse,
)
from .tag import S7Tag


@dataclass
class WriteResult:
    """Result of a single write operation.
    
    Attributes:
        tag: The S7Tag that was written
        success: True if write succeeded, False if failed
        error: Error message if write failed, None if succeeded
        error_code: PLC return code if available
    """
    tag: S7Tag
    success: bool
    error: Optional[str] = None
    error_code: Optional[int] = None


@dataclass
class ReadResult:
    """Result of a single read operation.
    
    Attributes:
        tag: The S7Tag that was read
        success: True if read succeeded, False if failed
        value: The value read from PLC if successful, None if failed
        error: Error message if read failed, None if succeeded
        error_code: PLC return code if available
    """
    tag: S7Tag
    success: bool
    value: Optional[Value] = None
    error: Optional[str] = None
    error_code: Optional[int] = None


@dataclass
class BatchWriteTransaction:
    """Batch write transaction for atomic multi-tag writes.
    
    Allows grouping multiple write operations into a single transaction
    with rollback support if any write fails.
    
    Attributes:
        tags: List of tags to write
        values: List of values to write
        auto_commit: If True, commit automatically on __exit__. Default True.
        rollback_on_error: If True, rollback on any error. Default True.
    
    Example:
        >>> with client.batch_write() as batch:
        ...     batch.add('DB1,I0', 100)
        ...     batch.add('DB1,I2', 200)
        ...     # Commits automatically on context exit
    """
    _client: 'S7Client'
    _tags: List[Union[str, S7Tag]]
    _values: List[Value]
    _original_values: Optional[List[Any]]
    auto_commit: bool = True
    rollback_on_error: bool = True
    
    def __init__(
        self,
        client: 'S7Client',
        auto_commit: bool = True,
        rollback_on_error: bool = True
    ):
        """Initialize batch write transaction."""
        self._client = client
        self._tags = []
        self._values = []
        self._original_values = None
        self.auto_commit = auto_commit
        self.rollback_on_error = rollback_on_error
    
    def add(self, tag: Union[str, S7Tag], value: Value) -> 'BatchWriteTransaction':
        """Add a tag/value pair to the batch.
        
        Args:
            tag: Tag address string or S7Tag object
            value: Value to write
            
        Returns:
            Self for method chaining
        """
        self._tags.append(tag)
        self._values.append(value)
        return self
    
    def commit(self) -> List[WriteResult]:
        """Execute all writes in the batch.
        
        Returns:
            List of WriteResult objects for each write operation
            
        Raises:
            ValueError: If no tags have been added
            S7CommunicationError: If communication fails
        """
        if not self._tags:
            raise ValueError("No tags added to batch")
        
        # Save original values if rollback is enabled
        if self.rollback_on_error:
            try:
                self._original_values = self._client.read(self._tags)
            except Exception as e:
                self._client.logger.warning(
                    f"Could not read original values for rollback: {e}"
                )
                self._original_values = None
        
        # Execute writes
        results = self._client.write_detailed(self._tags, self._values)
        
        # Check for failures and rollback if needed
        if self.rollback_on_error:
            failed_results = [r for r in results if not r.success]
            if failed_results and self._original_values is not None:
                self._client.logger.warning(
                    f"Batch write had {len(failed_results)} failures, rolling back"
                )
                try:
                    # Restore original values
                    self._client.write(self._tags, self._original_values)
                except Exception as e:
                    self._client.logger.error(f"Rollback failed: {e}")
        
        return results
    
    def rollback(self) -> None:
        """Manually rollback to original values.
        
        Raises:
            RuntimeError: If no original values were saved
        """
        if self._original_values is None:
            raise RuntimeError(
                "Cannot rollback: no original values saved. "
                "Ensure rollback_on_error=True or call commit() first."
            )
        
        self._client.write(self._tags, self._original_values)
        self._client.logger.info("Batch write transaction rolled back")
    
    def __enter__(self) -> 'BatchWriteTransaction':
        """Enter context manager."""
        return self
    
    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> None:
        """Exit context manager, auto-commit if enabled."""
        if exc_type is None and self.auto_commit and self._tags:
            self.commit()


class S7Client:
    """The S7Client class provides a high-level interface for communicating with a Siemens S7 programmable logic controller (PLC) over a network connection.
    It allows for reading from and writing to memory locations in the PLC, with support for a variety of data types.

    Attributes:
        address (str): The IP address of the PLC.
        rack (int): The rack number of the PLC (ignored if local_tsap/remote_tsap are provided).
        slot (int): The slot number of the PLC (ignored if local_tsap/remote_tsap are provided).
        connection_type (ConnectionType): The type of PLC connection (S7Basic, PG, OP). Default is ConnectionType.S7Basic.
        port (int): The port number for the network connection. Defaults to 102.
        timeout (int): The timeout in seconds for the network connection. Defaults to 5.
        local_tsap (Optional[Union[int, str]]): Local TSAP value (overrides rack/slot if provided).
            Can be an integer (0x0000-0xFFFF) or string in TIA Portal format (e.g., "03.00").
        remote_tsap (Optional[Union[int, str]]): Remote TSAP value (overrides rack/slot if provided).
            Can be an integer (0x0000-0xFFFF) or string in TIA Portal format (e.g., "03.01").
        max_pdu (int): Maximum PDU size for communication. Defaults to 960 bytes.
            Larger values can improve performance but must be supported by the PLC.
    """

    logger = logging.getLogger(__name__)

    def __init__(
        self,
        address: str,
        rack: int = 0,
        slot: int = 0,
        connection_type: ConnectionType = ConnectionType.S7Basic,
        port: int = 102,
        timeout: float = 5.0,
        local_tsap: Optional[Union[int, str]] = None,
        remote_tsap: Optional[Union[int, str]] = None,
        max_pdu: int = MAX_PDU,
    ) -> None:
        self.address = address
        self.rack = rack
        self.slot = slot
        self.connection_type = connection_type
        self.port = port
        self.timeout = timeout

        # Convert string TSAP to integer if needed
        if isinstance(local_tsap, str):
            local_tsap = self.tsap_from_string(local_tsap)
        if isinstance(remote_tsap, str):
            remote_tsap = self.tsap_from_string(remote_tsap)

        self.local_tsap = local_tsap
        self.remote_tsap = remote_tsap

        self.socket: Optional[socket.socket] = None
        self._io_lock = threading.Lock()
        self._connection_state = ConnectionState.DISCONNECTED
        self._last_error: Optional[str] = None

        self.pdu_size: int = max_pdu
        self.max_jobs_calling: int = MAX_JOB_CALLING
        self.max_jobs_called: int = MAX_JOB_CALLED

        # Validate TSAP values if provided
        if local_tsap is not None or remote_tsap is not None:
            self._validate_tsap(local_tsap, remote_tsap)

    def __enter__(self) -> "S7Client":
        """Context manager entry: establish connection to PLC."""
        self.connect()
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        """Context manager exit: disconnect from PLC."""
        self.disconnect()

    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state.
        
        Returns:
            ConnectionState: Current connection state
            
        Example:
            >>> client = S7Client('192.168.0.1', 0, 1)
            >>> print(client.connection_state)
            ConnectionState.DISCONNECTED
            >>> client.connect()
            >>> print(client.connection_state)
            ConnectionState.CONNECTED
        """
        return self._connection_state
    
    @property
    def last_error(self) -> Optional[str]:
        """Get the last connection error message.
        
        Returns:
            Optional[str]: Last error message, or None if no error
            
        Example:
            >>> client = S7Client('192.168.0.1', 0, 1)
            >>> try:
            ...     client.connect()
            ... except Exception:
            ...     print(client.last_error)
        """
        return self._last_error
    
    def _set_connection_state(self, state: ConnectionState, error: Optional[str] = None) -> None:
        """Set connection state and optionally store error.
        
        Args:
            state: New connection state
            error: Optional error message for ERROR state
        """
        old_state = self._connection_state
        self._connection_state = state
        
        if state == ConnectionState.ERROR:
            self._last_error = error
        elif state == ConnectionState.CONNECTED:
            # Clear error when successfully connected
            self._last_error = None
        
        if old_state != state:
            self.logger.debug(f"Connection state: {old_state.value} → {state.value}")
            if error:
                self.logger.debug(f"Error: {error}")

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected to the PLC.
        
        Returns:
            bool: True if connected, False otherwise
            
        Example:
            >>> client = S7Client('192.168.0.1', 0, 1)
            >>> print(client.is_connected)
            False
            >>> client.connect()
            >>> print(client.is_connected)
            True
            >>> client.disconnect()
            >>> print(client.is_connected)
            False
        """
        return self._connection_state == ConnectionState.CONNECTED

    def _read_large_string(self, tag: S7Tag) -> str:
        """Read a STRING or WSTRING that exceeds PDU size by chunking.
        
        Args:
            tag: The S7Tag representing a STRING or WSTRING
            
        Returns:
            The complete string value
        """
        chunks: List[str] = []
        
        if tag.data_type == DataType.STRING:
            # STRING: 1 byte max_length + 1 byte current_length + data
            header_size = 2
            # Read header to know actual string length
            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=2
            )
            header_bytes = self.read([header_tag], optimize=False)[0]
            # BYTE reads return a tuple of integers
            if not isinstance(header_bytes, tuple) or len(header_bytes) < 2:
                raise S7CommunicationError(
                    f"Invalid STRING header response: expected tuple with at least 2 bytes, got {type(header_bytes).__name__}"
                )
            max_length = int(header_bytes[0])
            current_length = int(header_bytes[1])
            
            if current_length == 0:
                return ""
            
            # Calculate chunk size
            max_data_per_read = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
            
            # Read data in chunks
            offset = 0
            while offset < current_length:
                chunk_size = min(max_data_per_read, current_length - offset)
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.CHAR,
                    start=tag.start + header_size + offset,
                    bit_offset=0,
                    length=chunk_size
                )
                chunk_data = self.read([chunk_tag], optimize=False)[0]
                if not isinstance(chunk_data, str):
                    raise S7CommunicationError(
                        f"Invalid STRING chunk response: expected str, got {type(chunk_data).__name__}"
                    )
                chunks.append(chunk_data)
                offset += chunk_size
            
            return "".join(chunks)
            
        elif tag.data_type == DataType.WSTRING:
            # WSTRING: 2 bytes max_length + 2 bytes current_length + UTF-16 data
            header_size = 4
            # Read header to know actual string length
            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=4
            )
            header_bytes = self.read([header_tag], optimize=False)[0]
            # BYTE reads return a tuple of integers
            if not isinstance(header_bytes, tuple) or len(header_bytes) < 4:
                raise S7CommunicationError(
                    f"Invalid WSTRING header response: expected tuple with at least 4 bytes, got {type(header_bytes).__name__}"
                )
            max_length = (int(header_bytes[0]) << 8) | int(header_bytes[1])
            current_length = (int(header_bytes[2]) << 8) | int(header_bytes[3])
            
            if current_length == 0:
                return ""
            
            # Calculate chunk size (in bytes, not characters)
            max_data_per_read = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
            # WSTRING uses 2 bytes per character
            bytes_to_read = current_length * 2
            
            # Read data in chunks
            offset = 0
            while offset < bytes_to_read:
                chunk_size = min(max_data_per_read, bytes_to_read - offset)
                # Make sure chunk_size is even (UTF-16 uses 2 bytes per char)
                if chunk_size % 2 != 0:
                    chunk_size -= 1
                
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.BYTE,
                    start=tag.start + header_size + offset,
                    bit_offset=0,
                    length=chunk_size
                )
                chunk_bytes = self.read([chunk_tag], optimize=False)[0]
                # BYTE reads return a tuple of integers, convert to bytes
                if not isinstance(chunk_bytes, tuple):
                    raise S7CommunicationError(
                        f"Invalid WSTRING chunk response: expected tuple of bytes, got {type(chunk_bytes).__name__}"
                    )
                byte_array = bytes(int(b) for b in chunk_bytes)
                chunks.append(byte_array.decode("utf-16-be"))
                offset += chunk_size
            
            return "".join(chunks)
        
        raise ValueError(f"Unsupported data type for large string read: {tag.data_type}")

    def _write_large_string(self, tag: S7Tag, value: str) -> None:
        """Write a STRING or WSTRING that exceeds PDU size by chunking.
        
        Args:
            tag: The S7Tag representing a STRING or WSTRING
            value: The string value to write
        """
        if tag.data_type == DataType.STRING:
            # STRING: 1 byte max_length + 1 byte current_length + data
            # Note: S7 STRING can only support up to 254 characters because
            # both length fields are single bytes (0-255), and 255 is often reserved
            header_size = 2
            max_length = tag.length
            
            # Validate string length
            encoded_value = value.encode('ascii', errors='replace')
            
            # Check if current string length exceeds byte range
            if len(encoded_value) > 254:
                raise S7AddressError(
                    f"STRING value length ({len(encoded_value)}) exceeds maximum supported length (254 characters). "
                    f"S7 STRING uses single-byte length fields and cannot store more than 254 characters. "
                    f"Consider using WSTRING for longer strings or splitting into multiple STRING variables."
                )
            
            if len(encoded_value) > max_length:
                raise ValueError(
                    f"String value length ({len(encoded_value)}) exceeds declared maximum length ({max_length})"
                )
            
            current_length = len(encoded_value)
            
            # Write header (max_length and current_length)
            # Note: max_length is stored in a single byte, so it's clamped to 254
            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=2
            )
            # Clamp max_length to 254 (safe maximum for STRING)
            header_max_length = min(max_length, 254)
            header_values = (header_max_length, current_length)
            self.write([header_tag], [header_values])
            
            if current_length == 0:
                return
            
            # Calculate chunk size
            max_data_per_write = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
            
            # Write data in chunks
            offset = 0
            while offset < current_length:
                chunk_size = min(max_data_per_write, current_length - offset)
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.CHAR,
                    start=tag.start + header_size + offset,
                    bit_offset=0,
                    length=chunk_size
                )
                chunk_value = encoded_value[offset:offset + chunk_size].decode('ascii')
                self.write([chunk_tag], [chunk_value])
                offset += chunk_size
            
        elif tag.data_type == DataType.WSTRING:
            # WSTRING: 2 bytes max_length + 2 bytes current_length + UTF-16 data
            header_size = 4
            max_length = tag.length
            
            # Validate string length (in characters)
            if len(value) > max_length:
                raise ValueError(
                    f"String value length ({len(value)}) exceeds maximum length ({max_length})"
                )
            
            current_length = len(value)
            
            # Write header (max_length and current_length)
            header_tag = S7Tag(
                memory_area=tag.memory_area,
                db_number=tag.db_number,
                data_type=DataType.BYTE,
                start=tag.start,
                bit_offset=0,
                length=4
            )
            # Pack as big-endian 16-bit values (clamp to 65535 max)
            header_max_length = min(max_length, 65535)
            header_bytes: tuple[int, int, int, int] = (
                (header_max_length >> 8) & 0xFF,
                header_max_length & 0xFF,
                (current_length >> 8) & 0xFF,
                current_length & 0xFF
            )
            self.write([header_tag], [header_bytes])
            
            if current_length == 0:
                return
            
            # Calculate chunk size (in bytes, not characters)
            max_data_per_write = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
            # WSTRING uses 2 bytes per character
            encoded_value = value.encode('utf-16-be')
            bytes_to_write = len(encoded_value)
            
            # Write data in chunks
            offset = 0
            while offset < bytes_to_write:
                chunk_size = min(max_data_per_write, bytes_to_write - offset)
                # Make sure chunk_size is even (UTF-16 uses 2 bytes per char)
                if chunk_size % 2 != 0:
                    chunk_size -= 1
                
                chunk_tag = S7Tag(
                    memory_area=tag.memory_area,
                    db_number=tag.db_number,
                    data_type=DataType.BYTE,
                    start=tag.start + header_size + offset,
                    bit_offset=0,
                    length=chunk_size
                )
                chunk_bytes = encoded_value[offset:offset + chunk_size]
                # Convert bytes to tuple of integers for BYTE write
                chunk_values = tuple(b for b in chunk_bytes)
                self.write([chunk_tag], [chunk_values])
                offset += chunk_size
        else:
            raise ValueError(f"Unsupported data type for large string write: {tag.data_type}")

    @staticmethod
    def tsap_from_string(tsap_str: str) -> int:
        """Convert Siemens TIA Portal TSAP notation to integer value.

        TIA Portal uses the format "XX.YY" where XX and YY are hexadecimal bytes.
        For example: "03.00" = 0x0300, "03.01" = 0x0301, "22.00" = 0x2200

        Args:
            tsap_str: TSAP string in format "XX.YY" (e.g., "03.00", "22.00")

        Returns:
            int: TSAP value as integer

        Raises:
            ValueError: If format is invalid or values are out of range

        Example:
            >>> local_tsap = S7Client.tsap_from_string("03.00")   # 0x0300
            >>> remote_tsap = S7Client.tsap_from_string("03.01")  # 0x0301
            >>> remote_tsap = S7Client.tsap_from_string("22.00")  # 0x2200
            >>> client = S7Client(address="192.168.0.1", local_tsap=local_tsap, remote_tsap=remote_tsap)
        """
        if not isinstance(tsap_str, str):
            raise ValueError(f"tsap_str must be a string, got {type(tsap_str).__name__}")

        parts = tsap_str.split('.')
        if len(parts) != 2:
            raise ValueError(
                f"TSAP string must be in format 'XX.YY' (e.g., '03.00', '22.00'), got '{tsap_str}'"
            )

        try:
            # Interpret as hexadecimal values (as TIA Portal does)
            byte1 = int(parts[0], 16)
            byte2 = int(parts[1], 16)
        except ValueError as e:
            raise ValueError(
                f"TSAP string must contain hexadecimal numbers (e.g., '03.00', '22.00'), got '{tsap_str}'"
            ) from e

        if not 0 <= byte1 <= 255:
            raise ValueError(f"First byte must be in range 0x00-0xFF, got 0x{byte1:02X}")
        if not 0 <= byte2 <= 255:
            raise ValueError(f"Second byte must be in range 0x00-0xFF, got 0x{byte2:02X}")

        return (byte1 << 8) | byte2

    @staticmethod
    def tsap_to_string(tsap: int) -> str:
        """Convert TSAP integer value to Siemens TIA Portal notation.

        Converts an integer TSAP value to TIA Portal format "XX.YY" where
        XX and YY are hexadecimal bytes.
        For example: 0x0300 = "03.00", 0x0301 = "03.01", 0x2200 = "22.00"

        Args:
            tsap: TSAP value as integer (0x0000 to 0xFFFF)

        Returns:
            str: TSAP string in format "XX.YY" (hexadecimal)

        Raises:
            ValueError: If TSAP value is out of range

        Example:
            >>> tsap_str = S7Client.tsap_to_string(0x0301)
            >>> print(tsap_str)  # "03.01"
            >>> tsap_str = S7Client.tsap_to_string(0x2200)
            >>> print(tsap_str)  # "22.00"
        """
        if not isinstance(tsap, int):
            raise ValueError(f"tsap must be an integer, got {type(tsap).__name__}")
        if not 0x0000 <= tsap <= 0xFFFF:
            raise ValueError(
                f"tsap must be in range 0x0000-0xFFFF (0-65535), got 0x{tsap:04X} ({tsap})"
            )

        byte1 = (tsap >> 8) & 0xFF
        byte2 = tsap & 0xFF
        return f"{byte1:02x}.{byte2:02x}"

    @staticmethod
    def tsap_from_rack_slot(rack: int, slot: int) -> int:
        """Calculate remote TSAP value from rack and slot numbers.

        This is a helper method for users who want to use TSAP connection
        but need to calculate the TSAP value from rack/slot.

        Args:
            rack: Rack number (0-7)
            slot: Slot number (0-31)

        Returns:
            int: Remote TSAP value (0x0100 | (rack * 32 + slot))

        Raises:
            ValueError: If rack or slot values are out of range

        Example:
            >>> tsap = S7Client.tsap_from_rack_slot(0, 1)
            >>> print(f"0x{tsap:04X}")  # 0x0101
            >>> client = S7Client(address="192.168.0.1", local_tsap=0x0100, remote_tsap=tsap)
        """
        if not isinstance(rack, int) or not isinstance(slot, int):
            raise ValueError("rack and slot must be integers")
        if not 0 <= rack <= 7:
            raise ValueError(f"rack must be in range 0-7, got {rack}")
        if not 0 <= slot <= 31:
            raise ValueError(f"slot must be in range 0-31, got {slot}")

        return 0x0100 | (rack * 32 + slot)

    @staticmethod
    def _validate_single_tsap(tsap_value: int, tsap_name: str) -> None:
        """Validate a single TSAP value.
        
        Args:
            tsap_value: TSAP value to validate (0x0000 to 0xFFFF)
            tsap_name: Name of the TSAP parameter for error messages
            
        Raises:
            ValueError: If TSAP value is invalid
        """
        if not isinstance(tsap_value, int):
            raise ValueError(f"{tsap_name} must be an integer, got {type(tsap_value).__name__}")
        if not 0x0000 <= tsap_value <= 0xFFFF:
            raise ValueError(
                f"{tsap_name} must be in range 0x0000-0xFFFF (0-65535), "
                f"got 0x{tsap_value:04X} ({tsap_value})"
            )

    def _validate_and_adjust_pdu(self, requested: int, negotiated: int) -> int:
        """Validate the negotiated PDU size and warn user if needed.
        
        Args:
            requested: PDU size requested by client
            negotiated: PDU size returned by PLC
            
        Returns:
            Validated and possibly adjusted PDU size
            
        Raises:
            S7ConnectionError: If negotiated PDU is invalid
        """
        # 1. Check protocol limits
        if negotiated <= 0 or negotiated < MIN_PDU_SIZE:
            raise S7ConnectionError(
                f"PLC returned invalid PDU size: {negotiated} bytes. "
                f"Minimum required: {MIN_PDU_SIZE} bytes. "
                f"Check PLC configuration or try a different connection type."
            )
        
        if negotiated > MAX_PDU_SIZE:
            self.logger.warning(
                f"PLC returned unusually large PDU size: {negotiated} bytes, "
                f"clamping to protocol maximum: {MAX_PDU_SIZE} bytes"
            )
            negotiated = MAX_PDU_SIZE
        
        # 2. Warn if PDU is very small
        if negotiated < RECOMMENDED_MIN_PDU:
            self.logger.warning(
                f"⚠️  PLC negotiated very small PDU: {negotiated} bytes. "
                f"This may limit functionality and performance. "
                f"Recommended minimum: {RECOMMENDED_MIN_PDU} bytes. "
                f"Consider: 1) Checking PLC configuration, 2) Using larger PDU in TIA Portal, "
                f"3) Reading/writing smaller data chunks."
            )
        
        # 3. Info if significantly reduced from request
        if negotiated < requested:
            reduction_percent = ((requested - negotiated) / requested) * 100
            if reduction_percent >= 20:
                self.logger.info(
                    f"PDU size reduced by {reduction_percent:.0f}%: "
                    f"requested {requested} bytes, negotiated {negotiated} bytes. "
                    f"Operations will be automatically adjusted to fit smaller PDU."
                )
        
        return negotiated

    @staticmethod
    def _validate_tsap(local_tsap: Optional[int], remote_tsap: Optional[int]) -> None:
        """Validate TSAP values are within valid ranges.

        Args:
            local_tsap: Local TSAP value (0x0000 to 0xFFFF)
            remote_tsap: Remote TSAP value (0x0000 to 0xFFFF)

        Raises:
            ValueError: If TSAP values are invalid
        """
        # If only one TSAP is provided, raise error
        if (local_tsap is None) != (remote_tsap is None):
            raise ValueError(
                "Both local_tsap and remote_tsap must be provided together, or neither. "
                f"Got local_tsap={local_tsap}, remote_tsap={remote_tsap}"
            )
        
        # Validate individual TSAP values if provided
        if local_tsap is not None:
            S7Client._validate_single_tsap(local_tsap, "local_tsap")
        if remote_tsap is not None:
            S7Client._validate_single_tsap(remote_tsap, "remote_tsap")

    def connect(self) -> None:
        """Establishes a TCP connection to the S7 PLC and sets up initial communication parameters."""
        
        # Check if already connected or connecting
        if self._connection_state == ConnectionState.CONNECTED:
            self.logger.warning("Already connected to PLC")
            return
        
        if self._connection_state == ConnectionState.CONNECTING:
            self.logger.warning("Connection already in progress")
            return
        
        self._set_connection_state(ConnectionState.CONNECTING)

        if self.local_tsap is not None and self.remote_tsap is not None:
            self.logger.debug(
                f"Connecting to PLC at {self.address}:{self.port} "
                f"(local_tsap={self.local_tsap:#06x}, remote_tsap={self.remote_tsap:#06x})"
            )
        else:
            self.logger.debug(
                f"Connecting to PLC at {self.address}:{self.port} "
                f"(rack={self.rack}, slot={self.slot})"
            )
        try:
            # Initialize the socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)

            # Establish TCP connection
            self.socket.connect((self.address, self.port))
            self.logger.debug(f"TCP connection established to {self.address}:{self.port}")
        except socket.timeout as e:
            error_msg = f"Connection timeout to {self.address}:{self.port} after {self.timeout}s"
            self.socket = None
            self._set_connection_state(ConnectionState.ERROR, error_msg)
            self.logger.error(error_msg)
            raise S7TimeoutError(error_msg) from e
        except socket.error as e:
            error_msg = f"Failed to connect to {self.address}:{self.port}: {e}"
            self.socket = None
            self._set_connection_state(ConnectionState.ERROR, error_msg)
            self.logger.error(error_msg)
            raise S7ConnectionError(error_msg) from e

        try:
            connection_request = ConnectionRequest(
                connection_type=self.connection_type,
                rack=self.rack,
                slot=self.slot,
                local_tsap=self.local_tsap,
                remote_tsap=self.remote_tsap,
            )
            if self.local_tsap is not None and self.remote_tsap is not None:
                self.logger.debug(f"Sending COTP connection request (local_tsap={self.local_tsap:#06x}, remote_tsap={self.remote_tsap:#06x})")
            else:
                self.logger.debug(f"Sending COTP connection request (rack={self.rack}, slot={self.slot})")
            
            # Log the actual COTP packet for debugging
            cotp_packet = connection_request.serialize()
            self.logger.debug(f"COTP CR packet: {cotp_packet.hex()}")
            
            connection_bytes_response: bytes = self.__send(connection_request)
            ConnectionResponse(response=connection_bytes_response)
            self.logger.debug("COTP connection accepted")

            # Communication Setup
            requested_pdu = self.pdu_size
            pdu_negotation_request = PDUNegotiationRequest(max_pdu=requested_pdu)
            self.logger.debug(f"Negotiating PDU size (requested: {requested_pdu} bytes)")
            pdu_negotation_bytes_response: bytes = self.__send(pdu_negotation_request)
            pdu_negotiation_response = PDUNegotiationResponse(
                response=pdu_negotation_bytes_response
            )

            (
                self.max_jobs_calling,
                self.max_jobs_called,
                negotiated_pdu,
            ) = pdu_negotiation_response.parse()
            
            # Validate and adjust PDU size
            self.pdu_size = self._validate_and_adjust_pdu(requested_pdu, negotiated_pdu)
            
            self._set_connection_state(ConnectionState.CONNECTED)
            self.logger.debug(
                f"Connected to PLC {self.address}:{self.port} - "
                f"PDU: {self.pdu_size} bytes, Jobs: {self.max_jobs_calling}/{self.max_jobs_called}"
            )
        except socket.timeout as e:
            error_msg = f"Connection timeout during COTP/PDU negotiation after {self.timeout}s: {e}"
            self._set_connection_state(ConnectionState.ERROR, error_msg)
            self.logger.error(error_msg)
            self.disconnect()
            raise S7TimeoutError(error_msg) from e
        except socket.error as e:
            error_msg = f"Socket error during connection setup: {e}"
            self._set_connection_state(ConnectionState.ERROR, error_msg)
            self.logger.error(error_msg)
            self.disconnect()
            raise S7ConnectionError(error_msg) from e
        except S7ConnectionError as e:
            # Re-raise S7ConnectionError as-is
            self._set_connection_state(ConnectionState.ERROR, str(e))
            self.disconnect()
            raise
        except S7CommunicationError as e:
            # Wrap S7CommunicationError in S7ConnectionError during connection phase
            error_msg = f"Communication error during connection setup: {e}"
            self._set_connection_state(ConnectionState.ERROR, error_msg)
            self.logger.error(error_msg)
            self.disconnect()
            raise S7ConnectionError(error_msg) from e
        except (ValueError, struct.error) as e:
            # Protocol parsing errors
            error_msg = f"Invalid protocol response during connection setup: {e}"
            self._set_connection_state(ConnectionState.ERROR, error_msg)
            self.logger.error(error_msg)
            self.disconnect()
            raise S7ProtocolError(error_msg) from e

    def disconnect(self) -> None:
        """Closes the TCP connection with the S7 PLC."""
        
        if self._connection_state == ConnectionState.DISCONNECTED:
            self.logger.debug("Already disconnected")
            return
        
        # Don't change state if we're cleaning up after an error during connection
        if self._connection_state != ConnectionState.ERROR:
            self._set_connection_state(ConnectionState.DISCONNECTING)

        if self.socket:
            self.logger.debug(f"Disconnecting from {self.address}:{self.port}")
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
                self.logger.debug(f"Disconnected from PLC {self.address}:{self.port}")
            except socket.error as e:
                self.logger.warning(f"Error during disconnect: {e}")
            finally:
                self.socket = None
        
        # Set to DISCONNECTED unless we were in ERROR state (preserve ERROR)
        if self._connection_state != ConnectionState.ERROR:
            self._set_connection_state(ConnectionState.DISCONNECTED)

    def read(
        self, tags: Sequence[Union[str, S7Tag]], optimize: bool = True
    ) -> List[Value]:
        """Reads data from an S7 PLC using the specified addresses.

        Args:
            tags (Sequence[S7Tag | str]): A sequence of S7Tag or string addresses to be read from the PLC.
            optimize (bool): If True, the tags are grouped together in the request to optimize the communication. Defaults to True.

        Returns:
            List[Value]: Values read from the PLC corresponding to the input addresses.

        Example:
            >>> client = S7Client('192.168.100.10', 0, 1)
            >>> client.connect()
            >>> tags = [
                    'DB1,X0.0',
                    'DB2,I2',
                    S7Tag(memory_area=MemoryArea.DB, db_number=3, data_type=DataType.REAL, start=4, bit_offset=0, length=1)
                ]
            >>> result = client.read(tags)
            >>> print(result)
            [True, 300, 20.5] # these values corresponds to the PLC data at specified addresses
        """
        list_tags: List[S7Tag] = [
            map_address_to_tag(address=tag) if isinstance(tag, str) else tag
            for tag in tags
        ]

        if not list_tags:
            self.logger.debug("Read called with empty tag list")
            return []
        
        self.logger.debug(
            f"Reading {len(list_tags)} tag(s) - optimize={optimize}, "
            f"PDU={self.pdu_size} bytes"
        )

        if not self.is_connected:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before performing read operations."
            )

        # Check for large tags (strings and arrays) and handle them separately
        regular_tags = []
        large_string_indices = []
        large_string_tags = []
        
        for i, tag in enumerate(list_tags):
            # Check if tag response exceeds PDU size
            tag_response_size = READ_RES_OVERHEAD + READ_RES_PARAM_SIZE_TAG + tag.size()
            if tag_response_size > self.pdu_size:
                # Only STRING and WSTRING support automatic chunking
                if tag.data_type in (DataType.STRING, DataType.WSTRING):
                    # This string is too large, will be read separately with chunking
                    large_string_indices.append(i)
                    large_string_tags.append(tag)
                    self.logger.debug(
                        f"Tag {tag} exceeds PDU size ({tag_response_size} > {self.pdu_size}), "
                        f"will be read in chunks automatically"
                    )
                    continue
                else:
                    # Other data types cannot be automatically chunked
                    tag_size = tag.size()
                    max_data_size = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
                    raise S7AddressError(
                        f"{tag} requires {tag_response_size} bytes but PDU size is {self.pdu_size} bytes. "
                        f"Maximum data size for this PDU: {max_data_size} bytes (current tag needs {tag_size} bytes). "
                        f"For {tag.data_type.name} arrays, read in smaller chunks. "
                        f"For STRING/WSTRING, automatic chunking is supported."
                    )
            regular_tags.append((i, tag))
        
        # Read regular tags (initialize with Optional[Value])
        data: List[Optional[Value]] = [None] * len(list_tags)

        # Read large strings separately with chunking
        for idx, tag in zip(large_string_indices, large_string_tags):
            data[idx] = self._read_large_string(tag)
        
        # Read regular tags if any
        if regular_tags:
            tags_only = [tag for _, tag in regular_tags]
            
            if optimize:
                requests, tags_map = prepare_optimized_requests(
                    tags=tags_only, max_pdu=self.pdu_size
                )
                self.logger.debug(
                    f"Optimized {len(tags_only)} tags into {len(requests[0])} request(s) "
                    f"(reduction: {len(tags_only) - len(requests[0])} merges)"
                )

                bytes_reponse = self.__send(ReadRequest(tags=requests[0]))
                response = ReadOptimizedResponse(
                    response=bytes_reponse,
                    tag_map={key: tags_map[key] for key in requests[0]},
                )

                for i in range(1, len(requests)):
                    bytes_reponse = self.__send(ReadRequest(tags=requests[i]))
                    response += ReadOptimizedResponse(
                        response=bytes_reponse,
                        tag_map={key: tags_map[key] for key in requests[i]},
                    )

                regular_data = response.parse()

            else:
                requests = prepare_requests(tags=tags_only, max_pdu=self.pdu_size)
                regular_data = []

                for request in requests:
                    bytes_reponse = self.__send(ReadRequest(tags=request))
                    read_response = ReadResponse(response=bytes_reponse, tags=request)
                    regular_data.extend(read_response.parse())
            
            # Fill in regular data at correct indices
            for (orig_idx, _), value in zip(regular_tags, regular_data):
                data[orig_idx] = value

        # All elements have been filled at this point (either large strings or regular tags)
        self.logger.debug(f"Read completed: {len(list_tags)} tag(s) retrieved successfully")
        return cast(List[Value], data)

    def read_detailed(
        self, tags: Sequence[Union[str, S7Tag]], optimize: bool = True
    ) -> List[ReadResult]:
        """Reads data from an S7 PLC with detailed results for each tag.
        
        Unlike read(), this method does not raise an exception on read failures.
        Instead, it returns detailed results for each tag, allowing you to see
        which reads succeeded and which failed.
        
        Args:
            tags (Sequence[S7Tag | str]): A sequence of S7Tag or string addresses.
            optimize (bool): If True, optimize reads by merging adjacent tags.
                Default True.
        
        Returns:
            List[ReadResult]: A list of ReadResult objects, one for each tag,
                containing success status, value, and error information.
        
        Raises:
            ValueError: If no tags are provided.
            S7CommunicationError: If not connected to PLC.
        
        Example:
            >>> client = S7Client('192.168.100.10', 0, 1)
            >>> client.connect()
            >>> tags = ['DB1,X0.0', 'DB1,I10', 'DB99,R14']  # DB99 might not exist
            >>> results = client.read_detailed(tags)
            >>> for result in results:
            ...     if result.success:
            ...         print(f"{result.tag}: {result.value}")
            ...     else:
            ...         print(f"{result.tag}: FAILED - {result.error}")
        """
        if not tags:
            raise ValueError("Tags list cannot be empty")
        
        # Convert string addresses to S7Tag objects
        list_tags: List[S7Tag] = [
            map_address_to_tag(address=tag) if isinstance(tag, str) else tag
            for tag in tags
        ]
        
        self.logger.debug(
            f"Reading {len(list_tags)} tag(s) with detailed results - "
            f"optimize={optimize}, PDU={self.pdu_size} bytes"
        )
        
        if not self.is_connected:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before performing read operations."
            )
        
        # Initialize results list
        results: List[ReadResult] = []
        
        # Track which tags have been processed
        processed_indices = set()
        
        # Handle large strings separately
        for i, tag in enumerate(list_tags):
            tag_response_size = READ_RES_OVERHEAD + READ_RES_PARAM_SIZE_TAG + tag.size()
            if tag_response_size > self.pdu_size:
                if tag.data_type in (DataType.STRING, DataType.WSTRING):
                    # Read large string with chunking
                    try:
                        value = self._read_large_string(tag)
                        results.append(ReadResult(tag=tag, success=True, value=value))
                        processed_indices.add(i)
                        self.logger.debug(f"Large string read succeeded: {tag}")
                    except Exception as e:
                        results.append(
                            ReadResult(
                                tag=tag,
                                success=False,
                                error=f"Large string read failed: {str(e)}"
                            )
                        )
                        processed_indices.add(i)
                        self.logger.warning(f"Large string read failed: {tag} - {e}")
                else:
                    # Tag too large for PDU
                    tag_size = tag.size()
                    max_data_size = self.pdu_size - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
                    results.append(
                        ReadResult(
                            tag=tag,
                            success=False,
                            error=f"Tag exceeds PDU size: {tag_response_size} bytes > {self.pdu_size} bytes. "
                                  f"Maximum: {max_data_size} bytes. Read in smaller chunks."
                        )
                    )
                    processed_indices.add(i)
        
        # Collect regular tags (not yet processed)
        regular_tags = [
            (i, tag) for i, tag in enumerate(list_tags) if i not in processed_indices
        ]
        
        # Read regular tags if any
        if regular_tags:
            tags_only = [tag for _, tag in regular_tags]
            
            try:
                if optimize:
                    requests, tags_map = prepare_optimized_requests(
                        tags=tags_only, max_pdu=self.pdu_size
                    )
                    self.logger.debug(
                        f"Optimized {len(tags_only)} tags into {len(requests[0])} request(s)"
                    )
                    
                    # Process all requests and parse with detailed error handling
                    all_bytes_responses = []
                    all_requests = []
                    
                    for request in requests:
                        try:
                            bytes_response = self.__send(ReadRequest(tags=request))
                            all_bytes_responses.append(bytes_response)
                            all_requests.append(request)
                        except Exception as e:
                            # If entire request fails, mark all tags in it as failed
                            for req_tag in request:
                                # Find original tags that match this request tag
                                for orig_idx, orig_tag in regular_tags:
                                    if orig_tag == req_tag:
                                        results.append(
                                            ReadResult(
                                                tag=orig_tag,
                                                success=False,
                                                error=f"Request failed: {str(e)}"
                                            )
                                        )
                                        processed_indices.add(orig_idx)
                            self.logger.warning(f"Read request failed: {e}")
                    
                    # Parse responses with detailed error handling
                    for bytes_response, request in zip(all_bytes_responses, all_requests):
                        # Extract only the original tag from tags_map for each request tag
                        tag_map: Dict[S7Tag, S7Tag] = {}
                        for key in request:
                            mapped = tags_map.get(key)
                            if mapped:
                                # Get the first original tag from the list
                                tag_map[key] = mapped[0][1]
                        detailed_results = self._parse_read_response_detailed(
                            bytes_response, request, tag_map
                        )
                        
                        # Map back to original indices
                        for result in detailed_results:
                            for orig_idx, orig_tag in regular_tags:
                                if orig_tag == result.tag and orig_idx not in processed_indices:
                                    results.append(result)
                                    processed_indices.add(orig_idx)
                                    break
                
                else:
                    requests = prepare_requests(tags=tags_only, max_pdu=self.pdu_size)
                    
                    for request in requests:
                        try:
                            bytes_response = self.__send(ReadRequest(tags=request))
                            detailed_results = self._parse_read_response_detailed(
                                bytes_response, request, None
                            )
                            
                            # Map back to original indices
                            for result in detailed_results:
                                for orig_idx, orig_tag in regular_tags:
                                    if orig_tag == result.tag and orig_idx not in processed_indices:
                                        results.append(result)
                                        processed_indices.add(orig_idx)
                                        break
                        
                        except Exception as e:
                            # Mark all tags in failed request as failed
                            for req_tag in request:
                                for orig_idx, orig_tag in regular_tags:
                                    if orig_tag == req_tag and orig_idx not in processed_indices:
                                        results.append(
                                            ReadResult(
                                                tag=orig_tag,
                                                success=False,
                                                error=f"Request failed: {str(e)}"
                                            )
                                        )
                                        processed_indices.add(orig_idx)
                            self.logger.warning(f"Read request failed: {e}")
            
            except Exception as e:
                # Unexpected error, mark all remaining tags as failed
                self.logger.error(f"Unexpected error during read_detailed: {e}")
                for orig_idx, orig_tag in regular_tags:
                    if orig_idx not in processed_indices:
                        results.append(
                            ReadResult(
                                tag=orig_tag,
                                success=False,
                                error=f"Unexpected error: {str(e)}"
                            )
                        )
        
        # Sort results by original order
        results_dict = {}
        for result in results:
            for i, tag in enumerate(list_tags):
                if tag == result.tag and i not in results_dict:
                    results_dict[i] = result
                    break
        
        sorted_results = [results_dict[i] for i in sorted(results_dict.keys())]
        
        success_count = sum(1 for r in sorted_results if r.success)
        self.logger.debug(
            f"Read detailed completed: {success_count}/{len(list_tags)} tags succeeded"
        )
        
        return sorted_results

    def write(self, tags: Sequence[Union[str, S7Tag]], values: Sequence[Value]) -> None:
        """Writes data to an S7 PLC at the specified addresses.

        Args:
            tags (Sequence[S7Tag | str]): A sequence of S7Tag or string addresses where the data will be written to in the PLC.
            values (Sequence[Value]): Values to be written to the PLC.

        Raises:
            ValueError: If the number of tags doesn't match the number of values.
            WriteResponseError: If it is impossible to parse the write response.

        Example:
            >>> client = S7Client('192.168.100.10', 0, 1)
            >>> client.connect()
            >>> tags = ['DB1,X0.0', 'DB1,I10', 'DB2,R14']
            >>> values = [False, 500, 40.5]
            >>> client.write(tags, values)  # writes these values to the PLC at specified addresses
        """

        if len(tags) != len(values):
            raise ValueError(
                "The number of tags should be equal to the number of values."
            )

        tags_list: List[S7Tag] = [
            map_address_to_tag(address=tag) if isinstance(tag, str) else tag
            for tag in tags
        ]

        if not tags_list:
            self.logger.debug("Write called with empty tag list")
            return
        
        self.logger.debug(f"Writing {len(tags_list)} tag(s) to PLC")

        if not self.is_connected:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before performing write operations."
            )

        # Check for large tags (strings) and handle them separately
        regular_tags = []
        regular_values = []
        large_string_indices = []
        
        for i, (tag, value) in enumerate(zip(tags_list, values)):
            # Check if tag request exceeds PDU size
            tag_request_size = WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag.size() + 4
            if tag_request_size > self.pdu_size:
                # Only STRING and WSTRING support automatic chunking
                if tag.data_type in (DataType.STRING, DataType.WSTRING):
                    # This string is too large, will be written separately with chunking
                    large_string_indices.append(i)
                    self.logger.debug(
                        f"Tag {tag} exceeds PDU size ({tag_request_size} > {self.pdu_size}), "
                        f"will be written in chunks automatically"
                    )
                    self._write_large_string(tag, value)  # type: ignore
                    continue
                else:
                    # Other data types cannot be automatically chunked
                    tag_size = tag.size()
                    max_data_size = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
                    raise S7AddressError(
                        f"{tag} requires {tag_request_size} bytes but PDU size is {self.pdu_size} bytes. "
                        f"Maximum data size for this PDU: {max_data_size} bytes (current tag needs {tag_size} bytes). "
                        f"For {tag.data_type.name} arrays, write in smaller chunks. "
                        f"For STRING/WSTRING, automatic chunking is supported."
                    )
            regular_tags.append(tag)
            regular_values.append(value)
        
        # Write regular tags if any
        if regular_tags:
            requests, requests_values = prepare_write_requests_and_values(
                tags=regular_tags, values=regular_values, max_pdu=self.pdu_size
            )

            for i, request in enumerate(requests):
                bytes_response = self.__send(
                    WriteRequest(tags=request, values=requests_values[i])
                )
                response = WriteResponse(response=bytes_response, tags=request)
                response.parse()
        
        self.logger.debug(f"Write completed: {len(tags_list)} tag(s) written successfully")

    def write_detailed(
        self, tags: Sequence[Union[str, S7Tag]], values: Sequence[Value]
    ) -> List[WriteResult]:
        """Writes data to an S7 PLC with detailed results for each tag.
        
        Unlike write(), this method does not raise an exception on write failures.
        Instead, it returns detailed results for each tag, allowing you to see
        which writes succeeded and which failed.

        Args:
            tags (Sequence[S7Tag | str]): A sequence of S7Tag or string addresses.
            values (Sequence[Value]): Values to be written to the PLC.

        Returns:
            List[WriteResult]: A list of WriteResult objects, one for each tag,
                containing success status and error information.

        Raises:
            ValueError: If the number of tags doesn't match the number of values.
            S7CommunicationError: If not connected to PLC or communication fails.

        Example:
            >>> client = S7Client('192.168.100.10', 0, 1)
            >>> client.connect()
            >>> tags = ['DB1,X0.0', 'DB1,I10', 'DB2,R14']
            >>> values = [False, 500, 40.5]
            >>> results = client.write_detailed(tags, values)
            >>> for result in results:
            ...     if result.success:
            ...         print(f"{result.tag}: SUCCESS")
            ...     else:
            ...         print(f"{result.tag}: FAILED - {result.error}")
        """
        # Validate input lengths
        if not tags or not values:
            raise ValueError("Tags and values lists cannot be empty")
            
        if len(tags) != len(values):
            raise ValueError("Tags and values must have the same length")

        # Convert string addresses to S7Tag objects
        tags_list: List[S7Tag] = [
            map_address_to_tag(address=tag) if isinstance(tag, str) else tag
            for tag in tags
        ]
        
        self.logger.debug(f"Writing {len(tags_list)} tag(s) to PLC with detailed results")

        if not self.is_connected:
            raise ConnectionError("Not connected to PLC")

        # Initialize results list
        results: List[WriteResult] = []
        
        # Track which tags have been processed
        processed_indices = set()
        
        # Handle large strings separately
        for i, (tag, value) in enumerate(zip(tags_list, values)):
            tag_request_size = WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag.size() + 4
            if tag_request_size > self.pdu_size:
                if tag.data_type in (DataType.STRING, DataType.WSTRING):
                    # Write large string with chunking
                    try:
                        self._write_large_string(tag, value)  # type: ignore
                        results.append(WriteResult(tag=tag, success=True))
                        processed_indices.add(i)
                        self.logger.debug(f"Large string write succeeded: {tag}")
                    except Exception as e:
                        results.append(
                            WriteResult(
                                tag=tag,
                                success=False,
                                error=f"Large string write failed: {str(e)}"
                            )
                        )
                        processed_indices.add(i)
                        self.logger.warning(f"Large string write failed: {tag} - {e}")
                else:
                    # Tag too large for PDU
                    tag_size = tag.size()
                    max_data_size = self.pdu_size - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG - 4
                    results.append(
                        WriteResult(
                            tag=tag,
                            success=False,
                            error=f"Tag exceeds PDU size: {tag_request_size} bytes > {self.pdu_size} bytes. "
                                  f"Maximum: {max_data_size} bytes. Split into smaller chunks."
                        )
                    )
                    processed_indices.add(i)
        
        # Collect regular tags (not yet processed)
        regular_tags = []
        regular_values = []
        regular_indices = []
        
        for i, (tag, value) in enumerate(zip(tags_list, values)):
            if i not in processed_indices:
                regular_tags.append(tag)
                regular_values.append(value)
                regular_indices.append(i)
        
        # Write regular tags in batches
        if regular_tags:
            requests, requests_values = prepare_write_requests_and_values(
                tags=regular_tags, values=regular_values, max_pdu=self.pdu_size
            )

            # Track results for each batch
            tag_offset = 0
            for batch_idx, request in enumerate(requests):
                try:
                    bytes_response = self.__send(
                        WriteRequest(tags=request, values=requests_values[batch_idx])
                    )
                    # Parse with detailed results (don't raise on error)
                    batch_results = self._parse_write_response_detailed(
                        bytes_response, request
                    )
                    
                    # Map batch results back to original indices
                    for j, batch_result in enumerate(batch_results):
                        orig_idx = regular_indices[tag_offset + j]
                        results.append(batch_result)
                    
                    tag_offset += len(request)
                    
                except Exception as e:
                    # Communication error - mark all tags in this batch as failed
                    self.logger.error(f"Batch {batch_idx + 1} communication error: {e}")
                    for j in range(len(request)):
                        orig_idx = regular_indices[tag_offset + j]
                        results.append(
                            WriteResult(
                                tag=request[j],
                                success=False,
                                error=f"Communication error: {str(e)}"
                            )
                        )
                    tag_offset += len(request)
        
        # Sort results by original tag order
        # Create mapping of tag to original index
        tag_to_index = {id(tag): i for i, tag in enumerate(tags_list)}
        results_sorted = sorted(results, key=lambda r: tag_to_index.get(id(r.tag), 0))
        
        # Log summary
        success_count = sum(1 for r in results_sorted if r.success)
        failure_count = len(results_sorted) - success_count
        self.logger.info(
            f"Write detailed completed: {success_count} succeeded, {failure_count} failed "
            f"(total: {len(results_sorted)} tags)"
        )
        
        return results_sorted

    def _parse_write_response_detailed(
        self, bytes_response: bytes, tags: List[S7Tag]
    ) -> List[WriteResult]:
        """Parse write response and return detailed results for each tag.
        
        Unlike the standard parse that raises on first error, this collects
        all results and returns them.
        """
        from .constants import WRITE_RES_OVERHEAD, ReturnCode
        from .responses import _return_code_name
        
        results = []
        offset = WRITE_RES_OVERHEAD
        
        for tag in tags:
            try:
                return_code = struct.unpack_from(">B", bytes_response, offset)[0]
                offset += 1
                
                if return_code == ReturnCode.SUCCESS.value:
                    results.append(WriteResult(tag=tag, success=True))
                else:
                    error_name = _return_code_name(return_code)
                    results.append(
                        WriteResult(
                            tag=tag,
                            success=False,
                            error=f"PLC returned error: {error_name}",
                            error_code=return_code
                        )
                    )
            except Exception as e:
                # Parsing error for this tag
                results.append(
                    WriteResult(
                        tag=tag,
                        success=False,
                        error=f"Failed to parse response: {str(e)}"
                    )
                )
        
        return results

    def _parse_read_response_detailed(
        self,
        bytes_response: bytes,
        tags: List[S7Tag],
        tags_map: Optional[Dict[S7Tag, S7Tag]] = None
    ) -> List[ReadResult]:
        """Parse read response and return detailed results for each tag.
        
        Unlike the standard parse that raises on first error, this collects
        all results and returns them.
        
        Args:
            bytes_response: Raw response bytes from PLC
            tags: List of tags that were requested
            tags_map: Optional mapping for optimized reads (merged tags)
        
        Returns:
            List of ReadResult objects, one per tag
        """
        from .constants import READ_RES_OVERHEAD, ReturnCode
        from .responses import _return_code_name
        
        results = []
        offset = READ_RES_OVERHEAD
        
        for tag in tags:
            try:
                # Read return code
                return_code = struct.unpack_from(">B", bytes_response, offset)[0]
                offset += 1
                
                if return_code == ReturnCode.SUCCESS.value:
                    # Read transport size and length
                    transport_size = struct.unpack_from(">B", bytes_response, offset)[0]
                    offset += 1
                    length_bytes = struct.unpack_from(">H", bytes_response, offset)[0]
                    offset += 2
                    
                    # Calculate actual data length
                    if transport_size in (0x03, 0x04, 0x05):  # BIT, BYTE, CHAR
                        data_length = (length_bytes + 7) // 8
                    else:
                        data_length = length_bytes // 8
                    
                    # Extract data bytes
                    data_bytes = bytes_response[offset:offset + data_length]
                    offset += data_length
                    
                    # Handle fill byte for odd lengths
                    if data_length % 2 != 0:
                        offset += 1
                    
                    # Parse value based on data type
                    try:
                        value = self._parse_tag_value(tag, data_bytes, tags_map)
                        results.append(ReadResult(tag=tag, success=True, value=value))
                    except Exception as e:
                        results.append(
                            ReadResult(
                                tag=tag,
                                success=False,
                                error=f"Failed to parse value: {str(e)}"
                            )
                        )
                else:
                    # Error return code - no data follows, just add fill byte for alignment
                    error_name = _return_code_name(return_code)
                    results.append(
                        ReadResult(
                            tag=tag,
                            success=False,
                            error=f"PLC returned error: {error_name}",
                            error_code=return_code
                        )
                    )
                    # Add fill byte for alignment after single-byte return code
                    offset += 1
            
            except Exception as e:
                # Parsing error for this tag
                results.append(
                    ReadResult(
                        tag=tag,
                        success=False,
                        error=f"Failed to parse response: {str(e)}"
                    )
                )
        
        return results

    def _parse_tag_value(
        self,
        tag: S7Tag,
        data_bytes: bytes,
        tags_map: Optional[Dict[S7Tag, S7Tag]] = None
    ) -> Value:
        """Parse tag value from data bytes.
        
        Args:
            tag: The tag being parsed
            data_bytes: Raw data bytes for this tag
            tags_map: Optional mapping for optimized reads
        
        Returns:
            Parsed value
        """
        from .responses import (
            _parse_string,
            _parse_wstring,
            extract_bit_from_byte
        )
        
        # Handle bit extraction for BIT type or from larger types
        if tag.data_type == DataType.BIT:
            # For non-optimized BIT reads, PLC returns the bit value directly (0 or 1)
            return bool(data_bytes[0])
        
        # Handle string types
        if tag.data_type == DataType.STRING:
            return _parse_string(data_bytes, 0, tag.length)
        
        if tag.data_type == DataType.WSTRING:
            return _parse_wstring(data_bytes, 0, tag.length)
        
        # Handle arrays (length > 1)
        if tag.length > 1:
            values: List[Union[int, float]] = []
            item_size = tag.data_type.value
            
            for i in range(tag.length):
                item_bytes = data_bytes[i * item_size:(i + 1) * item_size]
                
                if tag.data_type == DataType.BYTE:
                    values.append(int(struct.unpack('>B', item_bytes)[0]))
                elif tag.data_type == DataType.INT:
                    values.append(int(struct.unpack('>h', item_bytes)[0]))
                elif tag.data_type == DataType.WORD:
                    values.append(int(struct.unpack('>H', item_bytes)[0]))
                elif tag.data_type == DataType.DINT:
                    values.append(int(struct.unpack('>i', item_bytes)[0]))
                elif tag.data_type == DataType.DWORD:
                    values.append(int(struct.unpack('>I', item_bytes)[0]))
                elif tag.data_type == DataType.REAL:
                    values.append(float(struct.unpack('>f', item_bytes)[0]))
            
            return tuple(values)
        
        # Handle single numeric types (length == 1)
        if tag.data_type == DataType.BYTE:
            return int(struct.unpack('>B', data_bytes)[0])
        
        if tag.data_type == DataType.CHAR:
            return str(struct.unpack('>c', data_bytes)[0].decode('ascii'))
        
        if tag.data_type == DataType.INT:
            return int(struct.unpack('>h', data_bytes)[0])
        
        if tag.data_type == DataType.WORD:
            return int(struct.unpack('>H', data_bytes)[0])
        
        if tag.data_type == DataType.DINT:
            return int(struct.unpack('>i', data_bytes)[0])
        
        if tag.data_type == DataType.DWORD:
            return int(struct.unpack('>I', data_bytes)[0])
        
        if tag.data_type == DataType.REAL:
            return float(struct.unpack('>f', data_bytes)[0])
        
        raise ValueError(f"Unsupported data type for parsing: {tag.data_type}")

    def batch_write(
        self,
        auto_commit: bool = True,
        rollback_on_error: bool = True
    ) -> BatchWriteTransaction:
        """Create a batch write transaction for atomic multi-tag writes.
        
        Allows grouping multiple write operations with optional automatic
        rollback on failure.
        
        Args:
            auto_commit: If True, commit automatically when context exits.
                Default True.
            rollback_on_error: If True, restore original values if any write
                fails. Default True.
        
        Returns:
            BatchWriteTransaction context manager
        
        Example:
            >>> # Automatic commit with rollback on error
            >>> with client.batch_write() as batch:
            ...     batch.add('DB1,I0', 100)
            ...     batch.add('DB1,I2', 200)
            ...     batch.add('DB1,I4', 300)
            
            >>> # Manual commit without rollback
            >>> with client.batch_write(auto_commit=False, rollback_on_error=False) as batch:
            ...     batch.add('DB1,I0', 100)
            ...     batch.add('DB1,I2', 200)
            ...     results = batch.commit()
            ...     if all(r.success for r in results):
            ...         print("All writes succeeded")
            
            >>> # Method chaining
            >>> with client.batch_write() as batch:
            ...     batch.add('DB1,I0', 100).add('DB1,I2', 200).add('DB1,I4', 300)
        """
        return BatchWriteTransaction(
            client=self,
            auto_commit=auto_commit,
            rollback_on_error=rollback_on_error
        )

    def get_cpu_status(self) -> str:
        """Get the current CPU operating status (RUN or STOP).

        Returns:
            str: The CPU status. Possible values:
                - "RUN": CPU is running
                - "STOP": CPU is stopped

        Raises:
            S7CommunicationError: If not connected to PLC or communication fails.

        Example:
            >>> client = S7Client('192.168.100.10', 0, 1)
            >>> client.connect()
            >>> status = client.get_cpu_status()
            >>> print(f"CPU is in {status} mode")
            CPU is in RUN mode
        """
        if not self.is_connected:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before getting CPU status."
            )

        # Request SZL ID 0x0424 (CPU diagnostic status)
        self.logger.debug("Requesting CPU diagnostic status (SZL ID 0x0424)")
        szl_request = SZLRequest(szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000)
        bytes_response = self.__send(szl_request)

        # Parse the response and extract CPU status
        szl_response = SZLResponse(response=bytes_response)
        cpu_status = szl_response.parse_cpu_status()
        self.logger.debug(f"CPU status: {cpu_status}")
        return cpu_status

    def get_cpu_info(self) -> Dict[str, Any]:
        """Get detailed CPU information including model, hardware/firmware versions.

        Returns:
            Dict[str, Any]: Dictionary containing CPU information with keys:
                - module_type_name: Full order number (e.g., "6ES7 211-1BE40-0XB0")
                - hardware_version: Hardware version (e.g., "V0.14")
                - firmware_version: Firmware version (e.g., "V32.32")
                - index: Module index (hex string)
                - modules: List of all detected modules (if multiple)

        Raises:
            S7CommunicationError: If not connected to PLC or communication fails.

        Example:
            >>> client = S7Client('192.168.100.10', 0, 1)
            >>> client.connect()
            >>> info = client.get_cpu_info()
            >>> print(f"CPU Model: {info['module_type_name']}")
            >>> print(f"Firmware: {info['firmware_version']}")
            CPU Model: 6ES7 211-1BE40-0XB0
            Firmware: V32.32
        """
        if not self.is_connected:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before getting CPU info."
            )

        # Request SZL ID 0x0011 (Module Identification)
        szl_request = SZLRequest(szl_id=SZLId.MODULE_IDENTIFICATION, szl_index=0x0000)
        bytes_response = self.__send(szl_request)

        # Parse the response and extract CPU info
        szl_response = SZLResponse(response=bytes_response)
        return szl_response.parse_cpu_info()

    def __send(self, request: Request) -> bytes:
        if not isinstance(request, Request):
            raise ValueError(f"Request type {type(request).__name__} not supported")

        if self.socket is None:
            raise S7CommunicationError("Socket is not initialized. Call connect() first.")
        try:
            with self._io_lock:
                request_data = request.serialize()
                self.logger.debug(
                    f"TX -> PLC: {len(request_data)} bytes "
                    f"[TPKT+COTP+S7]"
                )
                self.socket.sendall(request_data)

                header = self._recv_exact(TPKT_SIZE)
                self.logger.debug(f"RX <- PLC: TPKT header {header.hex()}")
                if len(header) < 4:
                    raise S7CommunicationError(
                        "Incomplete TPKT header received from the PLC."
                    )

                tpkt_length = int.from_bytes(header[2:4], byteorder="big")
                if tpkt_length < 4:
                    raise S7CommunicationError("Invalid TPKT length received from the PLC.")

                body = self._recv_exact(tpkt_length - 4)
                self.logger.debug(f"Received {len(body)} bytes body (total packet: {tpkt_length} bytes)")

                return header + body
        except socket.timeout as e:
            self.logger.error("Socket timeout during communication")
            raise S7TimeoutError(
                f"Communication timeout after {self.timeout}s"
            ) from e
        except socket.error as e:
            self.logger.error(f"Socket error during communication: {e}")
            raise S7CommunicationError(
                f"Socket error during communication: {e}."
            ) from e

    def _recv_exact(self, expected_length: int) -> bytes:
        if self.socket is None:
            raise S7CommunicationError("Socket is not initialized. Call connect() first.")

        if expected_length == 0:
            return b""

        data = bytearray()

        while len(data) < expected_length:
            chunk = self.socket.recv(expected_length - len(data))
            if len(chunk) == 0:
                raise S7CommunicationError(
                    "The connection has been closed by the peer."
                )

            data.extend(chunk)

        return bytes(data)
