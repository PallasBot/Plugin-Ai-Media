from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

pallas_runtime = pytest.importorskip("pallas.api.runtime")

nonebot.init(driver="nonebot.drivers.none:Driver")

DirectCommandContext = pallas_runtime.DirectCommandContext

from pallas_plugin_sing import direct as direct_mod  # noqa: E402
from pallas_plugin_sing import submission as submission_mod  # noqa: E402
from pallas_plugin_sing import work_handler as work_handler_mod  # noqa: E402


def make_context(text: str) -> DirectCommandContext:
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
    bot = SimpleNamespace(self_id="1001", send=AsyncMock())
    return DirectCommandContext(
        bot=bot,
        event=event,
        bot_id=1001,
        group_id=3003,
        message_id=4004,
        command_text=text,
    )


def sing_config(**overrides):
    values = {
        "sing_enable": True,
        "sing_speakers": {"牛牛": "pallas", "帕拉斯": "pallas"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_sing_direct_returns_durable_submission_job_and_commit_time_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    context = make_context("牛牛唱歌 青花瓷 key=2")
    refresh = AsyncMock()
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())
    monkeypatch.setattr(direct_mod, "is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(direct_mod, "refresh_command_cooldown", refresh)
    monkeypatch.setattr(direct_mod, "ULID", lambda: "request-1")

    result = await direct_mod.sing(context)

    assert result.fallback_to_matcher is False
    assert result.replies == ()
    assert len(result.work_jobs) == 1
    assert result.work_jobs[0].kind == "sing.submit"
    assert result.work_jobs[0].idempotency_key == "sing:1001:3003:4004"
    assert result.work_jobs[0].payload == {
        "request_id": "request-1",
        "bot_id": 1001,
        "group_id": 3003,
        "user_id": 2002,
        "speaker": "pallas",
        "song_query": "青花瓷",
        "key": "2",
        "chunk_index": 0,
    }
    refresh.assert_not_awaited()

    await result.effects[0].run()

    refresh.assert_awaited_once_with(context.event, "sing.sing")


@pytest.mark.asyncio
async def test_sing_direct_falls_back_for_bare_play_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())

    result = await direct_mod.sing(make_context("牛牛唱歌"))

    assert result.fallback_to_matcher is True
    assert result.fallback_reason == "play_command"


@pytest.mark.asyncio
async def test_request_song_direct_returns_durable_submission_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context("牛牛点歌 青花瓷")
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())
    monkeypatch.setattr(direct_mod, "is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(direct_mod, "refresh_command_cooldown", AsyncMock())
    monkeypatch.setattr(direct_mod, "ULID", lambda: "request-1")

    result = await direct_mod.request_song(context)

    assert len(result.work_jobs) == 1
    assert result.work_jobs[0].kind == "sing.request_song"
    assert result.work_jobs[0].idempotency_key == "sing.request_song:1001:3003:4004"
    assert result.work_jobs[0].payload == {
        "request_id": "request-1",
        "bot_id": 1001,
        "group_id": 3003,
        "user_id": 2002,
        "song_name": "青花瓷",
    }
    assert direct_mod.SING_DECLARATION.command_id == "sing.sing"
    assert direct_mod.REQUEST_SONG_DECLARATION.command_id == "sing.request_song"
    assert all(prefix.endswith(("唱歌", "继续唱", "接着唱")) for prefix in direct_mod.SING_DECLARATION.prefixes)
    assert all(prefix.endswith("点歌") for prefix in direct_mod.REQUEST_SONG_DECLARATION.prefixes)


@pytest.mark.asyncio
async def test_sing_direct_continue_uses_next_persisted_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    context = make_context("牛牛继续唱")
    group_config = SimpleNamespace(
        sing_progress=AsyncMock(return_value=SimpleNamespace(song_id="1474697449", chunk_index=2, key=-1))
    )
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())
    monkeypatch.setattr(direct_mod, "GroupConfig", lambda _group_id: group_config)
    monkeypatch.setattr(direct_mod, "is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(direct_mod, "refresh_command_cooldown", AsyncMock())
    monkeypatch.setattr(direct_mod, "ULID", lambda: "request-1")

    result = await direct_mod.sing(context)

    assert result.work_jobs[0].payload["song_query"] == "1474697449"
    assert result.work_jobs[0].payload["chunk_index"] == 3
    assert result.work_jobs[0].payload["key"] == -1


@pytest.mark.asyncio
async def test_sing_work_handler_returns_submission_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(work_handler_mod, "submit_sing", AsyncMock(return_value="欢呼吧！"))

    result = await work_handler_mod.handle_sing_submit({
        "request_id": "request-1",
        "bot_id": 1001,
        "group_id": 3003,
        "user_id": 2002,
        "speaker": "pallas",
        "song_query": "青花瓷",
        "key": 0,
        "chunk_index": 0,
    })

    assert result is not None
    assert result.actions[0].action == "send_group_msg"
    assert result.actions[0].target_bot_id == 1001
    assert result.actions[0].payload == {"group_id": 3003, "message_text": "欢呼吧！"}
    request = work_handler_mod.submit_sing.await_args.args[0]
    assert request.request_id == "request-1"


@pytest.mark.asyncio
async def test_request_song_work_handler_skips_empty_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(work_handler_mod, "submit_request_song", AsyncMock(return_value=None))

    result = await work_handler_mod.handle_request_song({
        "request_id": "request-1",
        "bot_id": 1001,
        "group_id": 3003,
        "user_id": 2002,
        "song_name": "青花瓷",
    })

    assert result is None


@pytest.mark.asyncio
async def test_submit_play_generates_request_id_for_legacy_random_play(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.json.return_value = {"task_id": "remote-1"}
    monkeypatch.setattr(submission_mod, "get_sing_config", lambda: sing_config(
        play_endpoint="/api/play",
        ai_server_host="127.0.0.1",
        ai_server_port=9099,
    ))
    monkeypatch.setattr(submission_mod, "sing_server_url", lambda _config: "http://media")
    monkeypatch.setattr(submission_mod, "ULID", lambda: "request-1")
    monkeypatch.setattr(submission_mod.TaskManager, "add_task", AsyncMock())
    monkeypatch.setattr(submission_mod.TaskManager, "remove_task", AsyncMock())
    monkeypatch.setattr(submission_mod.HTTPXClient, "post", AsyncMock(return_value=response))

    message = await submission_mod.submit_play(submission_mod.PlaySubmission(1001, 3003, 2002, "pallas"))

    assert message == submission_mod.ACCEPTED_REPLY
    submission_mod.HTTPXClient.post.assert_awaited_once()
    assert submission_mod.HTTPXClient.post.await_args.kwargs["json"] == {"speaker": "pallas"}


@pytest.mark.asyncio
async def test_submit_sing_registers_before_post_and_cleans_up_missing_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    remove_task = AsyncMock()
    response = MagicMock()
    response.json.return_value = {}

    async def add_task(_task_id: str, _payload: dict) -> None:
        calls.append("register")

    async def post(*_args, **_kwargs):
        calls.append("post")
        return response

    config = sing_config(
        sing_endpoint="/api/sing",
        sing_length=120,
        ai_server_host="127.0.0.1",
        ai_server_port=9099,
    )
    monkeypatch.setattr(submission_mod, "get_sing_config", lambda: config)
    monkeypatch.setattr(submission_mod, "get_song_id", AsyncMock(return_value=1474697449))
    monkeypatch.setattr(submission_mod, "sing_server_url", lambda _config: "http://media")
    monkeypatch.setattr(submission_mod, "ULID", lambda: "request-1")
    monkeypatch.setattr(submission_mod.TaskManager, "add_task", add_task)
    monkeypatch.setattr(submission_mod.TaskManager, "remove_task", remove_task)
    monkeypatch.setattr(submission_mod.HTTPXClient, "post", post)

    message = await submission_mod.submit_sing(
        submission_mod.SingSubmission(
            bot_id=1001,
            group_id=3003,
            user_id=2002,
            speaker="pallas",
            song_query="青花瓷",
            key="2",
        )
    )

    assert calls == ["register", "post"]
    assert message == submission_mod.FAILED_REPLY
    remove_task.assert_awaited_once_with("request-1")
