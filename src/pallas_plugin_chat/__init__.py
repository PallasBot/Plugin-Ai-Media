import time

from nonebot import logger, on_message
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, permission
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from ulid import ULID

from pallas.api.metadata import (
    PLUGIN_EXTRA_VERSION,
    PLUGIN_HOMEPAGE,
    PLUGIN_MENU_TEMPLATE,
    SCENE_GROUP,
    join_usage,
    usage_line,
)
from pallas.api.config import BotConfig, GroupConfig, TaskManager
from pallas.core.shared.utils import HTTPXClient
from pallas.product.llm import (
    ChatSubmitRequest,
    build_drunk_chat_system_prompt,
    is_legacy_rwkv_drunk_chat_enabled,
    is_llm_chat_service_enabled,
    submit_chat_task,
)
from pallas.product.llm.legacy_rwkv import submit_rwkv_drunk_chat
from pallas.product.llm.knowledge.declare import knowledge_source_row

from .config import Config, get_chat_config, plugin_config

__plugin_meta__ = PluginMetadata(
    name="酒后聊天",
    description="牛牛醉酒时在群内进行 AI 对话。",
    usage=join_usage(
        usage_line("@牛牛", "醉酒时和牛牛聊天"),
        usage_line("牛牛 + 文本", "醉酒时直接和牛牛搭话"),
    ),
    type="application",
    homepage=PLUGIN_HOMEPAGE,
    supported_adapters={"~onebot.v11"},
    extra={
        "version": PLUGIN_EXTRA_VERSION,
        "menu_template": PLUGIN_MENU_TEMPLATE,
        "ingress_route": {"lane": "remote"},
        "menu_data": [
            {
                "func": "酒后聊天",
                "trigger_method": "on_message",
                "trigger_scene": SCENE_GROUP,
                "trigger_condition": "@牛牛 / 牛牛 + 文本",
                "brief_des": "醉酒时 AI 对话",
                "detail_des": "要先让牛牛喝酒；它会结合当前上下文接话，开启 TTS 时还可能附带语音。",
            },
        ],
        "knowledge_sources": [
            knowledge_source_row(
                source_id="chat.faq",
                title="酒后聊天说明",
                description="醉酒时的 AI 对话",
                chunks=[
                    {
                        "title": "如何触发",
                        "content": (
                            "牛牛须先处于醉酒状态（可先发送「牛牛喝酒」）；"
                            "然后在群内 @牛牛 发消息，或以「牛牛 + 文本」搭话。"
                        ),
                        "keywords": "酒后,聊天,醉酒,@牛牛,怎么聊",
                    },
                    {
                        "title": "与随时闲聊的分工",
                        "content": (
                            "未醉酒时用 @牛牛 走的是本体「智能对话」插件；"
                            "醉酒后才走酒后聊天，两者不要混为一谈。"
                        ),
                        "keywords": "闲聊,智能对话,醉酒,区别,分工",
                    },
                    {
                        "title": "如何结束",
                        "content": "发送「牛牛醒一醒」或「牛牛别喝了」可醒酒并结束酒后会话。",
                        "keywords": "醒酒,醒一醒,别喝了,结束",
                    },
                ],
            ),
        ],
    },
)


def refresh_server_url(cfg: Config | None = None) -> None:
    global SERVER_URL
    c = cfg or get_chat_config()
    SERVER_URL = f"http://{c.ai_server_host}:{c.ai_server_port}"


refresh_server_url()
CHAT_COOLDOWN_KEY = "chat"

if plugin_config.chat_enable:

    @BotConfig.handle_sober_up
    async def on_sober_up(bot_id, group_id, drunkenness) -> None:
        session = f"{bot_id}_{group_id}"
        logger.info(
            f"bot [{bot_id}] sober up in group [{group_id}], clear session [{session}]"
        )
        url = f"{SERVER_URL}{plugin_config.del_session_endpoint}/{session}"
        await HTTPXClient.delete(url)


async def is_to_chat(event: GroupMessageEvent) -> bool:
    if plugin_config.chat_enable is False:
        return False
    text = event.get_plaintext()
    if not text.startswith("牛牛") and not event.is_tome():
        return False
    config = BotConfig(event.self_id, event.group_id)
    drunkness = await config.drunkenness()
    return drunkness > 0


drunk_msg = on_message(
    rule=Rule(is_to_chat),
    priority=13,
    block=True,
    permission=permission.GROUP,
)


@drunk_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    config = GroupConfig(event.group_id, cooldown=10)
    if not await config.is_cooldown(CHAT_COOLDOWN_KEY):
        return
    await config.refresh_cooldown(CHAT_COOLDOWN_KEY)

    text = event.get_plaintext()
    if text.startswith("牛牛"):
        text = text[2:].strip()
    if "\n" in text:
        text = text.split("\n")[0]
    text = text[:50].strip()
    if not text:
        return

    session = f"{bot.self_id}_{event.group_id}"
    request_id = str(ULID())
    await TaskManager.add_task(
        request_id,
        {
            "bot_id": bot.self_id,
            "group_id": event.group_id,
            "user_id": event.user_id,
            "task_type": "chat",
            "start_time": time.time(),
        },
    )

    if is_llm_chat_service_enabled():
        prompt_ctx = await build_drunk_chat_system_prompt(
            int(bot.self_id),
            int(event.group_id),
            text,
            user_id=int(event.user_id),
        )
        if prompt_ctx is None:
            await TaskManager.remove_task(request_id)
            logger.warning(
                "drunk chat system prompt empty: bot={} group={}",
                bot.self_id,
                event.group_id,
            )
            return
        result = await submit_chat_task(
            ChatSubmitRequest(
                request_id=request_id,
                session_id=session,
                user_text=text,
                system_prompt=prompt_ctx.system_prompt,
                bot_id=int(bot.self_id),
                group_id=int(event.group_id),
                user_id=int(event.user_id),
                mode="drunk",
                task="drunk",
                token_count=prompt_ctx.token_count or 50,
                temperature=prompt_ctx.temperature,
            )
        )
    elif is_legacy_rwkv_drunk_chat_enabled():
        task_id, ok = await submit_rwkv_drunk_chat(
            request_id=request_id,
            session=session,
            text=text,
            tts=False,
            chat_endpoint=plugin_config.chat_endpoint,
        )
        result = type("LegacyResult", (), {"ok": ok, "task_id": task_id})()
    else:
        await TaskManager.remove_task(request_id)
        return
    if not result or not getattr(result, "ok", False):
        await TaskManager.remove_task(request_id)
        return
    task_id = str(getattr(result, "task_id", "") or "")
    if not task_id:
        await TaskManager.remove_task(request_id)
        return
