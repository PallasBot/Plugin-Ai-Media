from __future__ import annotations

from pallas.api.limits import is_command_cooldown_ready, refresh_command_cooldown
from pallas.api.runtime import (
    DirectCommandContext,
    DirectCommandResult,
    DirectWorkJob,
    completion_effect,
    matcher_fallback,
    register_prefix_command_handler,
    reply,
)
from ulid import ULID

from .config import get_tts_config
from .text import extract_speak_text, is_speak_command_text

TTS_COMMAND_ID = "tts.speak"
TTS_PREFIX = "牛牛说"


async def speak(context: DirectCommandContext) -> DirectCommandResult:
    cfg = get_tts_config()
    if not cfg.tts_enable:
        return reply("语音合成未启用，请在插件「牛牛说」配置页打开开关。")

    route = (cfg.tts_route or "sidecar").strip().lower()
    if route == "cloud":
        return reply("云端语音通路尚未接入，请将「语音通路」改为侧车后再试。")
    if route != "sidecar":
        return reply("未知的语音通路配置，请改为侧车。")

    raw = context.command_text.strip()
    if not is_speak_command_text(raw):
        return matcher_fallback("invalid_command_shape")
    text = extract_speak_text(raw)
    if not text:
        return reply("用法：牛牛说 〈要念的内容〉（「牛牛说」后请加空格）")
    max_chars = int(cfg.tts_max_chars)
    if len(text) > max_chars:
        return reply(f"太长了，请控制在 {max_chars} 字以内。")
    if not await is_command_cooldown_ready(context.event, TTS_COMMAND_ID):
        return matcher_fallback("cooldown")

    request_id = str(ULID())
    job = DirectWorkJob(
        kind="tts.submit",
        payload={
            "request_id": request_id,
            "bot_id": context.bot_id,
            "group_id": context.group_id,
            "user_id": int(context.event.user_id),
            "text": text,
        },
        idempotency_key=f"tts:{context.bot_id}:{context.group_id}:{context.message_id}",
    )

    async def refresh_cooldown() -> None:
        await refresh_command_cooldown(context.event, TTS_COMMAND_ID)

    return DirectCommandResult(
        work_jobs=(job,),
        effects=(completion_effect("tts.speak.cooldown", refresh_cooldown),),
    )


SPEAK_DECLARATION = register_prefix_command_handler(
    handler_id="tts.speak.direct",
    module="tts",
    prefixes=(TTS_PREFIX,),
    command_id=TTS_COMMAND_ID,
    execute=speak,
)
