from pyS7 import Client, DataType, Item, MemoryArea

if __name__ == "__main__":

    # Create a new Client object to connect to S7-300/400/1200/1500 PLC.
    # Provide the PLC's IP address and slot/rack information
    client = Client(address="192.168.5.100", rack=0, slot=1)

    # Establish connection with the PLC
    client.connect()

    # Using Item provides greater flexibility and is recommended when there's a high number of items
    # Define a list of items to read from the PLC.
    # Each item is an instance of the Item class with parameters specifying the memory area,
    # datablock number, data type, start index, bit index and length.
    items = [
        Item(MemoryArea.DB, 1, DataType.BIT, 0, 6, 1),      # Read bit 6 of DB1
        Item(MemoryArea.DB, 1, DataType.INT, 30, 0, 1),     # Read INT at address 30 of DB1
        Item(MemoryArea.DB, 1, DataType.INT, 32, 0, 1),     # Read INT at address 32 of DB1
        Item(MemoryArea.DB, 1, DataType.INT, 34, 0, 1),     # Read INT at address 34 of DB1
        Item(MemoryArea.DB, 1, DataType.INT, 36, 0, 1),     # Read INT at address 36 of DB1
        Item(MemoryArea.DB, 1, DataType.INT, 38, 0, 1),     # Read INT at address 38 of DB1
        Item(MemoryArea.DB, 1, DataType.REAL, 64, 0, 1),    # Read REAL at address 64 of DB1
        Item(MemoryArea.DB, 1, DataType.REAL, 68, 0, 1),    # Read REAL at address 68 of DB1
        Item(MemoryArea.DB, 1, DataType.REAL, 72, 0, 4),    # Read array of 4 REAL at address 72 of DB1
        Item(MemoryArea.DB, 1, DataType.CHAR, 102, 0, 37),  # Read string of 37 CHARs starting at address 102 of DB1
    ]

    # Read the data from the PLC using the specified items list
    data = client.read(items=items)

    print(data)  # [True, -32768, -1234, 32767, 1234, -3402823106560.0, (-1.1754943806535634e-12, 0.0, 1.1754943508222875e-38, 1.1754943806535634e-12), -1.7549434765121066e-30, 'the brown fox jumps over the lazy dog']
