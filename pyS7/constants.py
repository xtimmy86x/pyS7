from enum import Enum
from typing import Dict

MAX_PDU = 960
MAX_JOB_CALLING = 8
MAX_JOB_CALLED = 8

MAX_READ_TAGS = 20
MAX_WRITE_TAGS = 20

TPKT_SIZE = 4
COTP_SIZE = 3

READ_REQ_HEADER_SIZE = 10
READ_REQ_PARAM_SIZE_NO_TAGS = 2
READ_REQ_PARAM_SIZE_TAG = 12
READ_REQ_OVERHEAD = (
    TPKT_SIZE + COTP_SIZE + READ_REQ_HEADER_SIZE + READ_REQ_PARAM_SIZE_NO_TAGS
)  # 3 + 4 + 10 + 2

READ_RES_HEADER_SIZE = 12
READ_RES_PARAM_SIZE_NO_TAGS = 2
READ_RES_PARAM_SIZE_TAG = 5
READ_RES_OVERHEAD = (
    TPKT_SIZE + COTP_SIZE + READ_RES_HEADER_SIZE + READ_RES_PARAM_SIZE_NO_TAGS
)  # 4 + 3 + 12 + 2

WRITE_REQ_HEADER_SIZE = 10
WRITE_REQ_PARAM_SIZE_NO_TAGS = 2
WRITE_REQ_PARAM_SIZE_TAG = 12
WRITE_REQ_OVERHEAD = (
    TPKT_SIZE + COTP_SIZE + WRITE_REQ_HEADER_SIZE + WRITE_REQ_PARAM_SIZE_NO_TAGS
)  # 3 + 4 + 10 + 2

WRITE_RES_HEADER_SIZE = 12
WRITE_RES_PARAM_SIZE = 2
WRITE_RES_OVERHEAD = (
    TPKT_SIZE + COTP_SIZE + WRITE_RES_HEADER_SIZE + WRITE_RES_PARAM_SIZE
)  # 3 + 4 + 12 + 2


class MessageType(Enum):
    REQUEST = 1
    ACK = 2
    RESPONSE = 3
    USERDATA = 7


class ConnectionType(int, Enum):
    PG = 1
    OP = 2
    S7Basic = 3


class Function(Enum):
    COMM_SETUP = 240
    READ_VAR = 4
    WRITE_VAR = 5


class MemoryArea(Enum):
    MERKER = 0x83  # Flags (M) (Merker)
    DB = 0x84  # Data blocks (DB)
    INPUT = 0x81  # Inputs (I)
    OUTPUT = 0x82  # Outputs (Q)
    COUNTER = 0x1C  # S7 counters (C)
    TIMER = 0x1D  # S7 timers (C)


class DataType(Enum):
    BIT = 1  # bit
    BYTE = 2  # byte
    CHAR = 3  # char
    WORD = 4  # unsigned INT 16 bit
    INT = 5  # signed INT 16 bit
    DWORD = 6  # unsigned INT 32 bit
    DINT = 7  # signed INT 32 bit
    REAL = 8  # FLOAT 32 bit
    LREAL = 0x1F  # FLOAT 64 bit


DataTypeSize: Dict[DataType, int] = {
    DataType.BIT: 1,
    DataType.BYTE: 1,
    DataType.CHAR: 1,
    DataType.WORD: 2,
    DataType.INT: 2,
    DataType.DWORD: 4,
    DataType.DINT: 4,
    DataType.REAL: 4,
    DataType.LREAL: 8,
}


class DataTypeData(Enum):
    # Transport size in data
    NULL = 0
    BIT = 3
    BYTE_WORD_DWORD = 4
    INTEGER = 5
    REAL = 7
    OCTET_STRING = 9


class ReturnCode(Enum):
    RESERVED = 0x00
    HW_FAULT = 0x01
    NO_ACCESS = 0x03
    OUT_OF_RANGE = 0x05
    UNSUPPORTED_DATA_TYPE = 0x06
    INCONSISTENT_DATA_TYPE = 0x07
    OBJECT_DOES_NOT_EXIST = 0x0A
    INVALID_DATA_SIZE = 0xFE
    SUCCESS = 0xFF


class ErrorClass(Enum):
    NO_ERROR = 0x00
    APP_RELATIONSHIP_ERROR = 0x81
    OBJECT_DEFINITION_ERROR = 0x82
    NO_RESSOURCES_AVAILABLE = 0x83
    SERVICE_PROCESSING_ERROR = 0x84
    SUPPLIES_ERROR = 0x85
    ACCESS_ERROR = 0x87


class ErrorCodes(Enum):
    NO_ERROR = 0x0000
    INVALID_BLOCK_TYPE = 0x0110
    INVALID_PARAMETER = 0x0112
    PG_RESSOURCE_ERROR = 0x011A
    PLC_RESSOURCE_ERROR = 0x011B
    PROTOCOL_ERROR = 0x011C
    USER_BUFFER_SHORT = 0x011F
    REQUEST_ERROR = 0x0141
    VERSION_MISMATCH = 0x01C0
    NOT_IMPLEMENTED = 0x01F0
    L7_INVALID_CPU_STATE = 0x8001
    L7_PDU_SIZE_ERROR = 0x8500
    L7_INVALID_SZL_ID = 0xD401
    L7_INVALID_INDEX = 0xD402
    L7_DGS_ALREADY_ANNOUNCED = 0xD403
    L7_MAX_USER_NB = 0xD404
    L7_DGS_SYNTAX_ERROR = 0xD405
    L7_NO_INFO = 0xD406
    L7_PRT_SYNTAX_ERROR = 0xD601
    L7_INVALID_VAR_ADDRESS = 0xD801
    L7_UNKNOWN_REQUEST = 0xD802
    L7_INVALID_REQUEST_STATUS = 0xD803


# Probably useless
ReturnCodeDict: Dict[int, str] = {
    0x00: "Reserved",
    0x01: "Hardware fault",
    0x03: "Accessing the object not allowed",
    0x05: "Address out of range",
    0x06: "Data type not supported",
    0x07: "Data type inconsistent",
    0x0A: "Object does not exist",
    0xFE: "Invalid data size",
    0xFF: "Success",
}

ErrorClassDict: Dict[int, str] = {
    0x00: "No error",
    0x81: "Application relationship error",
    0x82: "Object definition error",
    0x83: "No ressources available error",
    0x84: "Error on service processing",
    0x85: "Error on supplies",
    0x87: "Access error",
}


ErrorCodesDict: Dict[int, str] = {
    0x0000: "No error",
    0x0110: "Invalid block type number",
    0x0112: "Invalid parameter",
    0x011A: "PG ressource error",
    0x011B: "PLC ressource error",
    0x011C: "Protocol error",
    0x011F: "User buffer too short",
    0x0141: "Request error",
    0x01C0: "Version mismatch",
    0x01F0: "Not implemented",
    0x8001: "L7 invalid CPU state",
    0x8500: "L7 PDU size error",
    0xD401: "L7 invalid SZL ID",
    0xD402: "L7 invalid index",
    0xD403: "L7 DGS Connection already announced",
    0xD404: "L7 Max user NB",
    0xD405: "L7 DGS function parameter syntax error",
    0xD406: "L7 no info",
    0xD601: "L7 PRT function parameter syntax error",
    0xD801: "L7 invalid variable address",
    0xD802: "L7 unknown request",
    0xD803: "L7 invalid request status",
}
