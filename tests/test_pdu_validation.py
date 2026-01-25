"""Tests for PDU size validation during connection negotiation."""

import logging
from unittest.mock import MagicMock

import pytest

from pyS7 import S7Client, S7ConnectionError
from pyS7.constants import (
    ConnectionType,
    MAX_PDU_SIZE,
    MIN_PDU_SIZE,
    RECOMMENDED_MIN_PDU,
)


class TestPDUValidation:
    """Test PDU size validation logic."""

    def test_validate_pdu_normal_case(self) -> None:
        """Test normal PDU negotiation within acceptable range."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # Normal negotiation: requested 960, got 960
        result = client._validate_and_adjust_pdu(960, 960)
        assert result == 960
        
        # Normal negotiation: requested 960, got 480
        result = client._validate_and_adjust_pdu(960, 480)
        assert result == 480

    def test_validate_pdu_below_minimum(self) -> None:
        """Test that PDU below minimum raises error."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # PDU too small
        with pytest.raises(S7ConnectionError, match="invalid PDU size"):
            client._validate_and_adjust_pdu(960, MIN_PDU_SIZE - 1)
        
        # Zero PDU
        with pytest.raises(S7ConnectionError, match="invalid PDU size"):
            client._validate_and_adjust_pdu(960, 0)
        
        # Negative PDU
        with pytest.raises(S7ConnectionError, match="invalid PDU size"):
            client._validate_and_adjust_pdu(960, -10)

    def test_validate_pdu_above_maximum(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that PDU above maximum is clamped with warning."""
        client = S7Client("192.168.1.1", 0, 1)
        
        with caplog.at_level(logging.WARNING):
            result = client._validate_and_adjust_pdu(960, MAX_PDU_SIZE + 1000)
        
        # Should clamp to maximum
        assert result == MAX_PDU_SIZE
        
        # Should log warning
        assert "unusually large PDU size" in caplog.text
        assert "clamping to protocol maximum" in caplog.text

    def test_validate_pdu_below_recommended(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test warning when PDU is below recommended minimum."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # PDU below recommended but above absolute minimum
        small_pdu = RECOMMENDED_MIN_PDU - 50
        assert small_pdu > MIN_PDU_SIZE  # Ensure test is valid
        
        with caplog.at_level(logging.WARNING):
            result = client._validate_and_adjust_pdu(960, small_pdu)
        
        # Should accept the value
        assert result == small_pdu
        
        # Should log warning
        assert "very small PDU" in caplog.text
        assert "may limit functionality" in caplog.text
        assert str(RECOMMENDED_MIN_PDU) in caplog.text

    def test_validate_pdu_significant_reduction(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test info message when PDU is significantly reduced."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # 50% reduction (should trigger info message)
        with caplog.at_level(logging.INFO):
            result = client._validate_and_adjust_pdu(960, 480)
        
        assert result == 480
        assert "reduced by 50%" in caplog.text
        assert "Operations will be automatically adjusted" in caplog.text

    def test_validate_pdu_small_reduction(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test no info message for small PDU reductions."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # 10% reduction (should not trigger info message)
        with caplog.at_level(logging.INFO):
            result = client._validate_and_adjust_pdu(960, 864)
        
        assert result == 864
        # Should not log reduction info (< 20% reduction)
        assert "reduced by" not in caplog.text

    def test_validate_pdu_edge_case_at_minimum(self) -> None:
        """Test PDU exactly at minimum boundary."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # Exactly at minimum should be accepted
        result = client._validate_and_adjust_pdu(960, MIN_PDU_SIZE)
        assert result == MIN_PDU_SIZE

    def test_validate_pdu_edge_case_at_recommended(self) -> None:
        """Test PDU exactly at recommended minimum."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # Exactly at recommended should be accepted without warning
        result = client._validate_and_adjust_pdu(960, RECOMMENDED_MIN_PDU)
        assert result == RECOMMENDED_MIN_PDU

    def test_validate_pdu_edge_case_at_maximum(self) -> None:
        """Test PDU exactly at maximum boundary."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # Exactly at maximum should be accepted
        result = client._validate_and_adjust_pdu(960, MAX_PDU_SIZE)
        assert result == MAX_PDU_SIZE

    def test_validate_pdu_increased_from_request(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that PDU larger than requested is accepted without warning."""
        client = S7Client("192.168.1.1", 0, 1)
        
        # PLC returns larger PDU than requested (unusual but valid)
        with caplog.at_level(logging.INFO):
            result = client._validate_and_adjust_pdu(480, 960)
        
        assert result == 960
        # Should not log reduction info (PDU increased, not decreased)
        assert "reduced" not in caplog.text
