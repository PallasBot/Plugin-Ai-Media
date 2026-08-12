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


@dataclass(frozen=True, slots=True)
class PlaySubmission:
    bot_id: int
    group_id: int
    user_id: int
    speaker: str


@dataclass(frozen=True, slots=True)
class RequestSongSubmission:
    bot_id: int
    group_id: int
    user_id: int
    song_name: str
    request_id: str = ""


def log_ignored_remote_task_id(local_task_id: str, remote_task_id: str, task_payload: dict) -> None:
    if not remote_task_id or remote_task_id == local_task_id:
        return
    logger.info(
        format_plugin_event(
            "task_alias",
            f"Task alias ignored, request [id={local_task_id}] differs from remote task [id={remote_task_id}], "
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
    except Exception:
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
            f"Bot [{request.bot_id}] dispatched a sing request [id={request_id}] "
            f"in group [{request.group_id}] by speaker [{request.speaker}]",
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
    task_part = f", task [id={remote_task_id}]" if remote_task_id != request_id else ""
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}]'s sing request [id={request_id}] was accepted{task_part}, "
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
            f"Bot [{request.bot_id}] queued a song [id={song_id}] for user [{request.user_id}] "
            f"in group [{request.group_id}] by speaker [{request.speaker}]",
        )
    )
    return ACCEPTED_REPLY


async def submit_play(request: PlaySubmission) -> str:
    plugin_config = get_sing_config()
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
            f"Bot [{request.bot_id}] dispatched a play request [id={request_id}] "
            f"in group [{request.group_id}] by speaker [{request.speaker}]",
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
    task_part = f", task [id={remote_task_id}]" if remote_task_id != request_id else ""
    logger.info(
        format_plugin_event(
            "play",
            f"Bot [{request.bot_id}]'s play request [id={request_id}] was accepted{task_part}, "
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
            f"Bot [{request.bot_id}] dispatched a song request [id={request_id}] "
            f"in group [{request.group_id}], song [id={song_id},name={request.song_name}]",
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
    task_part = f", task [id={remote_task_id}]" if remote_task_id != request_id else ""
    logger.info(
        format_plugin_event(
            "request",
            f"Bot [{request.bot_id}]'s song request [id={request_id}] was accepted{task_part}, "
            f"status [{response_status_code(response) or '-'}]",
        )
    )
    await GroupConfig(request.group_id).update_sing_progress(SingProgress(song_id=str(song_id), chunk_index=0, key=0))
    logger.info(
        format_plugin_event(
            "sing",
            f"Bot [{request.bot_id}] queued a song request [id={song_id}] for user [{request.user_id}] "
            f"in group [{request.group_id}]",
        )
    )
    return ACCEPTED_REPLY
