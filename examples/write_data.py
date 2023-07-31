from pyS7 import Client, DataType, Item, MemoryArea

if __name__ == "__main__":

    # Create a new Client object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = Client(address="192.168.5.100", rack=0, slot=1)

    # Establish connection with the PLC
    client.connect()

    # Define area tags to write
    items = [
        "DB1,X0.0",     # => Item(MemoryArea.DB, 1, DataType.BIT, 0, 0, 1) - BIT 0 (first bit) of DB1
        "DB1,X0.6",     # => Item(MemoryArea.DB, 1, DataType.BIT, 0, 6, 1) - BIT 7 (7th bit) of DB1
        "DB1,I30",      # => Item(MemoryArea.DB, 1, DataType.INT, 30, 0, 1) - INT at address 30 of DB1
        "M54.4",        # => Item(MemoryArea.MERKER, 0, DataType.BIT, 4, 4, 1) - BIT 4 (fifth bit) in the merker (memento) area
        "IW22",         # => Item(MemoryArea.INPUT, 0, DataType.WORD, 22, 0, 1) - WORD at address 22 in input area
        "QR24",         # => Item(MemoryArea.OUTPUT, 0, DataType.REAL, 24, 0, 1) - REAL at address 24 in output area
        "DB1,S10.5",    # => Item(MemoryArea.DB, 1, DataType.CHAR, 10, 0, 5) - Sequence of CHAR (string) of length 5 starting at address 10 of DB1
        Item(memory_area=MemoryArea.DB, db_number=5, data_type=DataType.REAL, start=50, bit_offset=0, length=3) # => Sequence of REAL of length 3 starting at address 50 of DB5 
    ]

    # Defines values to write
    values = [
        False,
        True,
        25000,
        True,
        120,
        1.2345,
        "Hello",
        (3.14, 6.28, 9.42)
    ]

    # Write data to the PLC using items and values
    client.write(items=items, values=values)
