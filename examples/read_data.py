from pyS7 import Client

if __name__ == "__main__":

    # Create a new Client object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = Client(address="192.168.5.100", rack=0, slot=1)

    # Establish connection with the PLC
    client.connect()

    # Define area tags to read
    items = [
        "DB1,X0.0",     # => Item(MemoryArea.DB, 1, DataType.BIT, 0, 0, 1) - Read BIT 0 (first bit) of DB1
        "DB1,X0.6",     # => Item(MemoryArea.DB, 1, DataType.BIT, 0, 6, 1) - Read BIT 7 (7th bit) of DB1
        "DB1,I30",      # => Item(MemoryArea.DB, 1, DataType.INT, 30, 0, 1) - Read INT at address 30 of DB1
        "M54.4",        # => Item(MemoryArea.MERKER, 0, DataType.BIT, 4, 4, 1) - Read BIT 4 (fifth bit) in the merker (memento) area
        "IW22",         # => Item(MemoryArea.INPUT, 0, DataType.WORD, 22, 0, 1) - Read WORD at address 22 in input area
        "QR24",         # => Item(MemoryArea.OUTPUT, 0, DataType.REAL, 24, 0, 1) - Read REAL at address 24 in output area
        "DB1,S10.5"     # => Item(MemoryArea.DB, 1, DataType.CHAR, 10, 0, 5) - Read sequence of CHAR of length 5 starting at address 10 of DB1
    ]

    # Read the data from the PLC using the specified items list
    data = client.read(items=items)

    print(data)  # [True, False, 123, True, 10, -2.54943805634653e-12, 'Hello']
