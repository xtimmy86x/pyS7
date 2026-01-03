"""
#######################################################################
# This code serves as an illustrative example demonstrating how
# to configure and handle a Logo! connection.
# 
#######################################################################
"""
from pyS7 import S7Client

if __name__ == "__main__":
    # Create a new S7Client object to connect to Siemens Logo! PLC.
    # Provide the PLC's IP address and localTSAP/remoteTSAP information
    # Remember that the TSAPs are crossed : Local TSAP PC-side is the Remote TSAP PLC-Side and vice-versa.
    # In over words, remote TSAP is the TSAP of PLC you want to connect to.
    client = S7Client(address="192.168.5.100", local_tsap="03.00", remote_tsap="22.00")

    # Establish connection with the PLC
    client.connect()

    # Define area tags to read.
    # To read/write data to Logo! use DB1 as MemoryArea.
    tags = [
        'DB1,X0.0',
        'DB1,WORD17',
    ]
    result = client.read(tags)
    print(result)