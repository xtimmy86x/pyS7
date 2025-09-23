"""
#######################################################################
# The following code is meant for demonstration purposes only.
# In a real-world application, you should use the S7Client class,
# which provides a high-level interface to interact
# with S7 devices and ensures proper handling of resources.
#######################################################################
"""

import socket

from pyS7 import S7Tag, map_address_to_tag
from pyS7.requests import PDUNegotiationRequest, ReadRequest
from pyS7.responses import PDUNegotiationResponse, ReadResponse

if __name__ == "__main__":
    address: str = "192.168.5.100"
    port: int = 102

    addresses = [
        "DB1,X0.0",
        "DB1,X0.6",
        "DB1,I30",
        "M54.4",
        "IW22",
        "QR24",
        "DB1,S10.5",
    ]

    socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    #####################################################
    ############# ESTABLISH CONNECTION ##################
    #####################################################

    # Establish TCP connection
    socket.connect((address, port))

    # Setup Communication -> request
    negotiation_request = PDUNegotiationRequest(max_pdu=960)
    socket.sendall(negotiation_request.serialize())

    # Setup Communication -> ack
    negotiation_bytes_response: bytes = socket.recv(980)
    negotiation_response = PDUNegotiationResponse(response=negotiation_bytes_response)

    # Extract negotiated pdu...
    max_jobs_calling, max_jobs_called, pdu_size = negotiation_response.parse()

    #####################################################
    ################# READ REQUEST ######################
    #####################################################

    # Make sure to convert string addresses to tags
    tags: list[S7Tag] = [map_address_to_tag(addr) for addr in addresses]

    # Read
    read_request = ReadRequest(tags=tags)
    socket.sendall(read_request.serialize())

    # Read -> ack
    read_bytes_response: bytes = socket.recv(pdu_size)
    read_response = ReadResponse(response=read_bytes_response, tags=tags)

    data = read_response.parse()

    print(data)  # [True, False, 123, True, 10, -2.54943805634653e-12, 'Hello']
