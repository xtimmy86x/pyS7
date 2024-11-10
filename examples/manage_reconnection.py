"""
#######################################################################
# This code serves as an illustrative example demonstrating how 
# to handle unexpected disconnections when interacting with
# a Siemens PLC using the pyS7 library.
#######################################################################
"""

import time
from pyS7 import S7Client, S7ConnectionError, S7CommunicationError


def attempt_connection(client: S7Client) -> None:
    """Recursively tries to connect to the PLC client in case of an error."""

    try:
        client.connect()
    except S7ConnectionError as e:
        print(e)
        time.sleep(5)
        attempt_connection(client)


if __name__ == "__main__":
    # Create a new S7Client object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = S7Client(address="192.168.5.100", rack=0, slot=1)

    # Define area tags to read
    tags = ["DB1,X0.0", "DB1,X0.1", "DB2,I2"]

    # Attempt to establish a connection to the PLC client.
    attempt_connection(client)

    # Start an infinite loop to continuously read from the PLC client.
    while True:
        try:
            print(client.read(tags))
            time.sleep(1)
        except S7CommunicationError as e:
            print(e)
            # If the connection is unexpectedly closed, or any other error, attempt to reconnect.
            attempt_connection(client)
