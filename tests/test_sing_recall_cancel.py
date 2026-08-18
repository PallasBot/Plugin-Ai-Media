from __future__ import annotations

import time
from unittest.mock import AsyncMock

import nonebot
import pytest

nonebot.init(driver="nonebot.drivers.none:Driver")

from pallas_plugin_sing import submission as submission_mod  # noqa: E402


@pytest.fixture(autouse=True)
def clean_message_task_index() -> None:
    submission_mod._message_task_index.clear()
    yield
    submission_mod._message_task_index.clear()


def test_remember_and_pending_task_for_message() -> None:
    submission_mod.remember_message_task(3003, 4004, "request-1")
    assert submission_mod.pending_task_for_message(3003, 4004) == "request-1"
    assert submission_mod.pending_task_for_message(3003, 9999) is None
    assert submission_mod.pending_task_for_message(1111, 4004) is None


def test_pending_task_expires_after_ttl() -> None:
    submission_mod.remember_message_task(3003, 4004, "request-1")
    key = (3003, 4004)
    submission_mod._message_task_index[key] = (
        "request-1",
        time.time() - submission_mod._message_task_ttl_sec - 1,
    )
    assert submission_mod.pending_task_for_message(3003, 4004) is None
    assert key not in submission_mod._message_task_index


def test_forget_message_task_removes_entry() -> None:
    submission_mod.remember_message_task(3003, 4004, "request-1")
    submission_mod.forget_message_task(3003, 4004)
    assert submission_mod.pending_task_for_message(3003, 4004) is None


@pytest.mark.asyncio
async def test_cancel_pending_task_removes_task(monkeypatch: pytest.MonkeyPatch) -> None:
    remove_task = AsyncMock()
    monkeypatch.setattr(submission_mod.TaskManager, "get_task", AsyncMock(return_value={"task_type": "sing"}))
    monkeypatch.setattr(submission_mod.TaskManager, "remove_task", remove_task)
    submission_mod.remember_message_task(3003, 4004, "request-1")

    cancelled = await submission_mod.cancel_pending_task_for_message(3003, 4004)

    assert cancelled is True
    remove_task.assert_awaited_once_with("request-1")
    assert submission_mod.pending_task_for_message(3003, 4004) is None


@pytest.mark.asyncio
async def test_cancel_pending_task_noop_without_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    remove_task = AsyncMock()
    monkeypatch.setattr(submission_mod.TaskManager, "remove_task", remove_task)

    cancelled = await submission_mod.cancel_pending_task_for_message(3003, 9999)

    assert cancelled is False
    remove_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_pending_task_skips_already_consumed_task(monkeypatch: pytest.MonkeyPatch) -> None:
    remove_task = AsyncMock()
    monkeypatch.setattr(submission_mod.TaskManager, "get_task", AsyncMock(return_value=None))
    monkeypatch.setattr(submission_mod.TaskManager, "remove_task", remove_task)
    submission_mod.remember_message_task(3003, 4004, "request-1")

    cancelled = await submission_mod.cancel_pending_task_for_message(3003, 4004)

    assert cancelled is False
    remove_task.assert_not_awaited()
    assert submission_mod.pending_task_for_message(3003, 4004) is None


@pytest.mark.asyncio
async def test_cancel_pending_task_failure_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_remove(_task_id: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(submission_mod.TaskManager, "get_task", AsyncMock(return_value={"task_type": "sing"}))
    monkeypatch.setattr(submission_mod.TaskManager, "remove_task", fail_remove)
    submission_mod.remember_message_task(3003, 4004, "request-1")

    cancelled = await submission_mod.cancel_pending_task_for_message(3003, 4004)

    assert cancelled is False
