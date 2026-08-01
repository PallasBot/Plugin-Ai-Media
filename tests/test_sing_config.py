from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_sing_config_module():
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

    config_path = SRC / "pallas_plugin_sing" / "config.py"
    spec = importlib.util.spec_from_file_location(
        "pallas_plugin_sing.config",
        config_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["pallas_plugin_sing.config"] = module
    spec.loader.exec_module(module)
    return module


sing_config = _load_sing_config_module()
Config = sing_config.Config
sing_runtime_mode = sing_config.sing_runtime_mode


def test_sing_runtime_mode_defaults_to_legacy() -> None:
    assert sing_runtime_mode(Config()) == "legacy"


def test_sing_runtime_mode_accepts_media_task() -> None:
    assert sing_runtime_mode(Config(sing_runtime_mode="media_task")) == "media_task"


def test_sing_runtime_mode_normalizes_unknown_values() -> None:
    assert sing_runtime_mode(Config(sing_runtime_mode="plugin")) == "legacy"


def test_sing_rule_debug_defaults_false() -> None:
    assert Config().sing_rule_debug is False


def test_build_sing_command_prefixes_from_speakers() -> None:
    build = sing_config.build_sing_command_prefixes
    prefixes = build({"一歌": "pallas", "牛牛": "pallas"})
    assert "一歌唱歌" in prefixes
    assert "一歌点歌" in prefixes
    assert "一歌继续唱" in prefixes
    assert "牛牛唱歌" in prefixes
    assert "一歌" not in prefixes


def test_build_sing_command_prefixes_skips_blank_names() -> None:
    build = sing_config.build_sing_command_prefixes
    assert build({"": "pallas", "  ": "x"}) == []
