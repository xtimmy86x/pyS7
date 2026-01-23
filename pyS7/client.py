import logging
import socket
import struct
import threading
from types import TracebackType
from typing import Any, Dict, List, Optional, Sequence, Type, Union, cast

from .address_parser import map_address_to_tag
from .constants import (
    COTP_SIZE,
    MAX_JOB_CALLED,
    MAX_JOB_CALLING,
    MAX_PDU,
    TPKT_SIZE,
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
        if self.socket is None:
            return False
        try:
            # Try to get socket options to verify if socket is still valid
            self.socket.getpeername()
            return True
        except (OSError, AttributeError):
            # Socket is closed or invalid
            return False

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
            self.socket = None
            self.logger.error(f"Connection timeout to {self.address}:{self.port}: {e}")
            raise S7TimeoutError(
                f"Connection timeout to {self.address}:{self.port} after {self.timeout}s"
            ) from e
        except socket.error as e:
            self.socket = None
            self.logger.error(f"Failed to connect to {self.address}:{self.port}: {e}")
            raise S7ConnectionError(
                f"Failed to connect to {self.address}:{self.port}: {e}"
            ) from e

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
            pdu_negotation_request = PDUNegotiationRequest(max_pdu=self.pdu_size)
            self.logger.debug(f"Negotiating PDU size (requested: {self.pdu_size} bytes)")
            pdu_negotation_bytes_response: bytes = self.__send(pdu_negotation_request)
            pdu_negotiation_response = PDUNegotiationResponse(
                response=pdu_negotation_bytes_response
            )

            (
                self.max_jobs_calling,
                self.max_jobs_called,
                self.pdu_size,
            ) = pdu_negotiation_response.parse()
            self.logger.debug(
                f"Connected to PLC {self.address}:{self.port} - "
                f"PDU: {self.pdu_size} bytes, Jobs: {self.max_jobs_calling}/{self.max_jobs_called}"
            )
        except socket.timeout as e:
            self.logger.error(f"Connection timeout during COTP/PDU negotiation: {e}")
            self.disconnect()
            raise S7TimeoutError(
                f"Connection timeout during COTP/PDU negotiation after {self.timeout}s: {e}"
            ) from e
        except socket.error as e:
            self.logger.error(f"Socket error during connection setup: {e}")
            self.disconnect()
            raise S7ConnectionError(f"Socket error during connection setup: {e}") from e
        except S7ConnectionError:
            # Re-raise S7ConnectionError as-is
            self.disconnect()
            raise
        except S7CommunicationError as e:
            # Wrap S7CommunicationError in S7ConnectionError during connection phase
            self.logger.error(f"Communication error during connection setup: {e}")
            self.disconnect()
            raise S7ConnectionError(f"Communication error during connection setup: {e}") from e
        except (ValueError, struct.error) as e:
            # Protocol parsing errors
            self.logger.error(f"Protocol parsing error during connection setup: {e}")
            self.disconnect()
            raise S7ProtocolError(f"Invalid protocol response during connection setup: {e}") from e

    def disconnect(self) -> None:
        """Closes the TCP connection with the S7 PLC."""

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
