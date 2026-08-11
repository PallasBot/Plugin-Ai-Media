from __future__ import annotations

import time

from nonebot import logger
from pallas.api.config import TaskManager
from pallas.api.logging import format_plugin_event
from pallas.core.shared.utils import HTTPXClient

from .config import get_tts_config, tts_auth_headers, tts_server_url

TTS_TASK_TYPE = "tts"


def response_task_id(response) -> str:
    try:
        data = response.json() if response is not None else {}
    except Exception as exc:
        logger.warning("tts response json parse failed: {}", exc)
        return ""
    if not isinstance(data, dict):
        return ""
    raw = data.get("task_id")
    return str(raw).strip() if raw is not None else ""


async def submit_tts_request(payload: dict) -> str | None:
    request_id = str(payload.get("request_id") or "").strip()
    bot_id = int(payload["bot_id"])
    group_id = int(payload["group_id"])
    user_id = int(payload["user_id"])
    text = str(payload.get("text") or "").strip()
    if not request_id or not text:
        raise ValueError("tts request_id and text are required")

    cfg = get_tts_config()
    task_payload = {
        "bot_id": str(bot_id),
        "group_id": group_id,
        "user_id": user_id,
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
        bot_id,
        group_id,
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
            bot_id,
            group_id,
            url,
        )
        await TaskManager.remove_task(request_id)
        return "语音合成提交失败，稍后再试或检查媒体服务。"
    if not response_task_id(response):
        await TaskManager.remove_task(request_id)
        return "语音合成没有返回任务号，请检查媒体服务日志。"
    logger.info(
        format_plugin_event(
            "tts",
            f"Bot [{bot_id}] queued speech synthesis for user [{user_id}] in group [{group_id}] (chars={len(text)})",
        )
    )
    return None
