from pyS7 import Client, Item, MemoryArea, DataType

if __name__ == "__main__":

    client = Client(address="localhost", rack=0, slot=1)
    client.connect()

    item0 = Item(MemoryArea.DB, 1, DataType.INT, 34, 0, 1)
    item1 = Item(MemoryArea.DB, 1, DataType.INT, 30, 0, 1)
    item2 = Item(MemoryArea.DB, 1, DataType.INT, 32, 0, 1)
    item3 = Item(MemoryArea.DB, 1, DataType.INT, 38, 0, 1)
    item4 = Item(MemoryArea.DB, 1, DataType.INT, 36, 0, 1)
    item5 = Item(MemoryArea.DB, 1, DataType.REAL, 64, 0, 1)
    item6 = Item(MemoryArea.DB, 1, DataType.REAL, 72, 0, 4)
    item7 = Item(MemoryArea.DB, 1, DataType.REAL, 68, 0, 1)


    items = [
        item0,
        item1,
        item2,
        item3,
        item4,
        item5,
        item6,
        item7,
    ]

    data = client.read(items=items, optimize=True)
    print(data) # [0, -32768, -1234, 32767, 1234, -3402823106560.0, (-1.1754943806535634e-12, 0.0, 1.1754943508222875e-38, 1.1754943806535634e-12), -1.7549434765121066e-30]


