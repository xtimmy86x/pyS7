# pyS7

Welcome to pyS7, a lightweight, pure Python library designed for efficient data retrieval from Siemens PLCs. Using the Siemens S7 Communication protocol over ISO-on-TCP (RFC1006), it enables effortless and streamlined interaction with S7 PLCs.

Key Features:

* *Pure Python*: No external dependencies for easy setup and platform compatibility.

* *User-friendly*, High-Level API: Intuitive and straightforward, offering simplicity and efficiency in reading multiple variables.

* *Multi-Variable Reading*: Enhanced support for simultaneous multi-variable reading, making your data retrieval tasks more efficient.

## Install

## Example

```python
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
        item0, item1, item2, item3, 
        item4, item5, item6, item7
    ]

    data = client.read(items=items)
    print(data)
```