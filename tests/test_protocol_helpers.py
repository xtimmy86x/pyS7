import logging

import pytest

from pyS7 import AsyncS7Client, ReadResult, S7Client, WriteResult
from pyS7._protocol import (
    read_item_data_length,
    tsap_from_rack_slot,
    tsap_from_string,
    tsap_to_string,
    validate_and_adjust_pdu,
    validate_tsap,
)
from pyS7.results import ReadResult as SharedReadResult
from pyS7.results import WriteResult as SharedWriteResult


def test_result_types_have_one_canonical_definition() -> None:
    assert ReadResult is SharedReadResult
    assert WriteResult is SharedWriteResult


@pytest.mark.parametrize("text,value", [("03.00", 0x0300), ("22.0a", 0x220A)])
def test_shared_tsap_conversion_and_client_parity(text: str, value: int) -> None:
    assert tsap_from_string(text) == value
    assert tsap_to_string(value) == text.lower()
    assert S7Client.tsap_from_string(text) == AsyncS7Client.tsap_from_string(text)


@pytest.mark.parametrize("value", ["0300", "03.gg", "100.00"])
def test_shared_tsap_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        tsap_from_string(value)


def test_shared_tsap_validation_and_rack_slot() -> None:
    assert tsap_from_rack_slot(0, 1) == 0x0101
    validate_tsap(0x0100, 0x0101)
    with pytest.raises(ValueError):
        validate_tsap(0x0100, None)


def test_shared_pdu_and_item_length() -> None:
    assert validate_and_adjust_pdu(960, 480, logging.getLogger(__name__)) == 480
    assert read_item_data_length(0x04, 16, 99) == 2
    assert read_item_data_length(0x09, 3, 99) == 3
