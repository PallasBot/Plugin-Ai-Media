from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_media_conn():
    path = SRC / "pallas_plugin_ai_media_runtime" / "conn.py"
    spec = importlib.util.spec_from_file_location(
        "pallas_plugin_ai_media_runtime.conn",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pallas_plugin_ai_media_runtime.conn"] = module
    spec.loader.exec_module(module)
    return module


def _load_sing_config():
    config_api = types.ModuleType("pallas.api.config")
    config_api.field_help = lambda *parts: " ".join(parts)
    config_api.install_hot_reload_config = lambda model, **kwargs: (
        types.SimpleNamespace(
            get=lambda: model(),
            reload=lambda: None,
            clear_cache=lambda: None,
        )
    )
    sys.modules["pallas.api.config"] = config_api
    path = SRC / "pallas_plugin_sing" / "config.py"
    spec = importlib.util.spec_from_file_location("pallas_plugin_sing.config", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pallas_plugin_sing.config"] = module
    spec.loader.exec_module(module)
    return module


def _load_tts_config():
    config_api = types.ModuleType("pallas.api.config")
    config_api.field_help = lambda *parts: " ".join(parts)
    config_api.install_hot_reload_config = lambda model, **kwargs: (
        types.SimpleNamespace(
            get=lambda: model(),
            reload=lambda: None,
            clear_cache=lambda: None,
        )
    )
    sys.modules["pallas.api.config"] = config_api
    path = SRC / "pallas_plugin_tts" / "config.py"
    spec = importlib.util.spec_from_file_location("pallas_plugin_tts.config", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pallas_plugin_tts.config"] = module
    spec.loader.exec_module(module)
    return module


def test_resolve_ai_server_url_prefers_env(monkeypatch) -> None:
    conn = _load_media_conn()
    monkeypatch.setenv("AI_SERVER_HOST", "pallasbot-ai")
    monkeypatch.setenv("AI_SERVER_PORT", "9099")
    assert conn.resolve_ai_server_url(fallback_host="127.0.0.1", fallback_port=8080) == (
        "http://pallasbot-ai:9099"
    )


def test_resolve_ai_server_url_falls_back_to_cfg(monkeypatch) -> None:
    conn = _load_media_conn()
    monkeypatch.delenv("AI_SERVER_HOST", raising=False)
    monkeypatch.delenv("AI_SERVER_PORT", raising=False)
    assert conn.resolve_ai_server_url(fallback_host="10.0.0.2", fallback_port=9100) == (
        "http://10.0.0.2:9100"
    )


def test_resolve_media_bearer_token_prefers_tts_api_token(monkeypatch) -> None:
    conn = _load_media_conn()
    monkeypatch.setenv("TTS_API_TOKEN", "from-tts")
    monkeypatch.setenv("PALLAS_AI_API_TOKEN", "from-ai")
    assert conn.resolve_media_bearer_token(fallback="cfg") == "from-tts"


def test_resolve_media_bearer_token_falls_back_to_cfg(monkeypatch) -> None:
    conn = _load_media_conn()
    monkeypatch.delenv("TTS_API_TOKEN", raising=False)
    monkeypatch.delenv("PALLAS_AI_API_TOKEN", raising=False)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    assert conn.resolve_media_bearer_token(fallback="cfg-token") == "cfg-token"


def test_sing_server_url_uses_env(monkeypatch) -> None:
    sing = _load_sing_config()
    monkeypatch.setenv("AI_SERVER_HOST", "sidecar")
    monkeypatch.setenv("AI_SERVER_PORT", "9191")
    assert sing.sing_server_url(sing.Config(ai_server_host="127.0.0.1", ai_server_port=9099)) == (
        "http://sidecar:9191"
    )


def test_sing_service_fields_are_ui_hidden() -> None:
    sing = _load_sing_config()
    for name in (
        "ai_server_host",
        "ai_server_port",
        "sing_endpoint",
        "play_endpoint",
        "request_endpoint",
    ):
        extra = sing.Config.model_fields[name].json_schema_extra or {}
        assert extra.get("ui_hidden") is True, name


def test_tts_auth_headers_prefer_env_token(monkeypatch) -> None:
    tts = _load_tts_config()
    monkeypatch.setenv("TTS_API_TOKEN", "env-secret")
    headers = tts.tts_auth_headers(tts.Config(api_token="cfg-secret"))
    assert headers == {"Authorization": "Bearer env-secret"}


def test_tts_service_fields_are_ui_hidden() -> None:
    tts = _load_tts_config()
    for name in ("ai_server_host", "ai_server_port", "tts_endpoint", "api_token"):
        extra = tts.Config.model_fields[name].json_schema_extra or {}
        assert extra.get("ui_hidden") is True, name
