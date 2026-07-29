from __future__ import annotations

from typing import Literal

from pallas.api.config import field_help, install_hot_reload_config
from pydantic import BaseModel, Field

from pallas_plugin_ai_media_runtime.conn import resolve_ai_server_url, resolve_media_bearer_token


def _ui(group: str, order: int, **extra: object) -> dict[str, object]:
    return {"ui_group": group, "ui_order": order, **extra}


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
            "由 AI 配置 · 媒体服务统一管理；此处仅作兼容回退",
        ),
        json_schema_extra=_ui("服务地址", 10, ui_hidden=True),
    )
    ai_server_port: int = Field(
        default=9099,
        description=field_help(
            "TTS 媒体服务监听的端口",
            "由 AI 配置 · 媒体服务统一管理；此处仅作兼容回退",
        ),
        json_schema_extra=_ui("服务地址", 20, ui_hidden=True),
    )
    tts_endpoint: str = Field(
        default="/v1/tts",
        description=field_help(
            "提交 TTS 任务的接口路径",
            "以 / 开头；推荐 /v1/tts（需 Bearer）；旧路径可用 /api/tts",
        ),
        json_schema_extra=_ui("服务地址", 30, ui_hidden=True),
    )
    api_token: str = Field(
        default="",
        description=field_help(
            "调用 /v1 时的 Bearer Token",
            "由 AI 配置 · 媒体服务统一管理；须与 AI 侧 PALLAS_AI_API_TOKEN 一致",
        ),
        json_schema_extra=_ui("服务地址", 40, secret=True, ui_hidden=True),
    )
    tts_route: Literal["sidecar", "cloud"] = Field(
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


Config.model_rebuild()


def on_tts_config_reload(cfg: Config) -> None:
    from packages.help.plugin_availability import (
        invalidate_plugin_help_availability_cache,
    )

    invalidate_plugin_help_availability_cache()


_FIELD_TO_ENV = {
    "tts_enable": "TTS_ENABLE",
    "ai_server_host": "AI_SERVER_HOST",
    "ai_server_port": "AI_SERVER_PORT",
    "tts_endpoint": "TTS_ENDPOINT",
    "api_token": "TTS_API_TOKEN",
    "tts_route": "TTS_ROUTE",
    "tts_timeout_sec": "TTS_TIMEOUT_SEC",
    "tts_max_chars": "TTS_MAX_CHARS",
}

plugin_webui = install_hot_reload_config(
    Config,
    config_module=__name__,
    on_reload=on_tts_config_reload,
    field_to_env=_FIELD_TO_ENV,
)
get_tts_config = plugin_webui.get
reload_tts_config = plugin_webui.reload
clear_tts_config_cache = plugin_webui.clear_cache


def tts_server_url(cfg: Config | None = None) -> str:
    c = cfg or get_tts_config()
    return resolve_ai_server_url(
        fallback_host=str(c.ai_server_host or "127.0.0.1"),
        fallback_port=int(c.ai_server_port or 9099),
    )


def tts_auth_headers(cfg: Config | None = None) -> dict[str, str]:
    c = cfg or get_tts_config()
    token = resolve_media_bearer_token(fallback=str(c.api_token or ""))
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}
