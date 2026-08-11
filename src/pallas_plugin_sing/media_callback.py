"""sing 媒体任务 AI callback 收尾。"""

from __future__ import annotations

from typing import Any

from nonebot import logger
from pallas.api.logging import format_plugin_event
from pallas.api.platform import SING_TASK_TYPES, register_media_task_hooks


def on_sing_task_success(task: dict[str, Any], _audio_bytes: bytes, group_id: int) -> None:
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{task.get('bot_id') or '-'}] delivered a song for user [{task.get('user_id') or '-'}] "
            f"in group [{group_id}]",
        )
    )


for _task_type in SING_TASK_TYPES:
    register_media_task_hooks(_task_type, on_success=on_sing_task_success)
