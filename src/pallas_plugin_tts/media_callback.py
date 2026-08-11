"""tts 媒体任务 AI callback 收尾。"""

from __future__ import annotations

from typing import Any

from nonebot import logger
from pallas.api.logging import format_plugin_event
from pallas.api.platform import TTS_TASK_TYPE, register_media_task_hooks


def on_tts_task_success(task: dict[str, Any], _audio_bytes: bytes, group_id: int) -> None:
    logger.info(
        format_plugin_event(
            "tts_callback",
            f"Bot [{task.get('bot_id') or '-'}] delivered speech synthesis for user [{task.get('user_id') or '-'}] "
            f"in group [{group_id}]",
        )
    )


register_media_task_hooks(TTS_TASK_TYPE, on_success=on_tts_task_success)
