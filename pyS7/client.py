import socket
from typing import Sequence

from .address_parser import map_address_to_item
from .constants import *
from .item import Item
from .requests import (ConnectionRequest, PDUNegotiationRequest, ReadRequest,
                       Request, group_items)
from .responses import (ConnectionResponse, PDUNegotiationResponse,
                        ReadOptimizedResponse, ReadResponse, Response)


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

    def read(self, items: Sequence[str | Item], optimize: bool = True) -> list:

        items: list[Item] = [map_address_to_item(address=item) if isinstance(item, str) else item for item in items] 

        if optimize:
            items_map = group_items(items=items, pdu_size=self.pdu_size)
            items = list(items_map.keys())

        requests: list[list[Item]] = [[]]
        read_size_counter: int = READ_REQ_HEADER_SIZE + \
            READ_REQ_PARAM_SIZE_NO_ITEMS  # 10 + 2

        for item in items:
            if item.size() + READ_REQ_HEADER_SIZE + READ_REQ_PARAM_SIZE_NO_ITEMS + READ_REQ_PARAM_SIZE_ITEM >= self.pdu_size:
                raise Exception(
                    f"{item} too big -> it cannot fit the size of the negotiated PDU ({self.pdu_size})")

            elif item.size() + read_size_counter + READ_REQ_PARAM_SIZE_ITEM < self.pdu_size and len(requests[-1]) < MAX_READ_ITEMS:
                requests[-1].append(item)
                read_size_counter += item.size() + READ_REQ_PARAM_SIZE_ITEM

            else:
                requests.append([item])
                read_size_counter = READ_REQ_HEADER_SIZE + READ_REQ_PARAM_SIZE_NO_ITEMS

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

    def __send(self, request: Request) -> bytes:

        if not isinstance(request, Request):
            raise ValueError(
                f"Request type {type(request).__name__} not supported")

        self.socket.send(request.serialize())

        bytes_response = self.socket.recv(self.pdu_size)

        return bytes_response

    def __del__(self) -> None:

        self.socket.close()
