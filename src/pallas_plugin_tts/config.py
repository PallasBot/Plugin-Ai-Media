from __future__ import annotations

from typing import Literal

from pallas.api.config import field_help, install_hot_reload_config
from pydantic import BaseModel, Field


def _ui(group: str, order: int, **extra: object) -> dict[str, object]:
    return {"ui_group": group, "ui_order": order, **extra}


TtsRoute = Literal["sidecar", "cloud"]


class Config(BaseModel, extra="ignore"):
    tts_enable: bool = Field(
        default=False,
        description=field_help(
            "是否启用「牛牛说」语音合成",
            "开启前请确认 AI Runtime 已部署，且音色/默认参考音已配置",
        ),
        json_schema_extra=_ui("语音", 10),
    )
    ai_server_host: str = Field(
        default="127.0.0.1",
        description=field_help(
            "TTS 媒体服务所在机器的地址",
            "本机填 127.0.0.1；服务在别的机器上填其 IP 或域名",
        ),
        json_schema_extra=_ui("服务地址", 10),
    )
    ai_server_port: int = Field(
        default=9099,
        description=field_help(
            "TTS 媒体服务监听的端口",
            "填整数，需与后端实际监听端口一致",
        ),
        json_schema_extra=_ui("服务地址", 20),
    )
    tts_endpoint: str = Field(
        default="/v1/tts",
        description=field_help(
            "提交 TTS 任务的接口路径",
            "以 / 开头；推荐 /v1/tts（需 Bearer）；旧路径可用 /api/tts",
        ),
        json_schema_extra=_ui("服务地址", 30),
    )
    api_token: str = Field(
        default="",
        description=field_help(
            "调用 /v1 时的 Bearer Token",
            "须与 AI 侧 PALLAS_AI_API_TOKEN 一致；Token 为空且 AI 未强制鉴权时可留空",
        ),
        json_schema_extra=_ui("服务地址", 40, secret=True),
    )
    tts_route: TtsRoute = Field(
        default="sidecar",
        description=field_help(
            "语音合成走哪条通路",
            "sidecar=本机/侧车 AI Runtime；cloud=直连云端（尚未接入，选中会提示未配置）",
        ),
        json_schema_extra=_ui("语音", 20),
    )
    tts_timeout_sec: float = Field(
        default=60.0,
        ge=5.0,
        le=300.0,
        description=field_help(
            "提交 TTS 任务的 HTTP 超时（秒）",
            "仅覆盖提交请求；合成与回调另算",
        ),
        json_schema_extra=_ui("语音", 30),
    )
    tts_max_chars: int = Field(
        default=200,
        ge=1,
        le=2000,
        description=field_help(
            "单次「牛牛说」允许的最大字数",
            "超出时提示缩短后再试",
        ),
        json_schema_extra=_ui("语音", 40),
    )


def on_tts_config_reload(cfg: Config) -> None:
    from packages.help.plugin_availability import (
        invalidate_plugin_help_availability_cache,
    )

    invalidate_plugin_help_availability_cache()


plugin_webui = install_hot_reload_config(Config, config_module=__name__, on_reload=on_tts_config_reload)
get_tts_config = plugin_webui.get
reload_tts_config = plugin_webui.reload
clear_tts_config_cache = plugin_webui.clear_cache


def tts_server_url(cfg: Config | None = None) -> str:
    c = cfg or get_tts_config()
    return f"http://{c.ai_server_host}:{c.ai_server_port}"


def tts_auth_headers(cfg: Config | None = None) -> dict[str, str]:
    c = cfg or get_tts_config()
    token = (c.api_token or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}
