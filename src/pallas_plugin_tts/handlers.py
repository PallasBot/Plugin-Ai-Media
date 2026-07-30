"""「牛牛说」：侧车 /v1/tts 提交与回调发语音。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from nonebot import logger
from pallas.api.config import TaskManager
from pallas.core.shared.utils import HTTPXClient
from ulid import ULID

from .config import get_tts_config, tts_auth_headers, tts_server_url
from .text import extract_speak_text, is_speak_command_text

if TYPE_CHECKING:
    from pallas.api.commands import PluginHandlerContext

TTS_TASK_TYPE = "tts"

__all__ = ["extract_speak_text", "handle_speak", "is_speak_command_text", "response_task_id"]


def response_task_id(response) -> str:
    try:
        data = response.json() if response is not None else {}
    except Exception as e:
        logger.warning("tts response json parse failed: {}", e)
        return ""
    if not isinstance(data, dict):
        return ""
    raw = data.get("task_id")
    return str(raw).strip() if raw is not None else ""


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
    task_payload = {
        "bot_id": str(ctx.event.self_id),
        "group_id": int(ctx.group_id),
        "user_id": int(ctx.event.user_id),
        "task_type": TTS_TASK_TYPE,
        "start_time": time.time(),
        "voice_only": True,
    }
    await TaskManager.add_task(request_id, task_payload)

    endpoint = (cfg.tts_endpoint or "/v1/tts").strip() or "/v1/tts"
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    url = f"{tts_server_url(cfg)}{endpoint.rstrip('/')}/{request_id}"
    headers = tts_auth_headers(cfg)
    logger.info(
        "tts request dispatch request_id={} bot_id={} group_id={} chars={} url={}",
        request_id,
        ctx.event.self_id,
        ctx.group_id,
        len(text),
        url,
    )
    response = await HTTPXClient.post(
        url,
        json={"text": text},
        headers=headers or None,
        timeout=float(cfg.tts_timeout_sec),
    )
    if not response:
        logger.warning(
            "tts request failed request_id={} bot_id={} group_id={} url={}",
            request_id,
            ctx.event.self_id,
            ctx.group_id,
            url,
        )
        await TaskManager.remove_task(request_id)
        await ctx.finish("语音合成提交失败，稍后再试或检查媒体服务。")
        return

    remote_id = response_task_id(response)
    if not remote_id:
        await TaskManager.remove_task(request_id)
        await ctx.finish("语音合成没有返回任务号，请检查媒体服务日志。")
        return

    await ctx.finish()
