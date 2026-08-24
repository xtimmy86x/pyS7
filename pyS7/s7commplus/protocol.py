"""Constants and pure packet builders for the S7CommPlus Phase 1/2 subset."""

from enum import IntEnum

PROTOCOL_ID = 0x72
DEFAULT_PORT = 102
MAX_PACKET_SIZE = 1024 * 1024
MAX_ACCESS_SEQUENCE = 64
DB_ACCESS_AREA_BASE = 0x8A0E0000
DB_VALUE_ACTUAL = 2550
LOCAL_TSAP = 0x0600
REMOTE_TSAP = b"SIMATIC-ROOT-HMI"


class ProtocolVersion(IntEnum):
    V1 = 1
    V2 = 2
    V3 = 3


class Opcode(IntEnum):
    REQUEST = 0x31
    RESPONSE = 0x32
    RESPONSE2 = 0x02


class FunctionCode(IntEnum):
    CREATE_OBJECT = 0x04CA
    DELETE_OBJECT = 0x04D4
    SET_MULTI_VARIABLES = 0x0542
    GET_MULTI_VARIABLES = 0x054C
    INIT_SSL = 0x05B3
    GET_VAR_SUBSTREAMED = 0x0586


READ_FUNCTION_CODES = frozenset(
    (FunctionCode.GET_MULTI_VARIABLES, FunctionCode.GET_VAR_SUBSTREAMED)
)


class DataType(IntEnum):
    NULL = 0x00
    BOOL = 0x01
    USINT = 0x02
    UINT = 0x03
    UDINT = 0x04
    ULINT = 0x05
    SINT = 0x06
    INT = 0x07
    DINT = 0x08
    LINT = 0x09
    BYTE = 0x0A
    WORD = 0x0B
    DWORD = 0x0C
    LWORD = 0x0D
    REAL = 0x0E
    LREAL = 0x0F
    TIMESTAMP = 0x10
    TIMESPAN = 0x11
    RID = 0x12
    AID = 0x13
    BLOB = 0x14
    WSTRING = 0x15
    STRUCT = 0x17


def db_access_area(db_number: int) -> int:
    """Return the symbolic AccessArea for DB ``db_number`` (1..65535)."""
    if (
        not isinstance(db_number, int)
        or isinstance(db_number, bool)
        or not 1 <= db_number <= 0xFFFF
    ):
        raise ValueError("DB number must be an integer from 1 through 65535")
    return DB_ACCESS_AREA_BASE + db_number
