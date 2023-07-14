from enum import Enum

MAX_PDU = 960
MAX_JOB_CALLING = 8
MAX_JOB_CALLED = 8

MAX_READ_ITEMS = 20

READ_REQ_HEADER_SIZE = 10
READ_REQ_PARAM_SIZE_NO_ITEMS = 2
READ_REQ_PARAM_SIZE_ITEM = 12


class MessageType(Enum):
    REQUEST = 1
    ACK = 2
    RESPONSE = 3
    USERDATA = 7


class Function(Enum):
    COMM_SETUP = 240
    READ_VAR = 4
    WRITE_VAR = 5


class MemoryArea(Enum):
    MERKER = 0x83   # Flags (M) (Merker)
    DB = 0x84       # Data blocks (DB)
    INPUT = 0x81    # Inputs (I)
    OUTPUT = 0x82   # Outputs (Q)
    COUNTER = 0x1c  # S7 counters (C)
    TIMER = 0x1d    # S7 timers (C)


class DataType(Enum):
    BIT = 1     # bit
    BYTE = 2    # byte
    CHAR = 3    #
    WORD = 4    # Unsigned INT 16 bit
    INT = 5     # Signed INT 16 bit
    DWORD = 6   # Unsigned INT 32 bit
    DINT = 7    # Signed INT 32 bit
    REAL = 8    # FLOAT 32 bit


DataTypeSize: dict[DataType, int] = {
    DataType.BIT: 1,
    DataType.BYTE: 1,
    DataType.CHAR: 1,
    DataType.WORD: 2,
    DataType.INT: 2,
    DataType.DWORD: 4,
    DataType.DINT: 4,
    DataType.REAL: 4,
}
