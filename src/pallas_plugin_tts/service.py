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


def response_status_code(response) -> int | None:
    try:
        code = getattr(response, "status_code", None)
        return int(code) if code is not None else None
    except Exception:
        return None


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
        format_plugin_event(
            "tts",
            f"Bot [{bot_id}] received a tts request in group [{group_id}] from user [{user_id}], {len(text)} chars",
        )
    )
    logger.info(
        format_plugin_event(
            "tts",
            f"Bot [{bot_id}] dispatched a tts request [{request_id}] in group [{group_id}] "
            f"from user [{user_id}], {len(text)} chars",
        )
    )
    response = await HTTPXClient.post(
        url,
        json={"text": text},
        headers=headers or None,
        timeout=float(cfg.tts_timeout_sec),
    )
    if not response:
        logger.warning(
            "Bot [{}] tts request [{}] to [{}] failed in group [{}]",
            bot_id,
            request_id,
            url,
            group_id,
        )
        await TaskManager.remove_task(request_id)
        return "语音合成提交失败，稍后再试或检查媒体服务。"
    remote_task_id = response_task_id(response)
    if not remote_task_id:
        await TaskManager.remove_task(request_id)
        return "语音合成没有返回任务号，请检查媒体服务日志。"
    task_part = f", task [{remote_task_id}]" if remote_task_id != request_id else ""
    logger.info(
        format_plugin_event(
            "tts",
            f"Bot [{bot_id}] tts request [{request_id}] accepted{task_part}, "
            f"status [{response_status_code(response) or '-'}]",
        )
    )
    logger.info(
        format_plugin_event(
            "tts",
            f"Bot [{bot_id}] queued speech synthesis [{len(text)} chars] for user [{user_id}] in group [{group_id}]",
        )
    )
    return None
