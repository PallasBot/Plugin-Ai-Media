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
async def test_sing_direct_defers_submission_and_cooldown_until_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    context = make_context("牛牛唱歌 青花瓷 key=2")
    submit = AsyncMock(return_value="欢呼吧！")
    refresh = AsyncMock()
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())
    monkeypatch.setattr(direct_mod, "is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(direct_mod, "refresh_command_cooldown", refresh)
    monkeypatch.setattr(direct_mod, "submit_sing", submit)

    result = await direct_mod.sing(context)

    assert result.fallback_to_matcher is False
    assert result.replies == ()
    assert len(result.effects) == 1
    submit.assert_not_awaited()
    refresh.assert_not_awaited()

    await result.effects[0].run()

    refresh.assert_awaited_once_with(context.event, "sing.sing")
    submit.assert_awaited_once()
    request = submit.await_args.args[0]
    assert request.bot_id == 1001
    assert request.group_id == 3003
    assert request.user_id == 2002
    assert request.speaker == "pallas"
    assert request.song_query == "青花瓷"
    assert request.key == "2"
    context.bot.send.assert_awaited_once_with(context.event, "欢呼吧！")


@pytest.mark.asyncio
async def test_sing_direct_falls_back_for_bare_play_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())

    result = await direct_mod.sing(make_context("牛牛唱歌"))

    assert result.fallback_to_matcher is True
    assert result.fallback_reason == "play_command"


@pytest.mark.asyncio
async def test_request_song_direct_uses_its_own_permission_and_deferred_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context("牛牛点歌 青花瓷")
    submit = AsyncMock(return_value="欢呼吧！")
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())
    monkeypatch.setattr(direct_mod, "is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(direct_mod, "refresh_command_cooldown", AsyncMock())
    monkeypatch.setattr(direct_mod, "submit_request_song", submit)

    result = await direct_mod.request_song(context)
    await result.effects[0].run()

    submit.assert_awaited_once()
    request = submit.await_args.args[0]
    assert request.song_name == "青花瓷"
    assert direct_mod.SING_DECLARATION.command_id == "sing.sing"
    assert direct_mod.REQUEST_SONG_DECLARATION.command_id == "sing.request_song"
    assert all(prefix.endswith(("唱歌", "继续唱", "接着唱")) for prefix in direct_mod.SING_DECLARATION.prefixes)
    assert all(prefix.endswith("点歌") for prefix in direct_mod.REQUEST_SONG_DECLARATION.prefixes)


@pytest.mark.asyncio
async def test_sing_direct_continue_uses_next_persisted_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    context = make_context("牛牛继续唱")
    submit = AsyncMock(return_value="欢呼吧！")
    group_config = SimpleNamespace(
        sing_progress=AsyncMock(return_value=SimpleNamespace(song_id="1474697449", chunk_index=2, key=-1))
    )
    monkeypatch.setattr(direct_mod, "get_sing_config", lambda: sing_config())
    monkeypatch.setattr(direct_mod, "GroupConfig", lambda _group_id: group_config)
    monkeypatch.setattr(direct_mod, "is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(direct_mod, "refresh_command_cooldown", AsyncMock())
    monkeypatch.setattr(direct_mod, "submit_sing", submit)

    result = await direct_mod.sing(context)
    await result.effects[0].run()

    request = submit.await_args.args[0]
    assert request.song_query == "1474697449"
    assert request.chunk_index == 3
    assert request.key == -1


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
