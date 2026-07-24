from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_stub(name: str, module: types.ModuleType) -> None:
    sys.modules[name] = module


def _bootstrap_stub_modules() -> None:
    nonebot = types.ModuleType("nonebot")
    nonebot.logger = types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
    nonebot.on_message = lambda *a, **k: types.SimpleNamespace(handle=lambda: (lambda fn: fn), finish=None)
    _install_stub("nonebot", nonebot)

    adapters = types.ModuleType("nonebot.adapters")
    adapters.Bot = object
    _install_stub("nonebot.adapters", adapters)

    ob11 = types.ModuleType("nonebot.adapters.onebot.v11")
    ob11.GroupMessageEvent = object
    ob11.permission = types.SimpleNamespace(GROUP=object())
    _install_stub("nonebot.adapters.onebot.v11", ob11)

    plugin = types.ModuleType("nonebot.plugin")
    plugin.PluginMetadata = lambda **kwargs: kwargs
    _install_stub("nonebot.plugin", plugin)

    rule = types.ModuleType("nonebot.rule")
    rule.Rule = lambda fn: fn
    _install_stub("nonebot.rule", rule)

    ulid = types.ModuleType("ulid")
    ulid.ULID = lambda: "chat-request-id"
    _install_stub("ulid", ulid)

    metadata_mod = types.ModuleType("pallas.api.metadata")
    metadata_mod.PLUGIN_EXTRA_VERSION = "4.0.1"
    metadata_mod.PLUGIN_HOMEPAGE = "https://example.com"
    metadata_mod.PLUGIN_MENU_TEMPLATE = "default"
    metadata_mod.SCENE_GROUP = "group"
    metadata_mod.join_usage = lambda *lines: "\n".join(lines)
    metadata_mod.usage_line = lambda text, desc: f"{text}: {desc}"
    _install_stub("pallas.api.metadata", metadata_mod)

    class DummyBotConfig:
        @staticmethod
        def handle_sober_up(fn):
            return fn

        def __init__(self, bot_id: str, group_id: int) -> None:
            self.bot_id = bot_id
            self.group_id = group_id

        async def drunkenness(self) -> int:
            return 1

    class DummyGroupConfig:
        def __init__(self, group_id: int, cooldown: int = 10) -> None:
            self.group_id = group_id
            self.cooldown = cooldown

        async def is_cooldown(self, _key: str) -> bool:
            return True

        async def refresh_cooldown(self, _key: str) -> None:
            return None

    config_mod = types.ModuleType("pallas.api.config")
    config_mod.BotConfig = DummyBotConfig
    config_mod.GroupConfig = DummyGroupConfig
    config_mod.TaskManager = types.SimpleNamespace(add_task=None, remove_task=None)
    _install_stub("pallas.api.config", config_mod)

    utils_mod = types.ModuleType("pallas.core.shared.utils")
    utils_mod.HTTPXClient = types.SimpleNamespace(delete=None, post=None)
    _install_stub("pallas.core.shared.utils", utils_mod)

    llm_models = types.ModuleType("pallas.product.llm.models")

    class ChatSubmitRequest:
        def __init__(self, **kwargs) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    llm_models.ChatSubmitRequest = ChatSubmitRequest
    _install_stub("pallas.product.llm.models", llm_models)

    llm_product = types.ModuleType("pallas.product.llm")
    llm_product.ChatSubmitRequest = ChatSubmitRequest
    llm_product.submit_chat_task = None

    async def fake_build_drunk_chat_system_prompt(*_a, **_k):
        return types.SimpleNamespace(system_prompt="你是牛牛。", token_count=50, temperature=None)

    llm_product.build_drunk_chat_system_prompt = fake_build_drunk_chat_system_prompt
    llm_product.is_legacy_rwkv_drunk_chat_enabled = lambda: False
    llm_product.is_llm_chat_service_enabled = lambda: True
    _install_stub("pallas.product.llm", llm_product)

    legacy_rwkv = types.ModuleType("pallas.product.llm.legacy_rwkv")
    legacy_rwkv.submit_rwkv_drunk_chat = None
    _install_stub("pallas.product.llm.legacy_rwkv", legacy_rwkv)

    knowledge_declare = types.ModuleType("pallas.product.llm.knowledge.declare")
    knowledge_declare.knowledge_source_row = lambda **kwargs: kwargs
    _install_stub("pallas.product.llm.knowledge", types.ModuleType("pallas.product.llm.knowledge"))
    _install_stub("pallas.product.llm.knowledge.declare", knowledge_declare)

    chat_config = types.ModuleType("pallas_plugin_chat.config")
    chat_config.Config = object
    chat_config.get_chat_config = lambda: types.SimpleNamespace(ai_server_host="127.0.0.1", ai_server_port=9099)
    chat_config.plugin_config = types.SimpleNamespace(
        chat_enable=True,
        chat_endpoint="/api/chat",
        del_session_endpoint="/api/del_session",
        tts_enable=False,
    )
    _install_stub("pallas_plugin_chat.config", chat_config)


_bootstrap_stub_modules()

chat_mod = importlib.import_module("pallas_plugin_chat")  # noqa: E402


class DummyBot:
    self_id = "123456"


class DummyEvent:
    self_id = "123456"
    group_id = 42
    user_id = 10001

    def is_tome(self) -> bool:
        return False

    def get_plaintext(self) -> str:
        return "牛牛 你好呀\n第二行忽略"


@pytest.mark.asyncio
async def test_drunk_chat_uses_unified_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    added: list[tuple[str, dict]] = []
    removed: list[str] = []
    captured: dict[str, object] = {}
    http_calls: list[tuple[str, dict]] = []

    async def fake_add_task(task_id: str, payload: dict) -> None:
        added.append((task_id, dict(payload)))

    async def fake_remove_task(task_id: str) -> None:
        removed.append(task_id)

    async def fake_submit_chat_task(request, *, cfg=None):
        captured["request_id"] = request.request_id
        captured["session_id"] = request.session_id
        captured["user_text"] = request.user_text
        captured["system_prompt"] = request.system_prompt
        captured["bot_id"] = request.bot_id
        captured["group_id"] = request.group_id
        captured["mode"] = request.mode
        captured["task"] = request.task
        captured["token_count"] = request.token_count
        captured["cfg"] = cfg
        return types.SimpleNamespace(ok=True, task_id="unified-task-id", status="processing")

    async def fake_post(url: str, json: dict | None = None):
        http_calls.append((url, dict(json or {})))
        raise AssertionError("legacy HTTP chat path should not be used")

    monkeypatch.setattr(chat_mod.TaskManager, "add_task", fake_add_task)
    monkeypatch.setattr(chat_mod.TaskManager, "remove_task", fake_remove_task)
    monkeypatch.setattr(chat_mod, "submit_chat_task", fake_submit_chat_task)
    monkeypatch.setattr(chat_mod.HTTPXClient, "post", fake_post)

    handler = getattr(chat_mod, "_")
    await handler(DummyBot(), DummyEvent())

    assert removed == []
    assert http_calls == []
    assert [task_id for task_id, _ in added] == ["chat-request-id"]
    assert added[0][1]["task_type"] == "chat"
    assert captured["request_id"] == "chat-request-id"
    assert captured["session_id"] == "123456_42"
    assert captured["user_text"] == "你好呀"
    assert captured["system_prompt"] == "你是牛牛。"
    assert captured["bot_id"] == 123456
    assert captured["group_id"] == 42
    assert captured["mode"] == "drunk"
    assert captured["task"] == "drunk"
    assert captured["token_count"] == 50
