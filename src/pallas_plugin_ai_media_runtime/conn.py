"""媒体侧车连接：统一读 AI_SERVER_* / Bearer，供唱歌与 TTS 共用。"""

from __future__ import annotations

import os


def resolve_ai_server_url(
    *,
    fallback_host: str = "127.0.0.1",
    fallback_port: int = 9099,
) -> str:
    host = (os.environ.get("AI_SERVER_HOST") or "").strip() or (fallback_host or "").strip() or "127.0.0.1"
    port_raw = (os.environ.get("AI_SERVER_PORT") or "").strip()
    if port_raw.isdigit():
        port = int(port_raw)
    else:
        try:
            port = int(fallback_port)
        except (TypeError, ValueError):
            port = 9099
    if not 1 <= port <= 65535:
        port = 9099
    return f"http://{host}:{port}"


def resolve_media_bearer_token(*, fallback: str = "") -> str:
    for key in ("TTS_API_TOKEN", "PALLAS_AI_API_TOKEN", "API_BEARER_TOKEN"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return (fallback or "").strip()
