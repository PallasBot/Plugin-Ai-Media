"""「牛牛说」：侧车 /v1/tts 提交与回调发语音。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ulid import ULID

from .config import get_tts_config
from .service import response_task_id, submit_tts_request
from .text import extract_speak_text, is_speak_command_text

if TYPE_CHECKING:
    from pallas.api.commands import PluginHandlerContext

__all__ = ["extract_speak_text", "handle_speak", "is_speak_command_text", "response_task_id"]


async def handle_speak(ctx: PluginHandlerContext) -> None:
    cfg = get_tts_config()
    if not cfg.tts_enable:
        await ctx.finish("语音合成未启用，请在插件「牛牛说」配置页打开开关。")
        return

    route = (cfg.tts_route or "sidecar").strip().lower()
    if route == "cloud":
        await ctx.finish("云端语音通路尚未接入，请将「语音通路」改为侧车后再试。")
        return
    if route != "sidecar":
        await ctx.finish("未知的语音通路配置，请改为侧车。")
        return

    if not ctx.is_group or ctx.group_id is None:
        await ctx.finish("请在群里使用「牛牛说」。")
        return

    raw = (ctx.plain_text or "").strip()
    # 粘连误触发（如「牛牛说啥呢」）：前缀后无空白 → 交回其它 matcher
    if raw.startswith("牛牛说") and not is_speak_command_text(raw):
        await ctx.matcher.skip()
        return

    text = extract_speak_text(raw) if raw.startswith("牛牛说") else raw
    if not text:
        await ctx.finish("用法：牛牛说 〈要念的内容〉（「牛牛说」后请加空格）")
        return
    max_chars = int(cfg.tts_max_chars)
    if len(text) > max_chars:
        await ctx.finish(f"太长了，请控制在 {max_chars} 字以内。")
        return

    request_id = str(ULID())
    error = await submit_tts_request({
        "request_id": request_id,
        "bot_id": int(ctx.event.self_id),
        "group_id": int(ctx.group_id),
        "user_id": int(ctx.event.user_id),
        "text": text,
    })
    if error:
        await ctx.finish(error)
        return

    await ctx.finish()
