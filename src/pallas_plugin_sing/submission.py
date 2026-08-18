from __future__ import annotations

import time
from dataclasses import dataclass

from nonebot import logger
from pallas.api.config import GroupConfig, SingProgress, TaskManager
from pallas.api.logging import format_plugin_event
from pallas.api.utils import HTTPXClient
from ulid import ULID

from .config import get_sing_config, sing_server_url
from .ncm_login import get_song_id

ACCEPTED_REPLY = "欢呼吧！"
FAILED_REPLY = "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。"

# 记录消息 → 已提交任务，供撤回时取消未开始的投递（仅在任务尚未被 AI 回调消费时有效）
# 键为 (group_id, message_id)，避免跨群消息号复用导致误取消
_message_task_index: dict[tuple[int, int], tuple[str, float]] = {}
_message_task_ttl_sec = 3600.0


def remember_message_task(group_id: int, message_id: int, request_id: str) -> None:
    if not message_id:
        return
    _prune_message_task_index()
    _message_task_index[(group_id, message_id)] = (request_id, time.time())


def forget_message_task(group_id: int, message_id: int) -> None:
    if message_id:
        _message_task_index.pop((group_id, message_id), None)


def pending_task_for_message(group_id: int, message_id: int) -> str | None:
    if not message_id:
        return None
    entry = _message_task_index.get((group_id, message_id))
    if entry is None:
        return None
    request_id, submitted_at = entry
    if time.time() - submitted_at > _message_task_ttl_sec:
        _message_task_index.pop((group_id, message_id), None)
        return None
    return request_id


def _prune_message_task_index() -> None:
    now = time.time()
    stale = [key for key, (_rid, ts) in _message_task_index.items() if now - ts > _message_task_ttl_sec]
    for key in stale:
        _message_task_index.pop(key, None)


async def cancel_pending_task_for_message(group_id: int, message_id: int) -> bool:
    """撤回点歌/唱歌消息时调用：若对应任务尚未被 AI 回调消费则移除，避免撤回后仍投递歌曲。"""
    request_id = pending_task_for_message(group_id, message_id)
    if not request_id:
        return False
    try:
        task = await TaskManager.get_task(request_id)
    except Exception as exc:
        logger.warning(
            f"Looking up pending sing task [{request_id}] for recalled message [{message_id}] in group [{group_id}] "
            f"failed: {exc}"
        )
        return False
    if task is None:
        forget_message_task(group_id, message_id)
        return False
    forget_message_task(group_id, message_id)
    try:
        await TaskManager.remove_task(request_id)
    except Exception as exc:
        logger.warning(
            f"Cancelling pending sing task [{request_id}] for recalled message [{message_id}] "
            f"in group [{group_id}] failed: {exc}"
        )
        return False
    logger.info(
        format_plugin_event(
            "sing_cancel",
            f"Cancelled pending task [{request_id}] for recalled message [{message_id}] in group [{group_id}]",
        )
    )
    return True


@dataclass(frozen=True, slots=True)
class SingSubmission:
    bot_id: int
    group_id: int
    user_id: int
    speaker: str
    song_query: str
    key: int | str = 0
    chunk_index: int = 0
    request_id: str = ""
    message_id: int = 0


@dataclass(frozen=True, slots=True)
class PlaySubmission:
    bot_id: int
    group_id: int
    user_id: int
    speaker: str
    message_id: int = 0


@dataclass(frozen=True, slots=True)
class RequestSongSubmission:
    bot_id: int
    group_id: int
    user_id: int
    song_name: str
    request_id: str = ""
    message_id: int = 0


def log_ignored_remote_task_id(local_task_id: str, remote_task_id: str, task_payload: dict) -> None:
    if not remote_task_id or remote_task_id == local_task_id:
        return
    logger.info(
        format_plugin_event(
            "task_alias",
            f"Task alias ignored, request [{local_task_id}] differs from remote task [{remote_task_id}], "
            f"task_type [{task_payload.get('task_type', '') or '-'}]",
        )
    )


def response_task_id(response) -> str:
    try:
        data = response.json() if response is not None else {}
    except Exception as exc:
        logger.warning("sing response json parse failed: {}", exc)
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


def task_payload(*, bot_id: int, group_id: int, user_id: int, task_type: str) -> dict:
    return {
        "bot_id": bot_id,
        "group_id": group_id,
        "user_id": user_id,
        "task_type": task_type,
        "start_time": time.time(),
    }


async def submit_registered_task(
    *,
    request_id: str,
    payload: dict,
    url: str,
    body: dict,
) -> tuple[object | None, str]:
    await TaskManager.add_task(request_id, payload)
    try:
        response = await HTTPXClient.post(url, json=body)
    except Exception as exc:
        logger.warning("sing task submission to [{}] failed: {}", url, exc)
        await TaskManager.remove_task(request_id)
        raise
    remote_task_id = response_task_id(response)
    if not response or not remote_task_id:
        await TaskManager.remove_task(request_id)
        return response, ""
    log_ignored_remote_task_id(request_id, remote_task_id, payload)
    return response, remote_task_id


async def submit_sing(request: SingSubmission) -> str:
    plugin_config = get_sing_config()
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}] received a sing request in group [{request.group_id}] "
            f"from user [{request.user_id}] for song [{request.song_query}] by speaker [{request.speaker}]",
        )
    )
    song_id = await get_song_id(request.song_query)
    if not song_id:
        return FAILED_REPLY
    request_id = request.request_id or str(ULID())
    payload = task_payload(
        bot_id=request.bot_id,
        group_id=request.group_id,
        user_id=request.user_id,
        task_type="sing",
    )
    payload["song_id"] = song_id
    url = f"{sing_server_url(plugin_config)}{plugin_config.sing_endpoint}/{request_id}"
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}] dispatched a sing request [{request_id}] "
            f"in group [{request.group_id}] from user [{request.user_id}] by speaker [{request.speaker}]",
        )
    )
    response, remote_task_id = await submit_registered_task(
        request_id=request_id,
        payload=payload,
        url=url,
        body={
            "speaker": request.speaker,
            "song_id": song_id,
            "sing_length": plugin_config.sing_length,
            "chunk_index": request.chunk_index,
            "key": request.key,
        },
    )
    if not remote_task_id:
        return FAILED_REPLY
    remember_message_task(request.group_id, request.message_id, request_id)
    task_part = f", task [{remote_task_id}]" if remote_task_id != request_id else ""
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}] sing request [{request_id}] accepted{task_part}, "
            f"status [{response_status_code(response) or '-'}]",
        )
    )
    if request.chunk_index == 0:
        await GroupConfig(request.group_id).update_sing_progress(
            SingProgress(song_id=str(song_id), chunk_index=0, key=request.key)
        )
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}] queued a song [{song_id}] for user [{request.user_id}] "
            f"in group [{request.group_id}] by speaker [{request.speaker}]",
        )
    )
    return ACCEPTED_REPLY


async def submit_play(request: PlaySubmission) -> str:
    plugin_config = get_sing_config()
    logger.info(
        format_plugin_event(
            "play",
            f"Bot [{request.bot_id}] received a random sing request in group [{request.group_id}] "
            f"from user [{request.user_id}] by speaker [{request.speaker}]",
        )
    )
    request_id = str(ULID())
    payload = task_payload(
        bot_id=request.bot_id,
        group_id=request.group_id,
        user_id=request.user_id,
        task_type="play",
    )
    url = f"{sing_server_url(plugin_config)}{plugin_config.play_endpoint}/{request_id}"
    logger.info(
        format_plugin_event(
            "play",
            f"Bot [{request.bot_id}] dispatched a play request [{request_id}] "
            f"in group [{request.group_id}] from user [{request.user_id}] by speaker [{request.speaker}]",
        )
    )
    response, remote_task_id = await submit_registered_task(
        request_id=request_id,
        payload=payload,
        url=url,
        body={"speaker": request.speaker},
    )
    if not remote_task_id:
        return FAILED_REPLY
    remember_message_task(request.group_id, request.message_id, request_id)
    task_part = f", task [{remote_task_id}]" if remote_task_id != request_id else ""
    logger.info(
        format_plugin_event(
            "play",
            f"Bot [{request.bot_id}] play request [{request_id}] accepted{task_part}, "
            f"status [{response_status_code(response) or '-'}]",
        )
    )
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}] queued a random song for user [{request.user_id}] "
            f"in group [{request.group_id}] by speaker [{request.speaker}]",
        )
    )
    return ACCEPTED_REPLY


async def submit_request_song(request: RequestSongSubmission) -> str | None:
    plugin_config = get_sing_config()
    logger.info(
        format_plugin_event(
            "request",
            f"Bot [{request.bot_id}] received a song request in group [{request.group_id}] "
            f"from user [{request.user_id}] for song [{request.song_name}]",
        )
    )
    song_id = await get_song_id(request.song_name)
    if not song_id:
        return None
    request_id = str(ULID())
    payload = task_payload(
        bot_id=request.bot_id,
        group_id=request.group_id,
        user_id=request.user_id,
        task_type="request",
    )
    payload["song_id"] = song_id
    url = f"{sing_server_url(plugin_config)}{plugin_config.request_endpoint}/{request_id}"
    logger.info(
        format_plugin_event(
            "request",
            f"Bot [{request.bot_id}] dispatched a song request [{request_id}] "
            f"in group [{request.group_id}] from user [{request.user_id}] for song [{request.song_name}] "
            f"(id [{song_id}])",
        )
    )
    response, remote_task_id = await submit_registered_task(
        request_id=request_id,
        payload=payload,
        url=url,
        body={"song_id": song_id},
    )
    if not remote_task_id:
        return FAILED_REPLY
    remember_message_task(request.group_id, request.message_id, request_id)
    task_part = f", task [{remote_task_id}]" if remote_task_id != request_id else ""
    logger.info(
        format_plugin_event(
            "request",
            f"Bot [{request.bot_id}] song request [{request_id}] accepted{task_part}, "
            f"status [{response_status_code(response) or '-'}]",
        )
    )
    await GroupConfig(request.group_id).update_sing_progress(SingProgress(song_id=str(song_id), chunk_index=0, key=0))
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}] queued a song request [{song_id}] for user [{request.user_id}] "
            f"in group [{request.group_id}]",
        )
    )
    return ACCEPTED_REPLY
