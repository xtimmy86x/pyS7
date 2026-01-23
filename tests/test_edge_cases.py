"""Tests for edge cases and boundary conditions in pyS7."""

import struct
from typing import Any

import pytest

from pyS7.constants import DataType, MemoryArea
from pyS7.errors import S7AddressError, S7PDUError, S7ReadResponseError
from pyS7.requests import prepare_requests, prepare_write_requests_and_values
from pyS7.responses import extract_bit_from_byte, parse_read_response
from pyS7.tag import S7Tag


class TestTagBoundaryConditions:
    """Test S7Tag with boundary values."""

    def test_bit_offset_boundary_values(self) -> None:
        """Test bit offset at boundaries (0 and 7)."""
        # Min boundary
        tag_min = S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, 0, 1)
        assert tag_min.bit_offset == 0
        
        # Max boundary
        tag_max = S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, 7, 1)
        assert tag_max.bit_offset == 7

    def test_bit_offset_out_of_range(self) -> None:
        """Test bit offset beyond valid range."""
        with pytest.raises(ValueError, match="Invalid 'bit_offset'.*between 0 and 7"):
            S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, 8, 1)
        
        with pytest.raises(ValueError, match="Invalid 'bit_offset'.*between 0 and 7"):
            S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, -1, 1)

    def test_zero_length_tag(self) -> None:
        """Test tag with zero length."""
        with pytest.raises(ValueError, match="Invalid 'length'.*positive value"):
            S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 0)

    def test_single_element_array(self) -> None:
        """Test array with single element."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        assert tag.length == 1
        assert tag.size() == 2  # INT is 2 bytes

    def test_large_db_number(self) -> None:
        """Test with large DB number at boundary."""
        # DB numbers can go up to 65535 (2 bytes unsigned)
        tag = S7Tag(MemoryArea.DB, 65535, DataType.INT, 0, 0, 1)
        assert tag.db_number == 65535

    def test_negative_db_number(self) -> None:
        """Test negative DB number."""
        with pytest.raises(ValueError, match="Invalid 'db_number'.*non-negative"):
            S7Tag(MemoryArea.DB, -1, DataType.INT, 0, 0, 1)

    def test_large_start_address(self) -> None:
        """Test with large start address."""
        # Start address can be large
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 65534, 0, 1)
        assert tag.start == 65534

    def test_negative_start_address(self) -> None:
        """Test negative start address."""
        with pytest.raises(ValueError, match="Invalid 'start'.*non-negative"):
            S7Tag(MemoryArea.DB, 1, DataType.INT, -1, 0, 1)


class TestStringBoundaries:
    """Test string handling at boundaries."""

    def test_empty_string_length(self) -> None:
        """Test STRING with minimal length (1 for header)."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.STRING, 0, 0, 1)
        assert tag.size() == 3  # 2 header + 1 data

    def test_max_string_length(self) -> None:
        """Test STRING with maximum typical length (254)."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.STRING, 0, 0, 254)
        assert tag.size() == 256  # 2 header + 254 data

    def test_single_char_string(self) -> None:
        """Test STRING with length 1."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.STRING, 0, 0, 1)
        assert tag.size() == 3  # 2 header + 1 char

    def test_wstring_boundaries(self) -> None:
        """Test WSTRING with various lengths."""
        # Single char (minimum)
        tag_one = S7Tag(MemoryArea.DB, 1, DataType.WSTRING, 0, 0, 1)
        assert tag_one.size() == 6  # 4 header + 2 data
        
        # Two chars
        tag_two = S7Tag(MemoryArea.DB, 1, DataType.WSTRING, 0, 0, 2)
        assert tag_two.size() == 8  # 4 header + 4 data
        
        # Large
        tag_large = S7Tag(MemoryArea.DB, 1, DataType.WSTRING, 0, 0, 1000)
        assert tag_large.size() == 2004  # 4 header + 2000 data


class TestPDUBoundaryConditions:
    """Test PDU size boundary conditions."""

    def test_tag_exactly_at_pdu_limit(self) -> None:
        """Test tag that fits comfortably in PDU."""
        pdu_size = 240
        # READ_RES_OVERHEAD = 21, READ_RES_PARAM_SIZE_TAG = 5
        # cumulated_response_size = OVERHEAD + PARAM_SIZE + tag.size()
        # Must be < max_pdu (not <=)
        max_data = pdu_size - 21 - 5 - 1  # 213 bytes to be safe
        tag = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, max_data)
        
        # Should not raise
        requests = prepare_requests([tag], pdu_size)
        assert len(requests) == 1

    def test_tag_one_byte_over_pdu(self) -> None:
        """Test tag that exceeds PDU by one byte."""
        pdu_size = 240
        max_data = pdu_size - 21 - 5  # 214
        tag = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, max_data + 1)
        
        with pytest.raises(S7PDUError, match=r"requires \d+ bytes but PDU size is"):
            prepare_requests([tag], pdu_size)

    def test_minimal_pdu_size(self) -> None:
        """Test with minimal PDU size."""
        pdu_size = 50  # Very small PDU
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        
        # Should work with small tag
        requests = prepare_requests([tag], pdu_size)
        assert len(requests) == 1

    def test_write_pdu_boundary(self) -> None:
        """Test write at PDU boundary."""
        pdu_size = 240
        # WRITE_REQ_OVERHEAD = 18, WRITE_REQ_PARAM_SIZE_TAG = 12
        max_data = pdu_size - 18 - 12 - 4
        tag = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, max_data)
        values = [tuple([0] * max_data)]
        
        # Should split into multiple requests if too large
        requests, _ = prepare_write_requests_and_values([tag], values, pdu_size)
        assert len(requests) >= 1


class TestNumericBoundaries:
    """Test numeric data type boundaries."""

    def test_extract_bit_boundary_values(self) -> None:
        """Test bit extraction at boundaries."""
        # All bits off
        assert extract_bit_from_byte(0, 0) is False
        assert extract_bit_from_byte(0, 7) is False
        
        # All bits on
        assert extract_bit_from_byte(255, 0) is True
        assert extract_bit_from_byte(255, 7) is True
        
        # Only bit 0
        assert extract_bit_from_byte(1, 0) is True
        assert extract_bit_from_byte(1, 1) is False
        
        # Only bit 7
        assert extract_bit_from_byte(128, 7) is True
        assert extract_bit_from_byte(128, 6) is False

    def test_extract_bit_invalid_offset(self) -> None:
        """Test bit extraction with invalid offset."""
        with pytest.raises(ValueError, match="bit_offset must be between 0 and 7"):
            extract_bit_from_byte(100, 8)
        
        with pytest.raises(ValueError, match="bit_offset must be between 0 and 7"):
            extract_bit_from_byte(100, -1)

    def test_extract_bit_invalid_byte_value(self) -> None:
        """Test bit extraction with invalid byte value."""
        with pytest.raises(ValueError, match="byte_value must be between 0 and 255"):
            extract_bit_from_byte(256, 0)
        
        with pytest.raises(ValueError, match="byte_value must be between 0 and 255"):
            extract_bit_from_byte(-1, 0)


class TestResponseParsing:
    """Test response parsing edge cases."""

    def test_parse_read_response_truncated(self) -> None:
        """Test parsing truncated response."""
        tags = [S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 1)]
        
        # Response too short
        response = b"\x03\x00\x00\x10" + b"\x00" * 12
        
        with pytest.raises(S7ReadResponseError, match="response too short"):
            parse_read_response(response, tags)


class TestTagContainment:
    """Test tag containment edge cases."""

    def test_tag_contains_itself(self) -> None:
        """Test if tag contains itself."""
        tag = S7Tag(MemoryArea.DB, 1, DataType.INT, 10, 0, 1)
        assert tag in tag

    def test_tag_contains_exact_subset(self) -> None:
        """Test exact subset containment."""
        parent = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 10)
        child = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 10)
        assert child in parent

    def test_tag_adjacent_not_contained(self) -> None:
        """Test that adjacent tags don't contain each other."""
        tag1 = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)  # bytes 0-1
        tag2 = S7Tag(MemoryArea.DB, 1, DataType.INT, 2, 0, 1)  # bytes 2-3
        assert tag2 not in tag1
        assert tag1 not in tag2

    def test_tag_overlapping_start(self) -> None:
        """Test tag overlapping at start."""
        tag1 = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 5)   # bytes 0-4
        tag2 = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 4, 0, 2)   # bytes 4-5
        # tag2 starts inside tag1 but extends beyond
        assert tag2 not in tag1

    def test_different_memory_areas_not_contained(self) -> None:
        """Test tags in different memory areas."""
        tag1 = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        tag2 = S7Tag(MemoryArea.MERKER, 0, DataType.INT, 0, 0, 1)
        assert tag2 not in tag1

    def test_different_db_numbers_not_contained(self) -> None:
        """Test tags in different DBs."""
        tag1 = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
        tag2 = S7Tag(MemoryArea.DB, 2, DataType.INT, 0, 0, 1)
        assert tag2 not in tag1

    def test_bit_tag_containment(self) -> None:
        """Test bit tag containment."""
        byte_tag = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 0, 0, 1)
        bit_tag = S7Tag(MemoryArea.DB, 1, DataType.BIT, 0, 3, 1)
        # Bit should be contained in byte
        assert bit_tag in byte_tag

    def test_multiple_bits_same_byte(self) -> None:
        """Test multiple bit tags in same byte."""
        byte_tag = S7Tag(MemoryArea.DB, 1, DataType.BYTE, 5, 0, 1)
        bit0 = S7Tag(MemoryArea.DB, 1, DataType.BIT, 5, 0, 1)
        bit7 = S7Tag(MemoryArea.DB, 1, DataType.BIT, 5, 7, 1)
        
        assert bit0 in byte_tag
        assert bit7 in byte_tag
        # Containment logic doesn't check bit_offset, only start address
        # So bits at same start are considered mutually contained
        assert bit0 in bit7
        assert bit7 in bit0


class TestArrayBoundaries:
    """Test array handling at boundaries."""

    def test_single_element_arrays(self) -> None:
        """Test various data types with single element."""
        for dtype in [DataType.INT, DataType.DINT, DataType.REAL]:
            tag = S7Tag(MemoryArea.DB, 1, dtype, 0, 0, 1)
            assert tag.length == 1

    def test_large_array_size_calculation(self) -> None:
        """Test size calculation for large arrays."""
        # 1000 REALs = 4000 bytes
        tag = S7Tag(MemoryArea.DB, 1, DataType.REAL, 0, 0, 1000)
        assert tag.size() == 4000
        
        # 500 DINTs = 2000 bytes
        tag2 = S7Tag(MemoryArea.DB, 1, DataType.DINT, 0, 0, 500)
        assert tag2.size() == 2000


class TestMemoryAreaBoundaries:
    """Test different memory areas at boundaries."""

    def test_all_memory_areas_valid(self) -> None:
        """Test creating tags for all memory areas."""
        areas = [
            MemoryArea.DB,
            MemoryArea.INPUT,
            MemoryArea.OUTPUT,
            MemoryArea.MERKER,
            MemoryArea.TIMER,
            MemoryArea.COUNTER,
        ]
        
        for area in areas:
            db_num = 1 if area == MemoryArea.DB else 0
            tag = S7Tag(area, db_num, DataType.INT, 0, 0, 1)
            assert tag.memory_area == area

    def test_non_db_with_db_number(self) -> None:
        """Test that non-DB areas have db_number=0."""
        tag = S7Tag(MemoryArea.MERKER, 0, DataType.INT, 0, 0, 1)
        assert tag.db_number == 0

    def test_db_requires_db_number(self) -> None:
        """Test DB area works with various DB numbers."""
        for db_num in [1, 100, 65535]:
            tag = S7Tag(MemoryArea.DB, db_num, DataType.INT, 0, 0, 1)
            assert tag.db_number == db_num
