"""Strict batch-write failure semantics shared by sync and async clients."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pyS7 import AsyncS7Client, BatchWriteError, S7Client, WriteResult
from pyS7.constants import DataType, MemoryArea
from pyS7.tag import S7Tag

TAG = S7Tag(MemoryArea.DB, 1, DataType.INT, 0, 0, 1)
FAILED_RESULTS = [WriteResult(TAG, True), WriteResult(TAG, False, "PLC rejected write")]


def test_batch_write_error_is_structured_and_public() -> None:
    rollback_error = RuntimeError("rollback unavailable")
    error = BatchWriteError(
        "batch failed",
        FAILED_RESULTS,
        rollback_attempted=True,
        rollback_succeeded=False,
        rollback_error=rollback_error,
    )
    assert error.results == FAILED_RESULTS
    assert error.rollback_attempted is True
    assert error.rollback_succeeded is False
    assert error.rollback_error is rollback_error
    assert "batch failed" in str(error)


def test_sync_rollback_failure_preserves_write_results() -> None:
    client = MagicMock(spec=S7Client)
    client.read.return_value = [10]
    client.write_detailed.return_value = FAILED_RESULTS
    rollback_error = RuntimeError("connection lost")
    client.write.side_effect = rollback_error
    from pyS7 import BatchWriteTransaction

    transaction = BatchWriteTransaction(client)
    transaction.add(TAG, 100)
    with pytest.raises(BatchWriteError) as caught:
        transaction.commit()
    assert caught.value.results == FAILED_RESULTS
    assert caught.value.rollback_attempted is True
    assert caught.value.rollback_succeeded is False
    assert caught.value.rollback_error is rollback_error
    client.write.assert_called_once_with([TAG], [10])


def test_sync_context_failure_propagates_and_user_error_skips_commit() -> None:
    client = MagicMock(spec=S7Client)
    client.read.return_value = [10]
    client.write_detailed.return_value = FAILED_RESULTS
    from pyS7 import BatchWriteTransaction

    with pytest.raises(BatchWriteError):
        with BatchWriteTransaction(client) as batch:
            batch.add(TAG, 100)

    client.reset_mock()
    with pytest.raises(RuntimeError, match="user error"):
        with BatchWriteTransaction(client) as batch:
            batch.add(TAG, 100)
            raise RuntimeError("user error")
    client.read.assert_not_called()
    client.write_detailed.assert_not_called()


@pytest.mark.asyncio
async def test_async_failure_with_successful_rollback() -> None:
    client = MagicMock(spec=AsyncS7Client)
    client.read = AsyncMock(return_value=[10])
    client.write_detailed = AsyncMock(return_value=FAILED_RESULTS)
    client.write = AsyncMock(return_value=None)
    from pyS7 import AsyncBatchWriteTransaction

    transaction = AsyncBatchWriteTransaction(client)
    transaction.add(TAG, 100)
    with pytest.raises(BatchWriteError) as caught:
        await transaction.commit()
    assert caught.value.results == FAILED_RESULTS
    assert caught.value.rollback_attempted is True
    assert caught.value.rollback_succeeded is True
    assert caught.value.rollback_error is None
    client.write.assert_awaited_once_with([TAG], [10])


@pytest.mark.asyncio
async def test_async_rollback_failure_preserves_write_results() -> None:
    client = MagicMock(spec=AsyncS7Client)
    client.read = AsyncMock(return_value=[10])
    client.write_detailed = AsyncMock(return_value=FAILED_RESULTS)
    rollback_error = RuntimeError("connection lost")
    client.write = AsyncMock(side_effect=rollback_error)
    from pyS7 import AsyncBatchWriteTransaction

    transaction = AsyncBatchWriteTransaction(client)
    transaction.add(TAG, 100)
    with pytest.raises(BatchWriteError) as caught:
        await transaction.commit()
    assert caught.value.results == FAILED_RESULTS
    assert caught.value.rollback_attempted is True
    assert caught.value.rollback_succeeded is False
    assert caught.value.rollback_error is rollback_error


@pytest.mark.asyncio
async def test_async_no_rollback_and_snapshot_failure() -> None:
    client = MagicMock(spec=AsyncS7Client)
    client.read = AsyncMock(side_effect=RuntimeError("snapshot failed"))
    client.write_detailed = AsyncMock(return_value=FAILED_RESULTS)
    client.write = AsyncMock()
    from pyS7 import AsyncBatchWriteTransaction

    protected = AsyncBatchWriteTransaction(client)
    protected.add(TAG, 100)
    with pytest.raises(BatchWriteError) as caught:
        await protected.commit()
    assert caught.value.results == []
    client.write_detailed.assert_not_awaited()

    client.reset_mock()
    client.write_detailed = AsyncMock(return_value=FAILED_RESULTS)
    unprotected = AsyncBatchWriteTransaction(client, rollback_on_error=False)
    unprotected.add(TAG, 100)
    with pytest.raises(BatchWriteError) as caught:
        await unprotected.commit()
    assert caught.value.rollback_attempted is False
    assert caught.value.rollback_succeeded is None
    client.read.assert_not_awaited()
    client.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_context_failure_and_user_error() -> None:
    client = MagicMock(spec=AsyncS7Client)
    client.read = AsyncMock(return_value=[10])
    client.write_detailed = AsyncMock(return_value=FAILED_RESULTS)
    client.write = AsyncMock()
    from pyS7 import AsyncBatchWriteTransaction

    with pytest.raises(BatchWriteError):
        async with AsyncBatchWriteTransaction(client) as batch:
            batch.add(TAG, 100)

    client.reset_mock()
    with pytest.raises(RuntimeError, match="user error"):
        async with AsyncBatchWriteTransaction(client) as batch:
            batch.add(TAG, 100)
            raise RuntimeError("user error")
    client.read.assert_not_awaited()
    client.write_detailed.assert_not_awaited()
