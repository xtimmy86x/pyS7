import socket
from typing import List, Optional, Sequence, Union

from .address_parser import map_address_to_tag
from .constants import MAX_JOB_CALLED, MAX_JOB_CALLING, MAX_PDU, ConnectionType
from .errors import S7CommunicationError, S7ConnectionError
from .requests import (
    ConnectionRequest,
    PDUNegotiationRequest,
    ReadRequest,
    Request,
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
    Response,
    WriteResponse,
)
from .tag import S7Tag


class S7Client:
    """The S7Client class provides a high-level interface for communicating with a Siemens S7 programmable logic controller (PLC) over a network connection.
    It allows for reading from and writing to memory locations in the PLC, with support for a variety of data types.

    Attributes:
        address (str): The IP address of the PLC.
        rack (int): The rack number of the PLC.
        slot (int): The slot number of the PLC.
        connection_type (ConnectionType): The type of PLC connection (S7Basic, PG, OP). Default is ConnectionType.S7Basic.
        port (int): The port number for the network connection. Defaults to 102.
        timeout (int): The timeout in seconds for the network connection. Defaults to 5.
    """

    def __init__(
        self,
        address: str,
        rack: int,
        slot: int,
        connection_type: ConnectionType = ConnectionType.S7Basic,
        port: int = 102,
        timeout: float = 5.0,
    ) -> None:
        self.address = address
        self.rack = rack
        self.slot = slot
        self.connection_type = connection_type
        self.port = port
        self.timeout = timeout

        self.socket: Optional[socket.socket] = None

        self.pdu_size: int = MAX_PDU
        self.max_jobs_calling: int = MAX_JOB_CALLING
        self.max_jobs_called: int = MAX_JOB_CALLED

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
                connection_type=self.connection_type, rack=self.rack, slot=self.slot
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

        if not self.socket:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before performing read operations."
            )

        list_tags: List[S7Tag] = [
            map_address_to_tag(address=tag) if isinstance(tag, str) else tag
            for tag in tags
        ]

        data: List[Value] = []

        if optimize:
            requests, tags_map = prepare_optimized_requests(
                tags=list_tags, max_pdu=self.pdu_size
            )

            bytes_reponse = self.__send(ReadRequest(tags=requests[0]))
            response: Response = ReadOptimizedResponse(
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
                response = ReadResponse(response=bytes_reponse, tags=request)

                data.extend(response.parse())

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

        if not self.socket:
            raise S7CommunicationError(
                "Not connected to PLC. Call 'connect' before performing write operations."
            )

        if len(tags) != len(values):
            raise ValueError(
                "The number of tags should be equal to the number of values."
            )

        tags_list: List[S7Tag] = [
            map_address_to_tag(address=tag) if isinstance(tag, str) else tag
            for tag in tags
        ]

        requests, requests_values = prepare_write_requests_and_values(
            tags=tags_list, values=values, max_pdu=self.pdu_size
        )

        for i, request in enumerate(requests):
            bytes_response = self.__send(
                WriteRequest(tags=request, values=requests_values[i])
            )
            response = WriteResponse(response=bytes_response, tags=request)
            response.parse()

    def __send(self, request: Request) -> bytes:
        if not isinstance(request, Request):
            raise ValueError(f"Request type {type(request).__name__} not supported")

        assert self.socket, "Unreachable"
        try:
            self.socket.send(request.serialize())

            bytes_response = self.socket.recv(self.pdu_size)
            if len(bytes_response) == 0:
                raise S7CommunicationError(
                    "The connection has been closed by the peer."
                )

            return bytes_response
        except socket.error as e:
            raise S7CommunicationError(
                f"Socket error during communication: {e}."
            ) from e
