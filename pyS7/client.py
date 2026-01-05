import socket
import threading
from typing import Any, Dict, List, Optional, Sequence, Union

from .address_parser import map_address_to_tag
from .constants import MAX_JOB_CALLED, MAX_JOB_CALLING, MAX_PDU, ConnectionType, SZLId
from .errors import S7CommunicationError, S7ConnectionError
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
    """

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

        self.pdu_size: int = MAX_PDU
        self.max_jobs_calling: int = MAX_JOB_CALLING
        self.max_jobs_called: int = MAX_JOB_CALLED

        # Validate TSAP values if provided
        if local_tsap is not None or remote_tsap is not None:
            self._validate_tsap(local_tsap, remote_tsap)

    @staticmethod
    def tsap_from_string(tsap_str: str) -> int:
        """Convert Siemens TIA Portal TSAP notation to integer value.
        
        TIA Portal uses the format "XX.YY" where XX and YY are decimal bytes.
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
            byte1 = int(parts[0])
            byte2 = int(parts[1])
        except ValueError:
            raise ValueError(
                f"TSAP string must contain decimal numbers (e.g., '03.00'), got '{tsap_str}'"
            )
        
        if not 0 <= byte1 <= 255:
            raise ValueError(f"First byte must be in range 0-255, got {byte1}")
        if not 0 <= byte2 <= 255:
            raise ValueError(f"Second byte must be in range 0-255, got {byte2}")
        
        return (byte1 << 8) | byte2

    @staticmethod
    def tsap_to_string(tsap: int) -> str:
        """Convert TSAP integer value to Siemens TIA Portal notation.
        
        Converts an integer TSAP value to TIA Portal format "XX.YY".
        For example: 0x0300 = "03.00", 0x0301 = "03.01", 0x2200 = "22.00"
        
        Args:
            tsap: TSAP value as integer (0x0000 to 0xFFFF)
            
        Returns:
            str: TSAP string in format "XX.YY"
            
        Raises:
            ValueError: If TSAP value is out of range
            
        Example:
            >>> tsap_str = S7Client.tsap_to_string(0x0301)
            >>> print(tsap_str)  # "03.01"
        """
        if not isinstance(tsap, int):
            raise ValueError(f"tsap must be an integer, got {type(tsap).__name__}")
        if not 0x0000 <= tsap <= 0xFFFF:
            raise ValueError(
                f"tsap must be in range 0x0000-0xFFFF (0-65535), got 0x{tsap:04X} ({tsap})"
            )
        
        byte1 = (tsap >> 8) & 0xFF
        byte2 = tsap & 0xFF
        return f"{byte1:02d}.{byte2:02d}"

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
    def _validate_tsap(local_tsap: Optional[int], remote_tsap: Optional[int]) -> None:
        """Validate TSAP values are within valid ranges.
        
        Args:
            local_tsap: Local TSAP value (0x0000 to 0xFFFF)
            remote_tsap: Remote TSAP value (0x0000 to 0xFFFF)
            
        Raises:
            ValueError: If TSAP values are invalid
        """
        if local_tsap is not None:
            if not isinstance(local_tsap, int):
                raise ValueError(f"local_tsap must be an integer, got {type(local_tsap).__name__}")
            if not 0x0000 <= local_tsap <= 0xFFFF:
                raise ValueError(
                    f"local_tsap must be in range 0x0000-0xFFFF (0-65535), got 0x{local_tsap:04X} ({local_tsap})"
                )
        
        if remote_tsap is not None:
            if not isinstance(remote_tsap, int):
                raise ValueError(f"remote_tsap must be an integer, got {type(remote_tsap).__name__}")
            if not 0x0000 <= remote_tsap <= 0xFFFF:
                raise ValueError(
                    f"remote_tsap must be in range 0x0000-0xFFFF (0-65535), got 0x{remote_tsap:04X} ({remote_tsap})"
                )
        
        # If only one TSAP is provided, warn user
        if (local_tsap is None) != (remote_tsap is None):
            raise ValueError(
                "Both local_tsap and remote_tsap must be provided together, or neither. "
                f"Got local_tsap={local_tsap}, remote_tsap={remote_tsap}"
            )

    def connect(self) -> None:
        """Establishes a TCP connection to the S7 PLC and sets up initial communication parameters."""

        try:
            # Initialize the socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)

            # Establish TCP connection
            self.socket.connect((self.address, self.port))
        except (socket.timeout, socket.error) as e:
            self.socket = None
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
            connection_bytes_response: bytes = self.__send(connection_request)
            ConnectionResponse(response=connection_bytes_response)

            # Communication Setup
            pdu_negotation_request = PDUNegotiationRequest(max_pdu=self.pdu_size)
            pdu_negotation_bytes_response: bytes = self.__send(pdu_negotation_request)
            pdu_negotiation_response = PDUNegotiationResponse(
                response=pdu_negotation_bytes_response
            )

            (
                self.max_jobs_calling,
                self.max_jobs_called,
                self.pdu_size,
            ) = pdu_negotiation_response.parse()
        except Exception as e:
            self.disconnect()
            raise S7ConnectionError(f"Failed to complete connection setup: {e}") from e

    def disconnect(self) -> None:
        """Closes the TCP connection with the S7 PLC."""

        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except socket.error:
                ...
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
            return []

        if not self.socket:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before performing read operations."
            )
        
        data: List[Value] = []

        if optimize:
            requests, tags_map = prepare_optimized_requests(
                tags=list_tags, max_pdu=self.pdu_size
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

            data = response.parse()

        else:
            requests = prepare_requests(tags=list_tags, max_pdu=self.pdu_size)

            for request in requests:
                bytes_reponse = self.__send(ReadRequest(tags=request))
                read_response = ReadResponse(response=bytes_reponse, tags=request)

                data.extend(read_response.parse())

        return data

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
            return

        if not self.socket:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before performing write operations."
            )
        
        requests, requests_values = prepare_write_requests_and_values(
            tags=tags_list, values=values, max_pdu=self.pdu_size
        )

        for i, request in enumerate(requests):
            bytes_response = self.__send(
                WriteRequest(tags=request, values=requests_values[i])
            )
            response = WriteResponse(response=bytes_response, tags=request)
            response.parse()

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
        if not self.socket:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before getting CPU status."
            )
        
        # Request SZL ID 0x0424 (CPU diagnostic status)
        szl_request = SZLRequest(szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000)
        bytes_response = self.__send(szl_request)
        
        # Parse the response and extract CPU status
        szl_response = SZLResponse(response=bytes_response)
        return szl_response.parse_cpu_status()
    
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
        if not self.socket:
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

        assert self.socket, "Unreachable"
        try:
            with self._io_lock:
                self.socket.sendall(request.serialize())

                header = self._recv_exact(4)
                if len(header) < 4:
                    raise S7CommunicationError(
                        "Incomplete TPKT header received from the PLC."
                    )

                tpkt_length = int.from_bytes(header[2:4], byteorder="big")
                if tpkt_length < 4:
                    raise S7CommunicationError("Invalid TPKT length received from the PLC.")

                body = self._recv_exact(tpkt_length - 4)

                return header + body
        except socket.timeout as e:
            raise S7CommunicationError(
                "Socket timeout during communication."
            ) from e
        except socket.error as e:
            raise S7CommunicationError(
                f"Socket error during communication: {e}."
            ) from e

    def _recv_exact(self, expected_length: int) -> bytes:
        assert self.socket, "Unreachable"

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