"""
Unit tests for CPU status reading functionality.
"""

import pytest
import struct
from pyS7.constants import SZLId, MessageType
from pyS7.requests import SZLRequest
from pyS7.responses import SZLResponse


class TestSZLRequest:
    """Tests for SZL request creation."""

    def test_szl_request_creation(self):
        """Test that SZL request is created correctly."""
        request = SZLRequest(szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000)
        
        # Check that request is a bytearray
        assert isinstance(request.request, bytearray)
        
        # Check TPKT header
        assert request.request[0] == 0x03  # TPKT version
        assert request.request[1] == 0x00  # Reserved
        
        # Check S7 protocol ID
        assert request.request[7] == 0x32
        
        # Check message type (USERDATA)
        assert request.request[8] == MessageType.USERDATA.value

    def test_szl_request_serialization(self):
        """Test that SZL request can be serialized."""
        request = SZLRequest(szl_id=SZLId.CPU_DIAGNOSTIC_STATUS, szl_index=0x0000)
        serialized = request.serialize()
        
        assert isinstance(serialized, bytes)
        assert len(serialized) > 0


class TestSZLResponse:
    """Tests for SZL response parsing."""

    def create_mock_szl_response(self, status_byte: int = 0x08) -> bytes:
        """Create a mock SZL response for testing."""
        # Build a minimal valid SZL response
        packet = bytearray()
        
        # TPKT header
        packet.extend(b"\x03\x00")
        tpkt_length_pos = len(packet)
        packet.extend(b"\x00\x00")  # Placeholder for length
        
        # COTP header
        packet.extend(b"\x02\xf0\x80")
        
        # S7 header
        packet.extend(b"\x32")  # Protocol ID
        packet.extend(MessageType.USERDATA.value.to_bytes(1, byteorder="big"))
        packet.extend(b"\x00\x00")  # Reserved
        packet.extend(b"\x00\x00")  # PDU reference
        param_length_pos = len(packet)
        packet.extend(b"\x00\x00")  # Placeholder for param length
        data_length_pos = len(packet)
        packet.extend(b"\x00\x00")  # Placeholder for data length
        
        # Parameter section (minimal)
        param_start = len(packet)
        packet.extend(b"\x00\x01\x12")  # Parameter head
        packet.extend(b"\x04")  # Parameter length
        packet.extend(b"\x12")  # Method: Response
        packet.extend(b"\x04")  # Function
        packet.extend(b"\x01")  # Subfunction
        packet.extend(b"\x01")  # Sequence
        
        # Data section
        data_start = len(packet)
        packet.extend(b"\xff")  # Return code (success)
        packet.extend(b"\x09")  # Transport size
        packet.extend(b"\x00\x1C")  # Data unit length (28 bytes: 8 header + 20 data)
        packet.extend(b"\x04\x24")  # SZL ID 0x0424
        packet.extend(b"\x00\x00")  # SZL index
        packet.extend(b"\x00\x14")  # Length of data record (20 bytes)
        packet.extend(b"\x00\x01")  # Number of data records (1)
        
        # Data record (20 bytes) - matching real PLC structure
        packet.extend(b"\x02")  # Byte 0: Reserved (typical value)
        packet.extend(b"\x51")  # Byte 1: Status bits (typical value)
        packet.extend(b"\xff")  # Byte 2: Event bits
        packet.extend(bytes([status_byte]))  # Byte 3: Operating mode (0x08=RUN, 0x03=STOP)
        packet.extend(b"\x00" * 16)  # Bytes 4-19: Reserved/additional diagnostic info
        
        # Update lengths
        param_length = data_start - param_start
        data_length = len(packet) - data_start
        tpkt_length = len(packet)
        
        packet[tpkt_length_pos:tpkt_length_pos + 2] = tpkt_length.to_bytes(2, byteorder="big")
        packet[param_length_pos:param_length_pos + 2] = param_length.to_bytes(2, byteorder="big")
        packet[data_length_pos:data_length_pos + 2] = data_length.to_bytes(2, byteorder="big")
        
        return bytes(packet)

    def test_parse_szl_response(self):
        """Test parsing a valid SZL response."""
        response_bytes = self.create_mock_szl_response(status_byte=0x08)  # RUN
        response = SZLResponse(response=response_bytes)
        
        parsed = response.parse()
        
        assert parsed["szl_id"] == 0x0424
        assert parsed["szl_index"] == 0x0000
        assert parsed["length_dr"] == 20
        assert parsed["n_dr"] == 1
        assert len(parsed["data"]) == 20

    def test_parse_cpu_status_run(self):
        """Test parsing CPU status - RUN mode."""
        response_bytes = self.create_mock_szl_response(status_byte=0x08)  # Byte 3 = 0x08 = RUN
        response = SZLResponse(response=response_bytes)
        
        status = response.parse_cpu_status()
        assert status == "RUN"

    def test_parse_cpu_status_stop(self):
        """Test parsing CPU status - STOP mode."""
        response_bytes = self.create_mock_szl_response(status_byte=0x03)  # Byte 3 = 0x03 = STOP
        response = SZLResponse(response=response_bytes)
        
        status = response.parse_cpu_status()
        assert status == "STOP"

    def test_parse_cpu_status_unknown(self):
        """Test parsing CPU status - unknown mode."""
        response_bytes = self.create_mock_szl_response(status_byte=0x05)  # Unknown value
        response = SZLResponse(response=response_bytes)
        
        status = response.parse_cpu_status()
        assert status.startswith("UNKNOWN")
        assert "0x05" in status

    def test_invalid_response_too_short(self):
        """Test handling of response that is too short."""
        response_bytes = b"\x03\x00\x00\x10"  # Too short
        response = SZLResponse(response=response_bytes)
        
        with pytest.raises(ValueError, match="too short"):
            response.parse()

    def test_invalid_tpkt_version(self):
        """Test handling of invalid TPKT version."""
        response_bytes = bytearray(self.create_mock_szl_response())
        response_bytes[0] = 0x02  # Invalid version
        
        response = SZLResponse(response=bytes(response_bytes))
        
        with pytest.raises(ValueError, match="Invalid TPKT version"):
            response.parse()


class TestSZLConstants:
    """Tests for SZL-related constants."""

    def test_szl_id_enum(self):
        """Test that SZL ID enum values are correct."""
        assert SZLId.CPU_DIAGNOSTIC_STATUS.value == 0x0424
        assert SZLId.MODULE_IDENTIFICATION.value == 0x0011
        assert SZLId.CPU_CHARACTERISTICS.value == 0x0131

    def test_message_type_userdata(self):
        """Test that USERDATA message type is defined."""
        assert MessageType.USERDATA.value == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
