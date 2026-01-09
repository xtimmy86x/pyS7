"""
Tests for TSAP (Transport Service Access Point) functionality in S7Client.
"""
import pytest

from pyS7.client import S7Client
from pyS7.constants import ConnectionType


class TestTSAPStringConversion:
    """Tests for TSAP string conversion (TIA Portal format)."""

    def test_tsap_from_string_valid(self) -> None:
        """Test conversion from TIA Portal TSAP string to integer."""
        assert S7Client.tsap_from_string("03.00") == 0x0300
        assert S7Client.tsap_from_string("03.01") == 0x0301
        assert S7Client.tsap_from_string("22.00") == 0x2200
        assert S7Client.tsap_from_string("10.00") == 0x1000
        assert S7Client.tsap_from_string("01.01") == 0x0101
        assert S7Client.tsap_from_string("00.00") == 0x0000

    def test_tsap_from_string_leading_zeros(self) -> None:
        """Test that leading zeros are handled correctly."""
        assert S7Client.tsap_from_string("03.00") == 0x0300
        assert S7Client.tsap_from_string("3.0") == 0x0300
        assert S7Client.tsap_from_string("003.000") == 0x0300

    def test_tsap_from_string_invalid_format(self) -> None:
        """Test that invalid TSAP string formats are rejected."""
        with pytest.raises(ValueError, match="must be in format 'XX.YY'"):
            S7Client.tsap_from_string("0300")
        
        with pytest.raises(ValueError, match="must be in format 'XX.YY'"):
            S7Client.tsap_from_string("03.00.01")
        
        with pytest.raises(ValueError, match="must be in format 'XX.YY'"):
            S7Client.tsap_from_string("03")

    def test_tsap_from_string_invalid_numbers(self) -> None:
        """Test that non-numeric TSAP strings are rejected."""
        with pytest.raises(ValueError, match="must contain hexadecimal numbers"):
            S7Client.tsap_from_string("XX.YY")
        
        with pytest.raises(ValueError, match="must contain hexadecimal numbers"):
            S7Client.tsap_from_string("03.gg")

    def test_tsap_from_string_out_of_range(self) -> None:
        """Test that TSAP string values out of byte range are rejected."""
        with pytest.raises(ValueError, match="First byte must be in range 0x00-0xFF"):
            S7Client.tsap_from_string("100.00")  # 0x100 > 0xFF
        
        with pytest.raises(ValueError, match="Second byte must be in range 0x00-0xFF"):
            S7Client.tsap_from_string("03.100")  # 0x100 > 0xFF
        
        with pytest.raises(ValueError, match="First byte must be in range 0x00-0xFF"):
            S7Client.tsap_from_string("-1.00")  # -1 parses but is out of range

    def test_tsap_from_string_wrong_type(self) -> None:
        """Test that non-string input is rejected."""
        with pytest.raises(ValueError, match="tsap_str must be a string"):
            S7Client.tsap_from_string(0x0300)  # type: ignore
        
        with pytest.raises(ValueError, match="tsap_str must be a string"):
            S7Client.tsap_from_string(None)  # type: ignore

    def test_tsap_to_string_valid(self) -> None:
        """Test conversion from integer TSAP to TIA Portal string."""
        assert S7Client.tsap_to_string(0x0300) == "03.00"
        assert S7Client.tsap_to_string(0x0301) == "03.01"
        assert S7Client.tsap_to_string(0x2200) == "22.00"  # 0x22 in hex
        assert S7Client.tsap_to_string(0x1000) == "10.00"  # 0x10 in hex
        assert S7Client.tsap_to_string(0x0101) == "01.01"
        assert S7Client.tsap_to_string(0x0000) == "00.00"
        assert S7Client.tsap_to_string(0xFFFF) == "ff.ff"

    def test_tsap_to_string_edge_values(self) -> None:
        """Test TSAP to string conversion with edge values."""
        assert S7Client.tsap_to_string(0x0001) == "00.01"
        assert S7Client.tsap_to_string(0x0100) == "01.00"
        assert S7Client.tsap_to_string(0xFF00) == "ff.00"
        assert S7Client.tsap_to_string(0x00FF) == "00.ff"

    def test_tsap_to_string_out_of_range(self) -> None:
        """Test that TSAP values out of range are rejected."""
        with pytest.raises(ValueError, match="tsap must be in range 0x0000-0xFFFF"):
            S7Client.tsap_to_string(0x10000)
        
        with pytest.raises(ValueError, match="tsap must be in range 0x0000-0xFFFF"):
            S7Client.tsap_to_string(-1)

    def test_tsap_to_string_wrong_type(self) -> None:
        """Test that non-integer input is rejected."""
        with pytest.raises(ValueError, match="tsap must be an integer"):
            S7Client.tsap_to_string("03.00")  # type: ignore
        
        with pytest.raises(ValueError, match="tsap must be an integer"):
            S7Client.tsap_to_string(None)  # type: ignore

    def test_tsap_roundtrip_conversion(self) -> None:
        """Test that conversion from string to int and back preserves value."""
        test_values = ["03.00", "03.01", "22.00", "10.00", "00.00", "ff.ff"]
        for tsap_str in test_values:
            tsap_int = S7Client.tsap_from_string(tsap_str)
            result_str = S7Client.tsap_to_string(tsap_int)
            # Normalize to 2-digit hex format for comparison
            expected = ".".join(f"{int(x, 16):02x}" for x in tsap_str.split("."))
            assert result_str == expected, f"Roundtrip failed for {tsap_str}"


class TestTSAPValidation:
    """Tests for TSAP validation in S7Client."""

    def test_valid_tsap_values(self) -> None:
        """Test that valid TSAP values are accepted."""
        # Standard TSAP values
        client = S7Client(
            address="192.168.0.1",
            local_tsap=0x0100,
            remote_tsap=0x0101,
            timeout=1.0
        )
        assert client.local_tsap == 0x0100
        assert client.remote_tsap == 0x0101

    def test_tsap_edge_values(self) -> None:
        """Test TSAP validation with edge case values."""
        # Minimum values
        client = S7Client(
            address="192.168.0.1",
            local_tsap=0x0000,
            remote_tsap=0x0000,
            timeout=1.0
        )
        assert client.local_tsap == 0x0000
        assert client.remote_tsap == 0x0000

        # Maximum values
        client = S7Client(
            address="192.168.0.1",
            local_tsap=0xFFFF,
            remote_tsap=0xFFFF,
            timeout=1.0
        )
        assert client.local_tsap == 0xFFFF
        assert client.remote_tsap == 0xFFFF

    def test_invalid_tsap_out_of_range_high(self) -> None:
        """Test that TSAP values above 0xFFFF are rejected."""
        with pytest.raises(ValueError, match="local_tsap must be in range 0x0000-0xFFFF"):
            S7Client(
                address="192.168.0.1",
                local_tsap=0x10000,
                remote_tsap=0x0101,
                timeout=1.0
            )

        with pytest.raises(ValueError, match="remote_tsap must be in range 0x0000-0xFFFF"):
            S7Client(
                address="192.168.0.1",
                local_tsap=0x0100,
                remote_tsap=0x10000,
                timeout=1.0
            )

    def test_invalid_tsap_negative(self) -> None:
        """Test that negative TSAP values are rejected."""
        with pytest.raises(ValueError, match="local_tsap must be in range"):
            S7Client(
                address="192.168.0.1",
                local_tsap=-1,
                remote_tsap=0x0101,
                timeout=1.0
            )

        with pytest.raises(ValueError, match="remote_tsap must be in range"):
            S7Client(
                address="192.168.0.1",
                local_tsap=0x0100,
                remote_tsap=-1,
                timeout=1.0
            )

    def test_invalid_tsap_wrong_type(self) -> None:
        """Test that invalid string TSAP formats are rejected (strings are now valid if properly formatted)."""
        # Strings are now accepted, but must be in valid format
        with pytest.raises(ValueError, match="TSAP string must be in format 'XX.YY'"):
            S7Client(
                address="192.168.0.1",
                local_tsap="0x0100",  # Invalid format (0x prefix not allowed)
                remote_tsap=0x0101,
                timeout=1.0
            )

        with pytest.raises(ValueError, match="TSAP string must be in format 'XX.YY'"):
            S7Client(
                address="192.168.0.1",
                local_tsap=0x0100,
                remote_tsap="0x0101",  # Invalid format (0x prefix not allowed)
                timeout=1.0
            )

    def test_invalid_only_local_tsap(self) -> None:
        """Test that providing only local_tsap is rejected."""
        with pytest.raises(ValueError, match="Both local_tsap and remote_tsap must be provided together"):
            S7Client(
                address="192.168.0.1",
                local_tsap=0x0100,
                remote_tsap=None,
                timeout=1.0
            )

    def test_invalid_only_remote_tsap(self) -> None:
        """Test that providing only remote_tsap is rejected."""
        with pytest.raises(ValueError, match="Both local_tsap and remote_tsap must be provided together"):
            S7Client(
                address="192.168.0.1",
                local_tsap=None,
                remote_tsap=0x0101,
                timeout=1.0
            )

    def test_no_tsap_uses_rack_slot(self) -> None:
        """Test that omitting TSAP values falls back to rack/slot."""
        client = S7Client(
            address="192.168.0.1",
            rack=0,
            slot=1,
            timeout=1.0
        )
        assert client.rack == 0
        assert client.slot == 1
        assert client.local_tsap is None
        assert client.remote_tsap is None


class TestTSAPCalculator:
    """Tests for tsap_from_rack_slot helper method."""

    def test_basic_calculations(self) -> None:
        """Test basic TSAP calculations from rack/slot."""
        assert S7Client.tsap_from_rack_slot(0, 0) == 0x0100
        assert S7Client.tsap_from_rack_slot(0, 1) == 0x0101
        assert S7Client.tsap_from_rack_slot(0, 2) == 0x0102
        assert S7Client.tsap_from_rack_slot(1, 0) == 0x0120
        assert S7Client.tsap_from_rack_slot(1, 1) == 0x0121

    def test_edge_case_calculations(self) -> None:
        """Test TSAP calculations with edge case rack/slot values."""
        # Maximum rack (7) and slot (31)
        assert S7Client.tsap_from_rack_slot(7, 31) == 0x01FF
        # Minimum values
        assert S7Client.tsap_from_rack_slot(0, 0) == 0x0100

    def test_formula_correctness(self) -> None:
        """Test that the TSAP formula is correct: 0x0100 | (rack * 32 + slot)."""
        for rack in range(8):
            for slot in range(32):
                expected = 0x0100 | (rack * 32 + slot)
                assert S7Client.tsap_from_rack_slot(rack, slot) == expected

    def test_invalid_rack_negative(self) -> None:
        """Test that negative rack values are rejected."""
        with pytest.raises(ValueError, match="rack must be in range 0-7"):
            S7Client.tsap_from_rack_slot(-1, 0)

    def test_invalid_rack_too_high(self) -> None:
        """Test that rack values above 7 are rejected."""
        with pytest.raises(ValueError, match="rack must be in range 0-7"):
            S7Client.tsap_from_rack_slot(8, 0)

    def test_invalid_slot_negative(self) -> None:
        """Test that negative slot values are rejected."""
        with pytest.raises(ValueError, match="slot must be in range 0-31"):
            S7Client.tsap_from_rack_slot(0, -1)

    def test_invalid_slot_too_high(self) -> None:
        """Test that slot values above 31 are rejected."""
        with pytest.raises(ValueError, match="slot must be in range 0-31"):
            S7Client.tsap_from_rack_slot(0, 32)

    def test_invalid_type_rack(self) -> None:
        """Test that non-integer rack values are rejected."""
        with pytest.raises(ValueError, match="rack and slot must be integers"):
            S7Client.tsap_from_rack_slot("0", 1)  # type: ignore

    def test_invalid_type_slot(self) -> None:
        """Test that non-integer slot values are rejected."""
        with pytest.raises(ValueError, match="rack and slot must be integers"):
            S7Client.tsap_from_rack_slot(0, "1")  # type: ignore


class TestTSAPIntegration:
    """Integration tests for TSAP functionality."""

    def test_tsap_string_in_constructor(self) -> None:
        """Test that TIA Portal TSAP strings work in S7Client constructor."""
        client = S7Client(
            address="192.168.0.1",
            local_tsap="03.00",
            remote_tsap="03.01",
            timeout=1.0
        )
        assert client.local_tsap == 0x0300
        assert client.remote_tsap == 0x0301

    def test_tsap_mixed_string_int(self) -> None:
        """Test that mixing string and integer TSAP works."""
        client = S7Client(
            address="192.168.0.1",
            local_tsap="03.00",
            remote_tsap=0x0301,
            timeout=1.0
        )
        assert client.local_tsap == 0x0300
        assert client.remote_tsap == 0x0301

    def test_tsap_string_validation_in_constructor(self) -> None:
        """Test that invalid TSAP strings are caught in constructor."""
        with pytest.raises(ValueError, match="must be in format 'XX.YY'"):
            S7Client(
                address="192.168.0.1",
                local_tsap="invalid",
                remote_tsap="03.01"
            )

    def test_tsap_overrides_rack_slot(self) -> None:
        """Test that TSAP values override rack/slot when both are provided."""
        client = S7Client(
            address="192.168.0.1",
            rack=0,
            slot=1,
            local_tsap=0x0200,
            remote_tsap=0x0300,
            timeout=1.0
        )
        # TSAP should be set
        assert client.local_tsap == 0x0200
        assert client.remote_tsap == 0x0300
        # Rack/slot should still be stored (for compatibility)
        assert client.rack == 0
        assert client.slot == 1

    def test_client_creation_with_calculator(self) -> None:
        """Test creating client using the TSAP calculator."""
        remote_tsap = S7Client.tsap_from_rack_slot(0, 2)
        client = S7Client(
            address="192.168.0.1",
            local_tsap=0x0100,
            remote_tsap=remote_tsap,
            timeout=1.0
        )
        assert client.local_tsap == 0x0100
        assert client.remote_tsap == 0x0102

    def test_default_rack_slot_when_tsap_provided(self) -> None:
        """Test that rack/slot default to 0 when TSAP is provided."""
        client = S7Client(
            address="192.168.0.1",
            local_tsap=0x0100,
            remote_tsap=0x0101,
            timeout=1.0
        )
        assert client.rack == 0
        assert client.slot == 0
        assert client.local_tsap == 0x0100
        assert client.remote_tsap == 0x0101

    def test_multiple_clients_different_tsap(self) -> None:
        """Test creating multiple clients with different TSAP values."""
        client1 = S7Client(
            address="192.168.0.1",
            local_tsap=0x0100,
            remote_tsap=0x0101,
            timeout=1.0
        )
        client2 = S7Client(
            address="192.168.0.2",
            local_tsap=0x0100,
            remote_tsap=0x0102,
            timeout=1.0
        )
        
        assert client1.remote_tsap == 0x0101
        assert client2.remote_tsap == 0x0102
        assert client1.address != client2.address


class TestTSAPBackwardCompatibility:
    """Tests to ensure TSAP changes don't break existing functionality."""

    def test_traditional_rack_slot_still_works(self) -> None:
        """Test that traditional rack/slot initialization still works."""
        client = S7Client(
            address="192.168.0.1",
            rack=0,
            slot=1,
            connection_type=ConnectionType.S7Basic,
            port=102,
            timeout=5.0
        )
        assert client.rack == 0
        assert client.slot == 1
        assert client.local_tsap is None
        assert client.remote_tsap is None

    def test_connection_type_with_tsap(self) -> None:
        """Test that connection_type can be used with TSAP."""
        client = S7Client(
            address="192.168.0.1",
            connection_type=ConnectionType.PG,
            local_tsap=0x0100,
            remote_tsap=0x0101,
            timeout=1.0
        )
        assert client.connection_type == ConnectionType.PG
        assert client.local_tsap == 0x0100
        assert client.remote_tsap == 0x0101

    def test_all_connection_types(self) -> None:
        """Test TSAP with all connection types."""
        for conn_type in [ConnectionType.S7Basic, ConnectionType.PG, ConnectionType.OP]:
            client = S7Client(
                address="192.168.0.1",
                connection_type=conn_type,
                local_tsap=0x0100,
                remote_tsap=0x0101,
                timeout=1.0
            )
            assert client.connection_type == conn_type
            assert client.local_tsap == 0x0100
