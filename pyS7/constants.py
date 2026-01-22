from enum import Enum
from typing import Dict

MAX_PDU = 960
MAX_JOB_CALLING = 8
MAX_JOB_CALLED = 8

MAX_READ_TAGS = 20
MAX_WRITE_TAGS = 20

MAX_GAP_BYTES = 8

TPKT_SIZE = 4
COTP_SIZE = 3

# TPKT Protocol constants
TPKT_VERSION = 0x03
TPKT_RESERVED = 0x00

# COTP Protocol constants (ISO 8073)
COTP_PDU_TYPE_CR = 0xE0  # Connection Request
COTP_PDU_TYPE_CC = 0xD0  # Connection Confirm
COTP_PDU_TYPE_DR = 0x80  # Disconnect Request
COTP_PDU_TYPE_DT = 0xF0  # Data Transfer
COTP_TPDU_SIZE_PARAM = 0xC0  # Parameter code for TPDU size
COTP_SRC_TSAP_PARAM = 0xC1   # Parameter code for Source TSAP
COTP_DST_TSAP_PARAM = 0xC2   # Parameter code for Destination TSAP
COTP_TPDU_SIZE_1024 = 0x0A   # TPDU size value for 1024 bytes

# S7 Protocol constants
S7_PROTOCOL_ID = 0x32

# Connection Request packet constants
COTP_CR_LENGTH = 0x11  # Length indicator for Connection Request (17 bytes)
COTP_CR_PACKET_LENGTH = 0x16  # Total TPKT length for Connection Request (22 bytes)
COTP_PARAM_LENGTH = 0x01  # Parameter length for COTP parameters
COTP_TSAP_LENGTH = 0x02  # TSAP parameter length

# SZL Request constants
SZL_PARAM_HEAD = b"\x00\x01\x12"  # Parameter head for SZL requests
SZL_PARAM_LENGTH = 0x04  # Parameter length (4 bytes after this)
SZL_METHOD_REQUEST = 0x11  # Method: Request
SZL_RETURN_CODE_SUCCESS = 0xFF  # Return code for successful request
SZL_TRANSPORT_SIZE = 0x09  # Transport size (octet string)

# S7 Header offsets in responses
S7_HEADER_OFFSET = 7  # Offset where S7 header starts (after TPKT + COTP)
S7_PROTOCOL_ID_OFFSET = 0  # Offset of protocol ID within S7 header
S7_MESSAGE_TYPE_OFFSET = 1  # Offset of message type within S7 header
S7_PARAM_LENGTH_OFFSET = 6  # Offset of parameter length within S7 header
S7_DATA_LENGTH_OFFSET = 8   # Offset of data length within S7 header

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


class UserDataFunction(Enum):
    CPU_FUNCTIONS = 0x04


class UserDataSubfunction(Enum):
    READ_SZL = 0x01


class SZLId(Enum):
    """SZL (System Status List) IDs for reading PLC information"""
    MODULE_IDENTIFICATION = 0x0011
    CPU_CHARACTERISTICS = 0x0131
    USER_MEMORY_AREAS = 0x0132
    SYSTEM_AREAS = 0x0174
    BLOCK_TYPES = 0x0191
    COMPONENT_IDENTIFICATION = 0x001C
    INTERRUPT_STATUS = 0x0222
    DIAGNOSTIC_BUFFER = 0x00A0
    MODULE_DIAGNOSTIC = 0x00B1
    CPU_LED_STATUS = 0x0119
    CPU_DIAGNOSTIC_STATUS = 0x0424  # Operating status of the CPU


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
    STRING = 9  # S7 string (max length + current length header)
    WSTRING = 10  # S7 wide string UTF-16 (max length + current length header, 2 bytes per char)
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
    DataType.STRING: 1,
    DataType.WSTRING: 2,  # 2 bytes per character (UTF-16)
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
    INVALID_ADDRESS = 0x38  # Invalid address or address out of range
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
