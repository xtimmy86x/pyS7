"""
Tests for handling of large arrays that exceed PDU size.
"""
import pytest
from typing import Any
from pyS7 import S7Client
from pyS7.tag import S7Tag
from pyS7.constants import DataType, MemoryArea
from pyS7.errors import S7AddressError


class TestLargeArrayHandling:
    """Test handling of arrays that exceed PDU size."""
    
    def test_large_byte_array_raises_error(self, monkeypatch: pytest.MonkeyPatch):
        """Test that large BYTE arrays raise clear error message."""
        client = S7Client(address="192.168.1.1", rack=0, slot=1)
        
        # Mock connection
        def mock_connect(self: Any, *args: Any) -> None:
            return None

        def mock_sendall(self: Any, bytes_request: bytes) -> None:
            return None

        connection_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x00\x08\x00\x08\x03\xc0"
        )
        pdu_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x07\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x01\x00\x01\x03\xc0\x00"
        )

        def _mock_recv_factory(*responses: bytes):
            from array import array
            buffers = [array("B", r) for r in responses]
            current: Any = None

            def _mock_recv(self: Any, buf_size: int) -> bytes:
                nonlocal current, buffers

                while current is None or len(current) == 0:
                    if not buffers:
                        return b""
                    current = buffers.pop(0)

                if len(current) <= buf_size:
                    chunk = current.tobytes()
                    current = None
                    return chunk

                chunk = current[:buf_size].tobytes()
                current = current[buf_size:]
                return chunk

            return _mock_recv

        monkeypatch.setattr("socket.socket.connect", mock_connect)
        monkeypatch.setattr("socket.socket.sendall", mock_sendall)
        monkeypatch.setattr(
            "socket.socket.recv", _mock_recv_factory(connection_response, pdu_response)
        )
        monkeypatch.setattr("socket.socket.shutdown", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.close", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.getpeername", lambda *args, **kwargs: ("192.168.1.1", 102))

        client.connect()
        client.pdu_size = 240  # Set small PDU for testing
        
        # Create a BYTE array that exceeds PDU (242 bytes data + 26 overhead = 268 > 240)
        large_tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=1,
            data_type=DataType.BYTE,
            start=0,
            bit_offset=0,
            length=242
        )
        
        with pytest.raises(S7AddressError) as exc_info:
            client.read([large_tag])
        
        error_msg = str(exc_info.value)
        assert "242 bytes" in error_msg
        assert "214 bytes" in error_msg  # max_data_size for PDU 240
        assert "BYTE arrays" in error_msg
        assert "smaller chunks" in error_msg
    
    def test_large_word_array_raises_error(self, monkeypatch: pytest.MonkeyPatch):
        """Test that large WORD arrays raise clear error message."""
        client = S7Client(address="192.168.1.1", rack=0, slot=1)
        
        # Mock connection (same as above)
        def mock_connect(self: Any, *args: Any) -> None:
            return None

        def mock_sendall(self: Any, bytes_request: bytes) -> None:
            return None

        connection_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x00\x08\x00\x08\x03\xc0"
        )
        pdu_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x07\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x01\x00\x01\x03\xc0\x00"
        )

        def _mock_recv_factory(*responses: bytes):
            from array import array
            buffers = [array("B", r) for r in responses]
            current: Any = None

            def _mock_recv(self: Any, buf_size: int) -> bytes:
                nonlocal current, buffers

                while current is None or len(current) == 0:
                    if not buffers:
                        return b""
                    current = buffers.pop(0)

                if len(current) <= buf_size:
                    chunk = current.tobytes()
                    current = None
                    return chunk

                chunk = current[:buf_size].tobytes()
                current = current[buf_size:]
                return chunk

            return _mock_recv

        monkeypatch.setattr("socket.socket.connect", mock_connect)
        monkeypatch.setattr("socket.socket.sendall", mock_sendall)
        monkeypatch.setattr(
            "socket.socket.recv", _mock_recv_factory(connection_response, pdu_response)
        )
        monkeypatch.setattr("socket.socket.shutdown", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.close", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.getpeername", lambda *args, **kwargs: ("192.168.1.1", 102))
        monkeypatch.setattr("socket.socket.shutdown", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.close", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.getpeername", lambda *args, **kwargs: ("192.168.1.1", 102))

        client.connect()
        client.pdu_size = 240
        
        # Create a WORD array that exceeds PDU (120 * 2 = 240 bytes data + 26 overhead = 266 > 240)
        large_tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=1,
            data_type=DataType.WORD,
            start=0,
            bit_offset=0,
            length=120
        )
        
        with pytest.raises(S7AddressError) as exc_info:
            client.read([large_tag])
        
        error_msg = str(exc_info.value)
        assert "240 bytes" in error_msg  # tag size
        assert "214 bytes" in error_msg  # max_data_size
        assert "WORD arrays" in error_msg
    
    def test_mixed_tags_with_large_array(self, monkeypatch: pytest.MonkeyPatch):
        """Test that mixed tags with one large array raises error for the large one."""
        client = S7Client(address="192.168.1.1", rack=0, slot=1)
        
        # Mock connection
        def mock_connect(self: Any, *args: Any) -> None:
            return None

        def mock_sendall(self: Any, bytes_request: bytes) -> None:
            return None

        connection_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x03\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x00\x08\x00\x08\x03\xc0"
        )
        pdu_response = (
            b"\x03\x00\x00\x1b\x02\xf0\x802\x07\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\xf0\x00\x01\x00\x01\x03\xc0\x00"
        )

        def _mock_recv_factory(*responses: bytes):
            from array import array
            buffers = [array("B", r) for r in responses]
            current: Any = None

            def _mock_recv(self: Any, buf_size: int) -> bytes:
                nonlocal current, buffers

                while current is None or len(current) == 0:
                    if not buffers:
                        return b""
                    current = buffers.pop(0)

                if len(current) <= buf_size:
                    chunk = current.tobytes()
                    current = None
                    return chunk

                chunk = current[:buf_size].tobytes()
                current = current[buf_size:]
                return chunk

            return _mock_recv

        monkeypatch.setattr("socket.socket.connect", mock_connect)
        monkeypatch.setattr("socket.socket.sendall", mock_sendall)
        monkeypatch.setattr(
            "socket.socket.recv", _mock_recv_factory(connection_response, pdu_response)
        )
        monkeypatch.setattr("socket.socket.shutdown", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.close", lambda *args, **kwargs: None)
        monkeypatch.setattr("socket.socket.getpeername", lambda *args, **kwargs: ("192.168.1.1", 102))

        client.connect()
        client.pdu_size = 240
        
        # Create a mix of tags
        normal_tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=1,
            data_type=DataType.INT,
            start=0,
            bit_offset=0,
            length=10
        )
        
        large_tag = S7Tag(
            memory_area=MemoryArea.DB,
            db_number=1,
            data_type=DataType.BYTE,
            start=100,
            bit_offset=0,
            length=242
        )
        
        # Should raise error for the large tag
        with pytest.raises(S7AddressError) as exc_info:
            client.read([normal_tag, large_tag])
        
        error_msg = str(exc_info.value)
        assert "242 bytes" in error_msg
        assert "start=100" in error_msg  # Confirm it's the right tag
