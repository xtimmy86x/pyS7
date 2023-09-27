"""
#######################################################################
# This code serves as an illustrative example demonstrating how 
# to handle unexpected disconnections when interacting with
# a Siemens PLC using the pyS7 library.
#######################################################################
"""

import socket
import time
import pyS7
from pyS7 import Client

def attempt_connection(client: Client) -> None:
    """Recursively tries to connect to the PLC client in case of a socket error."""
    
    try:
        client.connect()
    except socket.error as e:
        print(e)
        time.sleep(5)
        attempt_connection(client)    

if __name__ == "__main__":

    # Create a new Client object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = Client(address="192.168.5.100", rack=0, slot=1)
    
    # Define area tags to read
    items = ['DB1,X0.0', 'DB1,X0.1', 'DB2,I2']

    # Attempt to establish a connection to the PLC client.
    attempt_connection(client)

    # Start an infinite loop to continuously read from the PLC client.
    while True:
        try:
            print(client.read(items))
            time.sleep(1)
        except pyS7.errors.ConnectionClosed:
            # If the connection is unexpectedly closed, attempt to reconnect.
            attempt_connection(client)
        except socket.error as e:
            # If any other socket error occurs, attempt to reconnect.
            attempt_connection(client)
