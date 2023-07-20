# pyS7

Welcome to pyS7, a lightweight, pure Python library designed for efficient data retrieval from Siemens PLCs. Using the Siemens S7 Communication protocol over ISO-on-TCP (RFC1006), it enables effortless and streamlined interaction with S7 PLCs.

Key Features:

* *Pure Python*: No external dependencies for easy setup and platform compatibility.

* *User-friendly*, High-Level API: Intuitive and straightforward, offering simplicity and efficiency in reading multiple variables.

* *Multi-Variable Reading*: Enhanced support for simultaneous multi-variable reading, making your data retrieval tasks more efficient.

## Install

## Example

```python
from pyS7 import Client

if __name__ == "__main__":

    # Create a new Client object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = Client(address="192.168.5.100", rack=0, slot=1)

    # Establish connection with the PLC
    client.connect()

    # Define area tags to read
    items = [
        "DB1,X0.0",     # Read BIT 0 (first bit) of DB1
        "DB1,X0.6",     # Read BIT 7 (7th bit) of DB1
        "DB1,I30",      # Read INT at address 30 of DB1
        "M54.4",        # Read BIT 4 (fifth bit) in the merker (memento) area
        "IW22",         # Read WORD at address 22 in input area
        "QR24",         # Read REAL at address 24 in output area
        "DB1,S10.5"     # Read sequence of CHAR of length 5 starting at address 10 of DB1
    ]

    # Read the data from the PLC using the specified items list
    data = client.read(items=items)

    print(data)  # [True, False, 123, True, 10, -2.54943805634653e-12, 'Hello']
```

Look at the examples folder for more self-explanatory examples. 