from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

nonebot.init()

from pallas.api.runtime import DirectCommandContext  # noqa: E402

from pallas_plugin_tts import direct as direct_mod  # noqa: E402
from pallas_plugin_tts import service as service_mod  # noqa: E402
from pallas_plugin_tts import work_handler as work_handler_mod  # noqa: E402


def make_context(text: str = "牛牛说 你好") -> DirectCommandContext:
    event = GroupMessageEvent.model_construct(
        time=1,
        self_id=1001,
        post_type="message",
        message_type="group",
        sub_type="normal",
        user_id=2002,
        group_id=3003,
        message_id=4004,
        message=Message(text),
        raw_message=text,
        reply=None,
    )
    return DirectCommandContext(
        bot=SimpleNamespace(self_id="1001"),
        event=event,
        bot_id=1001,
        group_id=3003,
        message_id=4004,
        command_text=text,
    )


def tts_config(**overrides):
    values = {
        "tts_enable": True,
        "tts_route": "sidecar",
        "tts_max_chars": 200,
        "tts_endpoint": "/v1/tts",
        "tts_timeout_sec": 30,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_tts_direct_returns_a_durable_job_and_commit_time_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    refresh = AsyncMock()
    monkeypatch.setattr(direct_mod, "get_tts_config", lambda: tts_config())
    monkeypatch.setattr(direct_mod, "is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(direct_mod, "refresh_command_cooldown", refresh)
    monkeypatch.setattr(direct_mod, "ULID", lambda: "request-1")

    result = await direct_mod.speak(make_context())

    assert result.replies == ()
    assert len(result.work_jobs) == 1
    assert result.work_jobs[0].kind == "tts.submit"
    assert result.work_jobs[0].idempotency_key == "tts:1001:3003:4004"
    assert result.work_jobs[0].payload == {
        "request_id": "request-1",
        "bot_id": 1001,
        "group_id": 3003,
        "user_id": 2002,
        "text": "你好",
    }
    refresh.assert_not_awaited()
    await result.effects[0].run()
    refresh.assert_awaited_once_with(make_context().event, "tts.speak")


@pytest.mark.asyncio
async def test_tts_direct_falls_back_for_a_glued_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direct_mod, "get_tts_config", lambda: tts_config())

    result = await direct_mod.speak(make_context("牛牛说你好"))

    assert result.fallback_to_matcher is True
    assert result.fallback_reason == "invalid_command_shape"


@pytest.mark.asyncio
async def test_tts_work_handler_returns_a_failure_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(work_handler_mod, "submit_tts_request", AsyncMock(return_value="语音合成提交失败"))

    result = await work_handler_mod.handle_tts_submit({
        "request_id": "request-1",
        "bot_id": 1001,
        "group_id": 3003,
        "user_id": 2002,
        "text": "你好",
    })

    assert result is not None
    assert result.actions[0].action == "send_group_msg"
    assert result.actions[0].target_bot_id == 1001
    assert result.actions[0].payload == {"group_id": 3003, "message_text": "语音合成提交失败"}


@pytest.mark.asyncio
async def test_submit_tts_request_registers_callback_before_remote_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def add_task(_request_id, _payload):
        calls.append("register")

    async def post(*_args, **_kwargs):
        calls.append("post")
        response = MagicMock()
        response.json.return_value = {"task_id": "remote-1"}
        return response

    monkeypatch.setattr(service_mod, "get_tts_config", lambda: tts_config())
    monkeypatch.setattr(service_mod.TaskManager, "add_task", add_task)
    monkeypatch.setattr(service_mod.TaskManager, "remove_task", AsyncMock())
    monkeypatch.setattr(service_mod.HTTPXClient, "post", post)
    monkeypatch.setattr(service_mod, "tts_server_url", lambda _cfg: "http://media")
    monkeypatch.setattr(service_mod, "tts_auth_headers", lambda _cfg: {})

    error = await service_mod.submit_tts_request({
        "request_id": "request-1",
        "bot_id": 1001,
        "group_id": 3003,
        "user_id": 2002,
        "text": "你好",
    })

    assert error is None
    assert calls == ["register", "post"]
