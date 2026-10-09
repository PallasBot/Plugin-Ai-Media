import re

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, PrivateMessageEvent
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.params import ArgStr
from nonebot.typing import T_State
from pallas.api.logging import format_plugin_event
from pallas.api.perm import permission_for_command
from pallas.core.shared.utils import HTTPXClient
from pydantic import BaseModel

from pallas_plugin_tts.config import tts_auth_headers

from ..config import sing_server_url


class NCMLoginConfig(BaseModel, extra="ignore"):
    ai_server_host: str = "127.0.0.1"
    ai_server_port: int = 9099
    ncm_login_endpoint: str = "/api/ncm/login/cellphone/send-sms"
    ncm_verify_endpoint: str = "/api/ncm/login/cellphone/verify-sms"
    ncm_login_status_endpoint: str = "/api/ncm/login/status"
    ncm_logout_endpoint: str = "/api/ncm/login/logout"


ncm_cfg = NCMLoginConfig()
NCM_SEARCH_TIMEOUT = 15.0

ncm_login_cmd = on_command(
    "网易云登录",
    priority=10,
    block=True,
    permission=permission_for_command("sing.ncm_login"),
)
ncm_logout_cmd = on_command(
    "网易云登出",
    priority=10,
    block=True,
    permission=permission_for_command("sing.ncm_logout"),
)


@ncm_login_cmd.handle()
async def handle_first_receive(event: MessageEvent, state: T_State):
    if not isinstance(event, PrivateMessageEvent):
        return

    # 检查是否已经登录
    if await is_ncm_logged_in():
        await ncm_login_cmd.finish("已登录")
        return

    state["need_phone"] = True
    await ncm_login_cmd.send("请输入手机号：")


@ncm_login_cmd.got("phone")
async def got_phone(event: MessageEvent, state: T_State, phone: str = ArgStr()):
    if not state.get("need_phone"):
        return

    phone = phone.strip()
    if not re.match(r"^1[3-9]\d{9}$", phone):
        await ncm_login_cmd.reject("手机号格式不正确，请重新输入：")

    state["phone"] = phone

    try:
        url = f"{sing_server_url()}{ncm_cfg.ncm_login_endpoint}"
        response = await HTTPXClient.post(url, json={"phone": phone, "ctcode": 86})

        if response and response.json().get("code", 0) == 200:
            await ncm_login_cmd.send("验证码已发送，请查收短信。")
        else:
            await ncm_login_cmd.send("验证码发送失败")

    except Exception:
        await ncm_login_cmd.send("验证码发送失败")
    state["need_captcha"] = True


@ncm_login_cmd.got("captcha")
async def got_captcha(event: MessageEvent, state: T_State, captcha: str = ArgStr()):
    if not state.get("need_captcha"):
        return

    captcha = captcha.strip()
    if not re.match(r"^\d{4,8}$", captcha):
        await ncm_login_cmd.reject("验证码格式不正确，请重新输入：")

    phone = state["phone"]

    try:
        url = f"{sing_server_url()}{ncm_cfg.ncm_verify_endpoint}"
        response = await HTTPXClient.post(
            url,
            json={"phone": phone, "captcha": captcha, "ctcode": 86},
        )

        if response and response.json().get("success"):
            logger.info(format_plugin_event("ncm_login", f"Bot [{event.self_id}] logged into NetEase Cloud Music"))
            await ncm_login_cmd.send("登录成功！")
        else:
            await ncm_login_cmd.finish("登录失败，请检查验证码是否正确。")

    except Exception:
        await ncm_login_cmd.finish("登录过程中出现错误，请稍后重试。")


@ncm_logout_cmd.handle()
async def handle_logout(event: MessageEvent):
    if not isinstance(event, PrivateMessageEvent):
        return

    try:
        url = f"{sing_server_url()}{ncm_cfg.ncm_logout_endpoint}"
        response = await HTTPXClient.post(url)
        if response and response.json().get("success"):
            logger.info(format_plugin_event("ncm_logout", f"Bot [{event.self_id}] logged out of NetEase Cloud Music"))
            await ncm_logout_cmd.finish("已成功退出网易云音乐账号。")
        else:
            await ncm_logout_cmd.finish("登出失败，请稍后重试。")
    except FinishedException:
        raise
    except httpx.TimeoutException:
        await ncm_logout_cmd.finish("登出请求超时，请稍后重试。")
    except httpx.ConnectError:
        await ncm_logout_cmd.finish("无法连接到服务器，请检查网络或服务器状态。")
    except Exception as e:
        logger.error(f"ncm logout unexpected error: {e}", exc_info=True)
        await ncm_logout_cmd.finish(f"登出过程中出现错误: {e!s}，请稍后重试。")


async def is_ncm_logged_in():
    try:
        url = f"{sing_server_url()}{ncm_cfg.ncm_login_status_endpoint}"
        response = await HTTPXClient.get(url)
        if response and response.json().get("success"):
            return True
        return False
    except Exception:
        return False


async def get_song_id(song_name: str):
    if not song_name:
        return None
    if song_name.isdigit():
        return song_name

    headers = ncm_api_headers()
    if not headers:
        return None

    response = await HTTPXClient.get(
        f"{sing_server_url()}/v1/ncm/search",
        params={"q": song_name},
        headers=headers,
        timeout=NCM_SEARCH_TIMEOUT,
    )
    if response is None:
        return None

    try:
        payload = response.json()
    except (TypeError, ValueError):
        return None
    song_id = payload.get("song_id") if isinstance(payload, dict) else None
    if isinstance(song_id, bool) or not isinstance(song_id, (int, str)) or not str(song_id).isdigit():
        return None
    return song_id


def ncm_api_headers() -> dict[str, str] | None:
    return tts_auth_headers() or None


async def get_song_title_with_artist(song_id):
    """查询歌曲名与歌手列表，返回 (歌名, [歌手...])；无有效结果时返回 None。"""
    if isinstance(song_id, bool) or not str(song_id).isdigit():
        return None
    headers = ncm_api_headers()
    if not headers:
        return None

    response = await HTTPXClient.get(
        f"{sing_server_url()}/v1/ncm/songs/{song_id}",
        headers=headers,
        timeout=NCM_SEARCH_TIMEOUT,
    )
    if response is None:
        return None

    try:
        payload = response.json()
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    name = str(payload.get("name") or "").strip()
    if not name:
        return None
    raw_artists = payload.get("artists")
    artists = (
        [str(artist).strip() for artist in raw_artists if str(artist).strip()] if isinstance(raw_artists, list) else []
    )
    return name, artists
