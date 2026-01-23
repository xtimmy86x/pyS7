import random
import struct
from typing import (
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
    runtime_checkable,
)

from .constants import (
    COTP_CR_LENGTH,
    COTP_CR_PACKET_LENGTH,
    COTP_DST_TSAP_PARAM,
    COTP_PARAM_LENGTH,
    COTP_PDU_TYPE_CR,
    COTP_SIZE,
    COTP_SRC_TSAP_PARAM,
    COTP_TPDU_SIZE_1024,
    COTP_TPDU_SIZE_PARAM,
    COTP_TSAP_LENGTH,
    MAX_GAP_BYTES,
    MAX_READ_TAGS,
    MAX_WRITE_TAGS,
    READ_REQ_OVERHEAD,
    READ_REQ_PARAM_SIZE_TAG,
    READ_RES_OVERHEAD,
    READ_RES_PARAM_SIZE_TAG,
    S7_PROTOCOL_ID,
    SZL_METHOD_REQUEST,
    SZL_PARAM_HEAD,
    SZL_PARAM_LENGTH,
    SZL_RETURN_CODE_SUCCESS,
    SZL_TRANSPORT_SIZE,
    TPKT_RESERVED,
    TPKT_SIZE,
    TPKT_VERSION,
    WRITE_REQ_OVERHEAD,
    WRITE_REQ_PARAM_SIZE_TAG,
    WRITE_RES_OVERHEAD,
    ConnectionType,
    DataType,
    DataTypeData,
    DataTypeSize,
    Function,
    MessageType,
    SZLId,
    UserDataFunction,
    UserDataSubfunction,
)
from .errors import S7AddressError, S7PDUError
from .tag import S7Tag

TagsMap = Dict[S7Tag, List[Tuple[int, S7Tag]]]
Value = Union[bool, int, float, str, Tuple[Union[bool, int, float], ...]]


S7_HEADER_SIZE = 10
TPKT_LENGTH_SLICE = slice(2, 4)
PARAMETER_LENGTH_SLICE = slice(TPKT_SIZE + COTP_SIZE + 6, TPKT_SIZE + COTP_SIZE + 8)
DATA_LENGTH_SLICE = slice(TPKT_SIZE + COTP_SIZE + 8, TPKT_SIZE + COTP_SIZE + 10)
HEADER_SIZE = TPKT_SIZE + COTP_SIZE + S7_HEADER_SIZE


def _init_s7_packet(message_type: MessageType) -> Tuple[bytearray, int]:
    """Initialize an S7 packet with TPKT, COTP, and S7 headers.
    
    Creates the base packet structure with placeholders for lengths.
    Placeholders are filled by _finalize_packet after adding parameters and data.
    
    Args:
        message_type: Type of S7 message (JOB, ACK_DATA, USERDATA)
        
    Returns:
        Tuple of (packet bytearray, header size offset)
    """
    packet = bytearray()
    packet.extend(b"\x03\x00\x00\x00")  # TPKT header with placeholder length
    packet.extend(b"\x02\xf0\x80")  # COTP header
    packet.extend(b"\x32")  # S7 protocol id
    packet.extend(message_type.value.to_bytes(1, byteorder="big"))
    packet.extend(b"\x00\x00")  # Redundancy identification (reserved)
    packet.extend(b"\x00\x00")  # PDU reference
    packet.extend(b"\x00\x00")  # Parameter length placeholder
    packet.extend(b"\x00\x00")  # Data length placeholder

    return packet, HEADER_SIZE


def _finalize_packet(packet: bytearray, parameter_start: int, data_start: int) -> None:
    """Finalize S7 packet by updating length fields.
    
    Updates TPKT total length, S7 parameter length, and S7 data length
    based on the final packet size and section boundaries.
    
    Args:
        packet: Packet to finalize (modified in-place)
        parameter_start: Byte offset where parameters begin
        data_start: Byte offset where data begins
    """
    parameter_length = data_start - parameter_start
    data_length = len(packet) - data_start

    packet[PARAMETER_LENGTH_SLICE] = parameter_length.to_bytes(2, byteorder="big")
    packet[DATA_LENGTH_SLICE] = data_length.to_bytes(2, byteorder="big")
    packet[TPKT_LENGTH_SLICE] = len(packet).to_bytes(2, byteorder="big")


@runtime_checkable
class Request(Protocol):
    request: bytearray

    def serialize(self) -> bytes:
        return bytes(self.request)


class ConnectionRequest(Request):
    def __init__(
        self,
        rack: int,
        slot: int,
        connection_type: ConnectionType,
        local_tsap: Optional[int] = None,
        remote_tsap: Optional[int] = None,
    ) -> None:
        self.request = self.__prepare_packet(
            rack=rack,
            slot=slot,
            connection_type=connection_type,
            local_tsap=local_tsap,
            remote_tsap=remote_tsap,
        )

    def __prepare_packet(
        self,
        rack: int,
        slot: int,
        connection_type: ConnectionType,
        local_tsap: Optional[int] = None,
        remote_tsap: Optional[int] = None,
    ) -> bytearray:
        packet = bytearray()

        # TPKT Header (RFC 1006)
        packet.extend(TPKT_VERSION.to_bytes(1, byteorder="big"))  # Version
        packet.extend(TPKT_RESERVED.to_bytes(1, byteorder="big"))  # Reserved
        packet.extend(b"\x00")  # Length (MSB)
        packet.extend(COTP_CR_PACKET_LENGTH.to_bytes(1, byteorder="big"))  # Length (LSB) = 22 bytes

        # COTP Header (ISO 8073)
        packet.extend(COTP_CR_LENGTH.to_bytes(1, byteorder="big"))  # Length Indicator = 17 bytes
        packet.extend(COTP_PDU_TYPE_CR.to_bytes(1, byteorder="big"))  # PDU Type = CR (Connection Request)
        packet.extend(b"\x00")  # Destination Reference (MSB)
        packet.extend(b"\x00")  # Destination Reference (LSB)
        
        # Generate a random Source Reference
        # This prevents connection conflicts when reconnecting
        source_ref = random.randint(0, 0xFFFF)
        packet.extend(bytes([(source_ref >> 8) & 0xFF]))  # Source Reference (MSB)
        packet.extend(bytes([source_ref & 0xFF]))         # Source Reference (LSB)
        packet.extend(b"\x00")  # Class/Options (TP0)

        # COTP Parameters
        packet.extend(COTP_TPDU_SIZE_PARAM.to_bytes(1, byteorder="big"))  # Parameter Code: TPDU Size
        packet.extend(COTP_PARAM_LENGTH.to_bytes(1, byteorder="big"))  # Parameter Length
        packet.extend(COTP_TPDU_SIZE_1024.to_bytes(1, byteorder="big"))  # TPDU Size = 1024 bytes
        packet.extend(COTP_SRC_TSAP_PARAM.to_bytes(1, byteorder="big"))  # Parameter Code: Source TSAP
        packet.extend(COTP_TSAP_LENGTH.to_bytes(1, byteorder="big"))  # Parameter Length
        packet.extend(b"\x01")  # Src-TSAP (MSB) - placeholder
        packet.extend(b"\x00")  # Src-TSAP (LSB) - placeholder
        packet.extend(COTP_DST_TSAP_PARAM.to_bytes(1, byteorder="big"))  # Parameter Code: Destination TSAP
        packet.extend(COTP_TSAP_LENGTH.to_bytes(1, byteorder="big"))  # Parameter Length
        packet.extend(b"\x01")  # Dst-TSAP (MSB) - placeholder
        packet.extend(b"\x02")  # Dst-TSAP (LSB) - placeholder

        # If TSAP values are provided, use them directly
        # Otherwise, calculate from rack/slot and connection type
        if local_tsap is not None:
            packet[16] = (local_tsap >> 8) & 0xFF
            packet[17] = local_tsap & 0xFF
        else:
            # Default local TSAP based on connection type
            packet[16] = 0x01
            packet[17] = 0x00

        if remote_tsap is not None:
            packet[20] = (remote_tsap >> 8) & 0xFF
            packet[21] = remote_tsap & 0xFF
        else:
            # Connection type and rack/slot
            packet[20] = connection_type.value
            packet[21] = rack * 32 + slot

        return packet


class PDUNegotiationRequest(Request):
    """Request for negotiating the PDU size with the S7 device."""

    def __init__(self, max_pdu: int) -> None:
        self.request = self.__prepare_packet(max_pdu=max_pdu)

    def __prepare_packet(self, max_pdu: int) -> bytearray:
        packet, parameter_start = _init_s7_packet(MessageType.REQUEST)

        # S7: PARAMETER
        packet.extend(Function.COMM_SETUP.value.to_bytes(1, byteorder="big"))
        packet.extend(b"\x00")
        packet.extend(b"\x00")
        packet.extend(b"\x08")
        packet.extend(b"\x00")
        packet.extend(b"\x08")
        packet.extend(max_pdu.to_bytes(2, byteorder="big"))

        data_start = len(packet)
        _finalize_packet(packet, parameter_start, data_start)

        return packet


class ReadRequest(Request):
    """Request for reading data from an S7 device."""

    def __init__(self, tags: Sequence[S7Tag]) -> None:
        self.tags = tags
        self.request = self.__prepare_packet(tags=tags)

    def __prepare_packet(self, tags: Sequence[S7Tag]) -> bytearray:
        packet, parameter_start = _init_s7_packet(MessageType.REQUEST)

        # S7: PARAMETER
        packet.extend(Function.READ_VAR.value.to_bytes(1, byteorder="big"))
        tag_count_index = len(packet)
        packet.extend(b"\x00")  # placeholder for tag count

        # S7Tag specification
        for tag in tags:
            packet.extend(b"\x12")  # Variable specification
            packet.extend(b"\x0a")  # Length of following address specification
            packet.extend(b"\x10")  # Syntax ID: S7ANY (0x10)
            if tag.data_type == DataType.LREAL:
                transport_size = DataTypeData.BYTE_WORD_DWORD.value
                length = tag.length * DataTypeSize[tag.data_type]
            elif tag.data_type == DataType.STRING:
                transport_size = DataTypeData.BYTE_WORD_DWORD.value
                length = tag.size()
            elif tag.data_type == DataType.WSTRING:
                transport_size = DataTypeData.BYTE_WORD_DWORD.value
                length = tag.size()
            else:
                transport_size = tag.data_type.value
                length = tag.length
            packet.extend(transport_size.to_bytes(1, byteorder="big"))  # Transport size
            packet.extend(length.to_bytes(2, byteorder="big"))  # Length
            packet.extend(tag.db_number.to_bytes(2, byteorder="big"))  # DB Number
            packet.extend(
                tag.memory_area.value.to_bytes(1, byteorder="big")
            )  # Area Code (0x84 for DB)
            packet.extend(
                (tag.start * 8 + tag.bit_offset).to_bytes(3, byteorder="big")
            )  # Address

        packet[tag_count_index] = len(tags)

        data_start = len(packet)
        _finalize_packet(packet, parameter_start, data_start)

        return packet


# Helper functions for data packing to reduce code duplication
def _pack_numeric_data(data: Union[int, float, Tuple[Union[int, float], ...]], 
                       format_char: str, 
                       length: int) -> bytes:
    """Pack numeric data (int, float) using struct.pack.
    
    Args:
        data: Single value or tuple of values
        format_char: struct format character (e.g., 'h' for INT, 'f' for REAL)
        length: Number of elements to pack
        
    Returns:
        Packed bytes
    """
    if isinstance(data, tuple):
        return struct.pack(f">{length * format_char}", *data)
    else:
        return struct.pack(f">{format_char}", data)


def _pack_string_data(data: str, max_length: int, tag: S7Tag, encoding: str = "ascii") -> bytes:
    """Pack STRING data with header and padding.
    
    Args:
        data: String to pack
        max_length: Maximum string length
        tag: Tag for error messages
        encoding: Character encoding (default: ascii)
        
    Returns:
        Packed bytes with header and padding
        
    Raises:
        S7AddressError: If data type is incorrect or string is too long
    """
    if not isinstance(data, str):
        raise S7AddressError(
            f"STRING data must be str, got {type(data).__name__}"
        )
    encoded = data.encode(encoding=encoding)
    if len(encoded) > max_length:
        raise S7AddressError(
            f"STRING data too long for {tag}: max length is {max_length}, got {len(encoded)}"
        )
    header = bytes([max_length, len(encoded)])
    padding = b"\x00" * (max_length - len(encoded))
    return header + encoded + padding


def _pack_wstring_data(data: str, max_length: int, tag: S7Tag) -> bytes:
    """Pack WSTRING data with header and padding.
    
    Args:
        data: String to pack
        max_length: Maximum string length in characters
        tag: Tag for error messages
        
    Returns:
        Packed bytes with header and padding
        
    Raises:
        S7AddressError: If data type is incorrect or string is too long
    """
    if not isinstance(data, str):
        raise S7AddressError(
            f"WSTRING data must be str, got {type(data).__name__}"
        )
    encoded = data.encode(encoding="utf-16-be")
    if len(encoded) // 2 > max_length:  # Each char is 2 bytes
        raise S7AddressError(
            f"WSTRING data too long for {tag}: max length is {max_length} chars, got {len(encoded) // 2}"
        )
    # WSTRING uses 2-byte headers (unlike STRING which uses 1-byte headers)
    header = struct.pack(">HH", max_length, len(data))  # Big-endian 16-bit values
    padding = b"\x00" * ((max_length - len(data)) * 2)  # 2 bytes per char
    return header + encoded + padding


class WriteRequest(Request):
    """Request for writing data to an S7 device."""

    def __init__(self, tags: Sequence[S7Tag], values: Sequence[Value]) -> None:
        self.tags = tags
        self.values = values

        self.request = self.__prepare_packet(tags=tags, values=values)

    def __prepare_packet(
        self, tags: Sequence[S7Tag], values: Sequence[Value]
    ) -> bytearray:
        packet, parameter_start = _init_s7_packet(MessageType.REQUEST)

        # S7: PARAMETER
        packet.extend(
            Function.WRITE_VAR.value.to_bytes(1, byteorder="big")
        )  # Function Write Var
        tag_count_index = len(packet)
        packet.extend(b"\x00")  # placeholder for tag count

        # S7Tag specification
        for tag in tags:
            packet.extend(b"\x12")  # Variable specification
            packet.extend(b"\x0a")  # Length of following address specification
            packet.extend(b"\x10")  # Syntax ID: S7ANY (0x10)

            if tag.data_type == DataType.BIT:
                packet.extend(
                    DataType.BIT.value.to_bytes(1, byteorder="big")
                )  # Transport size
            else:
                # Transport size, write everything as bytes
                packet.extend(DataType.BYTE.value.to_bytes(1, byteorder="big"))

            # Length (tag length * size of data type)
            tag_size = tag.size() if tag.data_type in (DataType.STRING, DataType.WSTRING) else tag.length * DataTypeSize[tag.data_type]
            packet.extend(tag_size.to_bytes(2, byteorder="big"))
            packet.extend(tag.db_number.to_bytes(2, byteorder="big"))  # DB Number
            packet.extend(
                tag.memory_area.value.to_bytes(1, byteorder="big")
            )  # Area Code (0x84 for DB)

            packet.extend(
                (tag.start * 8 + tag.bit_offset).to_bytes(3, byteorder="big")
            )  # Address

        packet[tag_count_index] = len(tags)

        data_start = len(packet)

        # S7 : DATA
        for i, tag in enumerate(tags):
            packet.extend(b"\x00")  # Reserved (0x00)

            data = values[i]

            if tag.data_type == DataType.BIT:
                transport_size = DataTypeData.BIT
                new_length = tag.length * DataTypeSize[tag.data_type]
                packed_data = struct.pack(">?", data)

            elif tag.data_type == DataType.BYTE:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                # data can be int or tuple of ints for BYTE
                packed_data = _pack_numeric_data(data, 'B', tag.length)  # type: ignore[arg-type]

            elif tag.data_type == DataType.CHAR:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if not isinstance(data, str):
                    raise S7AddressError(
                        f"CHAR data must be str, got {type(data).__name__}"
                    )
                packed_data = data.encode(encoding="ascii")

            elif tag.data_type == DataType.STRING:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.size() * 8
                # Type checked inside _pack_string_data
                packed_data = _pack_string_data(data, tag.length, tag)  # type: ignore[arg-type]

            elif tag.data_type == DataType.WSTRING:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.size() * 8
                # Type checked inside _pack_wstring_data
                packed_data = _pack_wstring_data(data, tag.length, tag)  # type: ignore[arg-type]

            elif tag.data_type == DataType.INT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                packed_data = _pack_numeric_data(data, 'h', tag.length)  # type: ignore[arg-type]

            elif tag.data_type == DataType.WORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                packed_data = _pack_numeric_data(data, 'H', tag.length)  # type: ignore[arg-type]

            elif tag.data_type == DataType.DWORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                packed_data = _pack_numeric_data(data, 'I', tag.length)  # type: ignore[arg-type]

            elif tag.data_type == DataType.DINT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                packed_data = _pack_numeric_data(data, 'l', tag.length)  # type: ignore[arg-type]

            elif tag.data_type == DataType.REAL:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                packed_data = _pack_numeric_data(data, 'f', tag.length)  # type: ignore[arg-type]

            elif tag.data_type == DataType.LREAL:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                packed_data = _pack_numeric_data(data, 'd', tag.length)  # type: ignore[arg-type]

            else:
                raise RuntimeError(
                    f"DataType {tag.data_type} not supported for write operations"
                )

            # Data transport size - This is not the DataType
            packet.extend(transport_size.value.to_bytes(1, byteorder="big"))
            packet.extend(new_length.to_bytes(2, byteorder="big"))
            packet.extend(packed_data)

            if tag.data_type == DataType.BIT and i < len(tags) - 1:
                packet.extend(b"\x00")

            if len(packet) % 2 == 0 and i < len(tags) - 1:
                packet.extend(b"\x00")

        _finalize_packet(packet, parameter_start, data_start)

        return packet

def prepare_requests(tags: List[S7Tag], max_pdu: int) -> List[List[S7Tag]]:
    requests: List[List[S7Tag]] = [[]]

    cumulated_request_size = READ_REQ_OVERHEAD
    cumulated_response_size = READ_RES_OVERHEAD

    for tag in tags:
        # Cache tag size to avoid multiple calls (performance optimization)
        tag_size = tag.size()
        
        tag_request_size = READ_REQ_PARAM_SIZE_TAG
        tag_response_size = READ_RES_PARAM_SIZE_TAG + tag_size

        if (
            READ_REQ_OVERHEAD + tag_request_size >= max_pdu
            or READ_RES_OVERHEAD + tag_response_size > max_pdu
        ):
            max_data_size = max_pdu - READ_RES_OVERHEAD - READ_RES_PARAM_SIZE_TAG
            raise S7PDUError(
                f"{tag} requires {READ_RES_OVERHEAD + tag_response_size} bytes but PDU size is {max_pdu} bytes. "
                f"Maximum data size for this PDU: {max_data_size} bytes (current tag needs {tag_size} bytes). "
                f"Consider: 1) Negotiating larger PDU, 2) Reading in smaller chunks, or 3) Using shorter string length."
            )

        elif (
            cumulated_request_size + tag_request_size < max_pdu
            and cumulated_response_size + tag_response_size < max_pdu
            and len(requests[-1]) < MAX_READ_TAGS
        ):
            requests[-1].append(tag)

            cumulated_request_size += READ_REQ_PARAM_SIZE_TAG
            cumulated_response_size += READ_RES_PARAM_SIZE_TAG + tag_size

        else:
            requests.append([tag])
            cumulated_request_size = READ_REQ_OVERHEAD + READ_REQ_PARAM_SIZE_TAG
            cumulated_response_size = (
                READ_RES_OVERHEAD + READ_RES_PARAM_SIZE_TAG + tag_size
            )

    return requests


def _bucket_bit_tags(tags: List[S7Tag]) -> Tuple[List[Tuple[int, S7Tag]], TagsMap]:
    """Pre-bucket BIT tags by byte address to optimize reads.
    
    Groups BIT tags that share the same byte address into a single BYTE read.
    This avoids duplicate packed keys and works around PLCs that don't support
    single BIT reads reliably.
    
    Args:
        tags: List of tags to process
        
    Returns:
        Tuple of (work_items, initial_groups) where:
        - work_items: List of (index, tag) tuples ready for processing
        - initial_groups: TagsMap with packed BYTE tags already grouped
    """
    bit_buckets: Dict[Tuple[int, int, int], List[Tuple[int, S7Tag]]] = {}
    non_bits: List[Tuple[int, S7Tag]] = []
    groups: TagsMap = {}

    for idx, t in enumerate(tags):
        if t.data_type == DataType.BIT:
            key = (t.memory_area.value, t.db_number, t.start)
            bit_buckets.setdefault(key, []).append((idx, t))
        else:
            non_bits.append((idx, t))

    # Build "work items":
    # - If a bucket has more than one BIT, replace it with a single BYTE(1) planned tag.
    # - If a bucket has exactly one BIT, keep it as BIT to preserve existing semantics/tests.
    work: List[Tuple[int, S7Tag]] = []
    for lst in bit_buckets.values():
        if len(lst) == 1:
            work.append(lst[0])  # (idx, BIT)
        else:
            idx0, t0 = min(lst, key=lambda x: x[0])
            packed_byte = S7Tag(
                memory_area=t0.memory_area,
                db_number=t0.db_number,
                data_type=DataType.BYTE,
                start=t0.start,
                bit_offset=0,
                length=1,
            )
            work.append((idx0, packed_byte))
            # Map this packed byte to ALL original bit tags (with their original indices)
            groups[packed_byte] = list(lst)

    # Add all non-bit tags as-is
    work.extend(non_bits)
    return work, groups


def _check_tag_fits_pdu(tag: S7Tag, max_pdu: int) -> None:
    """Check if a single tag fits within PDU size limits.
    
    Args:
        tag: Tag to check
        max_pdu: Maximum PDU size
        
    Raises:
        S7AddressError: If tag doesn't fit in PDU
    """
    tag_request_size = READ_REQ_PARAM_SIZE_TAG
    tag_response_size = READ_RES_PARAM_SIZE_TAG + tag.size()
    
    if (
        READ_REQ_OVERHEAD + tag_request_size >= max_pdu
        or READ_RES_OVERHEAD + tag_response_size > max_pdu
    ):
        raise S7PDUError(
            f"{tag} too big -> it cannot fit negotiated PDU ({max_pdu}). "
            f"Tag size: {tag.size()} bytes."
        )


def _try_merge_tags(prev: S7Tag, tag: S7Tag, max_gap_bytes: int, allow_overlap: bool) -> Optional[S7Tag]:
    """Try to merge two adjacent tags into a single read.
    
    Args:
        prev: Previous tag
        tag: Current tag to merge
        max_gap_bytes: Maximum gap allowed between tags
        allow_overlap: Whether to allow overlapping tags
        
    Returns:
        Merged tag if merge is possible, None otherwise
    """
    # Only merge tags in the same memory area and DB
    if prev.memory_area != tag.memory_area or prev.db_number != tag.db_number:
        return None
    
    prev_start = prev.start
    prev_end = prev.start + prev.size()  # exclusive end in bytes
    tag_start = tag.start
    tag_end = tag.start + tag.size()     # exclusive end in bytes

    # Positive only when tag starts after prev_end; negative/zero means overlap/containment
    gap = tag_start - prev_end

    # Decide if merge is allowed
    if allow_overlap:
        # Merge if overlap/containment (gap <= 0) OR within gap threshold
        merge_ok = gap <= max_gap_bytes
    else:
        # Merge only when strictly after previous range AND within gap threshold
        merge_ok = (gap >= 0) and (gap <= max_gap_bytes)

    if not merge_ok:
        return None
    
    new_start = prev_start
    new_end = max(prev_end, tag_end)
    new_len = new_end - new_start

    return S7Tag(
        memory_area=prev.memory_area,
        db_number=prev.db_number,
        data_type=DataType.BYTE,
        start=new_start,
        bit_offset=0,
        length=new_len,
    )


def prepare_optimized_requests(
    tags: List[S7Tag],
    max_pdu: int,
    *,
    max_gap_bytes: int = MAX_GAP_BYTES,
    allow_overlap: bool = True,
) -> Tuple[List[List[S7Tag]], TagsMap]:
    """
    Prepare optimized read requests by:
      - Sorting tags by (area, db, start)
      - Pre-bucketing BIT tags that share the same byte address into a single BYTE(1) read
        to avoid duplicate packed keys and reduce telegram count
      - Merging tags into packed BYTE blocks:
          * If allow_overlap=True: merge when overlap/containment happens OR gap <= max_gap_bytes
          * If allow_overlap=False: merge only when tag starts after prev_end AND gap <= max_gap_bytes
      - Respecting negotiated PDU limits and MAX_READ_TAGS per request

    Returns:
      requests: List of request batches; each batch is a list of packed tags to be sent
      in one ReadRequest
      groups:   Mapping packed_tag -> list of (original_index, original_tag) for decoding
      in the optimized response parser
    """
    requests: List[List[S7Tag]] = [[]]
    
    # Pre-bucket BIT tags and prepare work items
    work, groups = _bucket_bit_tags(tags)
    
    cum_req = READ_REQ_OVERHEAD
    cum_res = READ_RES_OVERHEAD

    # Sort by address (the index is used only for stable ordering in the final decoded output)
    sorted_tags = sorted(
        work,
        key=lambda elem: (elem[1].memory_area.value, elem[1].db_number, elem[1].start),
    )

    for idx, tag in sorted_tags:
        _check_tag_fits_pdu(tag, max_pdu)

        # Ensure every tag has an entry in the mapping
        if tag not in groups:
            groups[tag] = [(idx, tag)]

        # First element in current request
        if not requests[-1]:
            requests[-1].append(tag)
            cum_req += READ_REQ_PARAM_SIZE_TAG
            cum_res += READ_RES_PARAM_SIZE_TAG + tag.size()
            continue

        # Calculate sizes for current tag
        tag_req_size = READ_REQ_PARAM_SIZE_TAG
        tag_res_size = READ_RES_PARAM_SIZE_TAG + tag.size()
        
        # If there is no room in the current request, start a new one
        if not (
            cum_req + tag_req_size < max_pdu
            and cum_res + tag_res_size < max_pdu
            and len(requests[-1]) < MAX_READ_TAGS
        ):
            requests.append([tag])
            cum_req = READ_REQ_OVERHEAD + tag_req_size
            cum_res = READ_RES_OVERHEAD + tag_res_size
            continue

        prev = requests[-1][-1]

        # Attempt merging with previous tag
        merged_tag = _try_merge_tags(prev, tag, max_gap_bytes, allow_overlap)
        if merged_tag is not None:
            # Request tag count does not increase (we replace prev with merged_tag),
            # only the response payload for that item grows.
            delta_res = merged_tag.size() - prev.size()
            if cum_res + delta_res < max_pdu:
                prev_map = groups.pop(prev, [(idx, prev)])
                cur_map = groups.pop(tag, [(idx, tag)])
                groups[merged_tag] = prev_map + cur_map

                requests[-1][-1] = merged_tag
                cum_res += delta_res
                continue

        # No merge: append tag to the request
        requests[-1].append(tag)
        cum_req += tag_req_size
        cum_res += tag_res_size

    return requests, groups




def prepare_write_requests_and_values(
    tags: Sequence[S7Tag], values: Sequence[Value], max_pdu: int
) -> Tuple[List[List[S7Tag]], List[List[Value]]]:
    requests: List[List[S7Tag]] = [[]]
    requests_values: List[List[Value]] = [[]]

    request_size = WRITE_REQ_OVERHEAD
    response_size = WRITE_RES_OVERHEAD

    for i, tag in enumerate(tags):
        # Cache tag size to avoid duplicate calls (performance optimization)
        tag_size = tag.size()
        tag_padding = tag_size % 2

        if (
            WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag_size >= max_pdu
            or WRITE_RES_OVERHEAD + tag_size + 1 >= max_pdu
        ):
            max_data_size = max_pdu - WRITE_REQ_OVERHEAD - WRITE_REQ_PARAM_SIZE_TAG
            raise S7PDUError(
                f"{tag} requires {WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag_size} bytes but PDU size is {max_pdu} bytes. "
                f"Maximum data size for this PDU: {max_data_size} bytes (current tag needs {tag_size} bytes). "
                f"Consider: 1) Negotiating larger PDU, 2) Writing in smaller chunks, or 3) Using shorter string length."
            )

        elif (
            request_size + WRITE_REQ_PARAM_SIZE_TAG + 4 + tag_size + tag_padding
            < max_pdu
            and response_size + 1 < max_pdu
            and len(requests[-1]) < MAX_WRITE_TAGS
        ):
            requests[-1].append(tag)
            requests_values[-1].append(values[i])

            request_size += WRITE_REQ_PARAM_SIZE_TAG + 4 + tag_size + tag_padding
            response_size += 1

        else:
            requests.append([tag])
            requests_values.append([values[i]])

            request_size = (
                WRITE_REQ_OVERHEAD
                + WRITE_REQ_PARAM_SIZE_TAG
                + 4
                + tag_size
                + tag_padding
            )
            response_size = WRITE_RES_OVERHEAD + 1

    return requests, requests_values


class SZLRequest(Request):
    """Request for reading System Status List (SZL) data from an S7 device."""

    def __init__(self, szl_id: SZLId, szl_index: int = 0x0000) -> None:
        """
        Initialize an SZL request.

        Args:
            szl_id: The SZL ID to request (e.g., SZLId.CPU_DIAGNOSTIC_STATUS)
            szl_index: The SZL index (default 0x0000)
        """
        self.szl_id = szl_id
        self.szl_index = szl_index
        self.request = self.__prepare_packet(szl_id=szl_id, szl_index=szl_index)

    def __prepare_packet(self, szl_id: SZLId, szl_index: int) -> bytearray:
        """Prepare the SZL request packet."""
        packet = bytearray()

        # TPKT header
        packet.extend(TPKT_VERSION.to_bytes(1, byteorder="big"))
        packet.extend(TPKT_RESERVED.to_bytes(1, byteorder="big"))
        tpkt_length_index = len(packet)
        packet.extend(b"\x00\x00")  # Placeholder for TPKT length

        # COTP header
        packet.extend(b"\x02\xf0\x80")

        # S7 Header
        packet.extend(S7_PROTOCOL_ID.to_bytes(1, byteorder="big"))  # S7 protocol ID
        packet.extend(MessageType.USERDATA.value.to_bytes(1, byteorder="big"))
        packet.extend(b"\x00\x00")  # Reserved
        packet.extend(b"\x00\x00")  # PDU reference (will be filled by sequence number if needed)
        param_length_index = len(packet)
        packet.extend(b"\x00\x00")  # Placeholder for parameter length
        data_length_index = len(packet)
        packet.extend(b"\x00\x00")  # Placeholder for data length

        parameter_start = len(packet)

        # Parameter section
        packet.extend(SZL_PARAM_HEAD)  # Parameter head (3 bytes)
        packet.extend(SZL_PARAM_LENGTH.to_bytes(1, byteorder="big"))  # Parameter length (4 bytes after this)
        packet.extend(SZL_METHOD_REQUEST.to_bytes(1, byteorder="big"))  # Method: Request
        packet.extend(UserDataFunction.CPU_FUNCTIONS.value.to_bytes(1, byteorder="big"))
        packet.extend(UserDataSubfunction.READ_SZL.value.to_bytes(1, byteorder="big"))
        packet.extend(b"\x01")  # Sequence number

        data_start = len(packet)

        # Data section
        packet.extend(SZL_RETURN_CODE_SUCCESS.to_bytes(1, byteorder="big"))  # Return code (0xFF for request)
        packet.extend(SZL_TRANSPORT_SIZE.to_bytes(1, byteorder="big"))  # Transport size (octet string)
        data_unit_length = 4
        packet.extend(data_unit_length.to_bytes(2, byteorder="big"))
        packet.extend(szl_id.value.to_bytes(2, byteorder="big"))
        packet.extend(szl_index.to_bytes(2, byteorder="big"))

        # Update lengths
        parameter_length = data_start - parameter_start
        data_length = len(packet) - data_start
        tpkt_length = len(packet)

        packet[tpkt_length_index:tpkt_length_index + 2] = tpkt_length.to_bytes(2, byteorder="big")
        packet[param_length_index:param_length_index + 2] = parameter_length.to_bytes(2, byteorder="big")
        packet[data_length_index:data_length_index + 2] = data_length.to_bytes(2, byteorder="big")

        return packet

