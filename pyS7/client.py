import socket
from typing import Sequence

from .address_parser import map_address_to_item
from .constants import MAX_JOB_CALLED, MAX_JOB_CALLING, MAX_PDU, MAX_WRITE_ITEMS
from .item import Item
from .requests import (ConnectionRequest, PDUNegotiationRequest, ReadRequest,
                       Request, WriteRequest, group_items, prepare_requests)
from .responses import (ConnectionResponse, PDUNegotiationResponse,
                        ReadOptimizedResponse, ReadResponse, Response, WriteResponse)


class Client:

    def __init__(self, address: str, rack: int, slot: int, port: int = 1102, timeout: float = 5) -> None:

        self.address = address
        self.rack = rack
        self.slot = slot
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(timeout)

        self.pdu_size: int = MAX_PDU
        self.max_jobs_calling: int = MAX_JOB_CALLING
        self.max_jobs_called: int = MAX_JOB_CALLED
        self.current_jobs: int = 0

    def connect(self) -> None:

        # Establish TCP connection
        self.socket.connect((self.address, self.port))

        # Do I need this?
        connection_bytes_response: bytes = self.__send(
            ConnectionRequest(rack=self.rack, slot=self.slot))
        connection_response: ConnectionResponse = ConnectionResponse(
            response=connection_bytes_response)

        # Communication Setup
        pdu_negotation_bytes_response: bytes = self.__send(
            PDUNegotiationRequest(max_pdu=self.pdu_size))
        pdu_negotiation_response = PDUNegotiationResponse(
            response=pdu_negotation_bytes_response)

        self.max_jobs_calling, self.max_jobs_called, self.pdu_size = pdu_negotiation_response.parse()

    def disconnect(self) -> None:

        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

    def read(self, items: Sequence[str | Item], optimize: bool = True) -> list[bool | int | float | str | tuple[bool | int | float, ...]]:

        items: list[Item] = [map_address_to_item(address=item) if isinstance(
            item, str) else item for item in items]

        if optimize:
            items_map = group_items(items=items, pdu_size=self.pdu_size)
            items = list(items_map.keys())

        requests: list[list[Item]] = prepare_requests(
            items=items, max_pdu=self.pdu_size)

        data = []
        for request in requests:
            bytes_reponse = self.__send(ReadRequest(items=request))

            if optimize:
                response: Response = ReadOptimizedResponse(
                    response=bytes_reponse, items_map=items_map)
            else:
                response = ReadResponse(response=bytes_reponse, items=request)

            data.extend(response.parse())

        return data
    
    def write(self, items: Sequence[str | Item], values: Sequence[bool | int | float | str]) -> None:
        
        items: list[Item] = [map_address_to_item(address=item) if isinstance(
            item, str) else item for item in items]

        requests: list[list[Item]] = [items[i:i + MAX_WRITE_ITEMS] for i in range(0, len(items), MAX_WRITE_ITEMS)]

        for request in requests:
            bytes_response = self.__send(WriteRequest(items=request, values=values))
            print(bytes_response)
            response = WriteResponse(response=bytes_response, items=items)
            response.parse() # Raise error if any

    def __send(self, request: Request) -> bytes:

        if not isinstance(request, Request):
            raise ValueError(
                f"Request type {type(request).__name__} not supported")
        
        self.socket.send(request.serialize())

        bytes_response = self.socket.recv(self.pdu_size)

        return bytes_response

    def __del__(self) -> None:

        self.disconnect()
