import struct
from typing import Dict, List, Optional, Protocol, Sequence, Tuple, Union, runtime_checkable

from .errors import S7AddressError

from .constants import (
    COTP_SIZE,
    MAX_GAP_BYTES,
    MAX_READ_TAGS,
    MAX_WRITE_TAGS,
    READ_REQ_OVERHEAD,
    READ_REQ_PARAM_SIZE_TAG,
    READ_RES_OVERHEAD,
    READ_RES_PARAM_SIZE_TAG,
    TPKT_SIZE,
    WRITE_REQ_OVERHEAD,
    WRITE_REQ_PARAM_SIZE_TAG,
    WRITE_RES_OVERHEAD,
    ConnectionType,
    DataType,
    DataTypeData,
    DataTypeSize,
    Function,
    MessageType
)
from .tag import S7Tag

TagsMap = Dict[S7Tag, List[Tuple[int, S7Tag]]]
Value = Union[bool, int, float, str, Tuple[Union[bool, int, float], ...]]


S7_HEADER_SIZE = 10
TPKT_LENGTH_SLICE = slice(2, 4)
PARAMETER_LENGTH_SLICE = slice(TPKT_SIZE + COTP_SIZE + 6, TPKT_SIZE + COTP_SIZE + 8)
DATA_LENGTH_SLICE = slice(TPKT_SIZE + COTP_SIZE + 8, TPKT_SIZE + COTP_SIZE + 10)
HEADER_SIZE = TPKT_SIZE + COTP_SIZE + S7_HEADER_SIZE


def _init_s7_packet(message_type: MessageType) -> Tuple[bytearray, int]:
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

        packet.extend(b"\x03")
        packet.extend(b"\x00")
        packet.extend(b"\x00")
        packet.extend(b"\x16")

        packet.extend(b"\x11")
        packet.extend(b"\xe0")
        packet.extend(b"\x00")

        packet.extend(b"\x00")
        packet.extend(b"\x00")
        packet.extend(b"\x02")
        packet.extend(b"\x00")
        packet.extend(b"\xc0")
        packet.extend(b"\x01")
        packet.extend(b"\x0a")
        packet.extend(b"\xc1")
        packet.extend(b"\x02")
        packet.extend(b"\x01")
        packet.extend(b"\x00")
        packet.extend(b"\xc2")
        packet.extend(b"\x02")
        packet.extend(b"\x01")
        packet.extend(b"\x02")

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
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'B'}", *data)
                else:
                    packed_data = struct.pack(">B", data)

            elif tag.data_type == DataType.CHAR:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                assert isinstance(data, str)
                packed_data = data.encode(encoding="ascii")

            elif tag.data_type == DataType.STRING:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                max_length = tag.length
                assert isinstance(data, str)
                encoded = data.encode(encoding="ascii")
                if len(encoded) > max_length:
                    raise S7AddressError(
                        f"STRING data too long for {tag}: max length is {max_length}, got {len(encoded)}"
                    )
                new_length = tag.size() * 8
                header = bytes([max_length, len(encoded)])
                padding = b"\x00" * (max_length - len(encoded))
                packed_data = header + encoded + padding

            elif tag.data_type == DataType.WSTRING:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                max_length = tag.length
                assert isinstance(data, str)
                encoded = data.encode(encoding="utf-16-be")
                if len(encoded) // 2 > max_length:  # Each char is 2 bytes
                    raise S7AddressError(
                        f"WSTRING data too long for {tag}: max length is {max_length} chars, got {len(encoded) // 2}"
                    )
                new_length = tag.size() * 8
                # WSTRING uses 2-byte headers (unlike STRING which uses 1-byte headers)
                header = struct.pack(">HH", max_length, len(data))  # Big-endian 16-bit values
                padding = b"\x00" * ((max_length - len(data)) * 2)  # 2 bytes per char
                packed_data = header + encoded + padding
                
            elif tag.data_type == DataType.INT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'h'}", *data)
                else:
                    packed_data = struct.pack(">h", data)

            elif tag.data_type == DataType.WORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'H'}", *data)
                else:
                    packed_data = struct.pack(">H", data)

            elif tag.data_type == DataType.DWORD:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'I'}", *data)
                else:
                    packed_data = struct.pack(">I", data)

            elif tag.data_type == DataType.DINT:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'l'}", *data)
                else:
                    packed_data = struct.pack(">l", data)

            elif tag.data_type == DataType.REAL:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'f'}", *data)
                else:
                    packed_data = struct.pack(">f", data)
            elif tag.data_type == DataType.LREAL:
                transport_size = DataTypeData.BYTE_WORD_DWORD
                new_length = tag.length * DataTypeSize[tag.data_type] * 8
                if isinstance(data, tuple):
                    packed_data = struct.pack(f">{tag.length * 'd'}", *data)
                else:
                    packed_data = struct.pack(">d", data)         
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
        tag_request_size = READ_REQ_PARAM_SIZE_TAG
        tag_response_size = READ_RES_PARAM_SIZE_TAG + tag.size()

        if (
            READ_REQ_OVERHEAD + tag_request_size >= max_pdu
            or READ_RES_OVERHEAD + tag_response_size > max_pdu
        ):
            tag_size = tag.size()
            raise S7AddressError(
                f"{tag} too big -> it cannot fit the size of the negotiated PDU ({max_pdu})."
                f" Tag size: {tag_size} bytes."
            )

        elif (
            cumulated_request_size + tag_request_size < max_pdu
            and cumulated_response_size + tag_response_size < max_pdu
            and len(requests[-1]) < MAX_READ_TAGS
        ):
            requests[-1].append(tag)

            cumulated_request_size += READ_REQ_PARAM_SIZE_TAG
            cumulated_response_size += READ_RES_PARAM_SIZE_TAG + tag.size()

        else:
            requests.append([tag])
            cumulated_request_size = READ_REQ_OVERHEAD + READ_REQ_PARAM_SIZE_TAG
            cumulated_response_size = (
                READ_RES_OVERHEAD + READ_RES_PARAM_SIZE_TAG + tag.size()
            )

    return requests


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
    groups: TagsMap = {}

    cum_req = READ_REQ_OVERHEAD
    cum_res = READ_RES_OVERHEAD

    # --- 0) Pre-bucket BIT tags by (area, db, byte_start) ---
    # This avoids collisions when many bits belong to the same byte (e.g. X0.0..X0.7),
    # and it also works around PLCs that do not support single BIT reads reliably.
    bit_buckets: Dict[Tuple[int, int, int], List[Tuple[int, S7Tag]]] = {}
    non_bits: List[Tuple[int, S7Tag]] = []

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

    # Sort by address (the index is used only for stable ordering in the final decoded output)
    sorted_tags = sorted(
        work,
        key=lambda elem: (elem[1].memory_area.value, elem[1].db_number, elem[1].start),
    )

    def _tag_request_size(_: S7Tag) -> int:
        return READ_REQ_PARAM_SIZE_TAG

    def _tag_response_size(t: S7Tag) -> int:
        return READ_RES_PARAM_SIZE_TAG + t.size()

    def _check_tag_fits(t: S7Tag) -> None:
        # Check single-tag feasibility against negotiated PDU size
        if (
            READ_REQ_OVERHEAD + _tag_request_size(t) >= max_pdu
            or READ_RES_OVERHEAD + _tag_response_size(t) > max_pdu
        ):
            raise S7AddressError(
                f"{t} too big -> it cannot fit negotiated PDU ({max_pdu}). "
                f"Tag size: {t.size()} bytes."
            )

    for idx, tag in sorted_tags:
        _check_tag_fits(tag)

        # Ensure every tag has an entry in the mapping
        if tag not in groups:
            groups[tag] = [(idx, tag)]

        # First element in current request
        if not requests[-1]:
            requests[-1].append(tag)
            cum_req += _tag_request_size(tag)
            cum_res += _tag_response_size(tag)
            continue

        # If there is no room in the current request, start a new one
        if not (
            cum_req + _tag_request_size(tag) < max_pdu
            and cum_res + _tag_response_size(tag) < max_pdu
            and len(requests[-1]) < MAX_READ_TAGS
        ):
            requests.append([tag])
            cum_req = READ_REQ_OVERHEAD + _tag_request_size(tag)
            cum_res = READ_RES_OVERHEAD + _tag_response_size(tag)
            continue

        prev = requests[-1][-1]

        # Attempt merging with previous tag if in the same memory area and DB
        if prev.memory_area == tag.memory_area and prev.db_number == tag.db_number:
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

            if merge_ok:
                new_start = prev_start
                new_end = max(prev_end, tag_end)
                new_len = new_end - new_start

                new_tag = S7Tag(
                    memory_area=prev.memory_area,
                    db_number=prev.db_number,
                    data_type=DataType.BYTE,
                    start=new_start,
                    bit_offset=0,
                    length=new_len,
                )

                # Request tag count does not increase (we replace prev with new_tag),
                # only the response payload for that item grows.
                delta_res = new_tag.size() - prev.size()
                if cum_res + delta_res < max_pdu:
                    prev_map = groups.pop(prev, [(idx, prev)])
                    cur_map = groups.pop(tag, [(idx, tag)])
                    groups[new_tag] = prev_map + cur_map

                    requests[-1][-1] = new_tag
                    cum_res += delta_res
                    continue

        # No merge: append tag to the request
        requests[-1].append(tag)
        cum_req += _tag_request_size(tag)
        cum_res += _tag_response_size(tag)

    return requests, groups




def prepare_write_requests_and_values(
    tags: Sequence[S7Tag], values: Sequence[Value], max_pdu: int
) -> Tuple[List[List[S7Tag]], List[List[Value]]]:
    requests: List[List[S7Tag]] = [[]]
    requests_values: List[List[Value]] = [[]]

    request_size = WRITE_REQ_OVERHEAD
    response_size = WRITE_RES_OVERHEAD

    for i, tag in enumerate(tags):
        tag_size = tag.size()
        tag_padding = tag_size % 2

        if (
            WRITE_REQ_OVERHEAD + WRITE_REQ_PARAM_SIZE_TAG + tag_size >= max_pdu
            or WRITE_RES_OVERHEAD + tag_size + 1 >= max_pdu
        ):
            raise S7AddressError(
                f"{tag} too big -> it cannot fit the size of the negotiated PDU ({max_pdu})"
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
