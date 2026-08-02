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
    config_api.install_hot_reload_config = lambda model, **kwargs: types.SimpleNamespace(
        get=lambda: model(),
        reload=lambda: None,
        clear_cache=lambda: None,
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


def test_format_sing_speakers_help_groups_by_voice() -> None:
    text = sing_config.format_sing_speakers_help(
        {"牛牛": "pallas", "帕拉斯": "pallas", "兔兔": "amiya"},
    )
    assert "pallas（牛牛、帕拉斯）" in text
    assert "amiya（兔兔）" in text


def test_apply_sing_speakers_to_menu_data_lists_voices() -> None:
    menu = [
        {
            "func": "牛牛唱歌",
            "trigger_condition": "牛牛唱歌 歌曲名 [key=±N]",
            "detail_des": "按歌名搜索并翻唱。",
        },
        {
            "func": "点歌",
            "trigger_condition": "牛牛点歌 歌曲名",
            "detail_des": "播放原曲。",
        },
    ]
    out = sing_config.apply_sing_speakers_to_menu_data(
        menu,
        {"牛牛": "pallas", "帕拉斯": "pallas"},
    )
    assert out[0]["trigger_condition"] == "〈音色〉唱歌 歌曲名 [key=±N]"
    assert out[1]["trigger_condition"] == "〈音色〉点歌 歌曲名"
    assert "可用音色：pallas（牛牛、帕拉斯）" in out[0]["detail_des"]
    # 热载不叠加
    again = sing_config.apply_sing_speakers_to_menu_data(out, {"牛牛": "pallas"})
    assert again[0]["detail_des"].count("可用音色：") == 1
    assert "pallas（牛牛）" in again[0]["detail_des"]


def test_sync_sing_help_menu_updates_usage_and_menu() -> None:
    meta = types.SimpleNamespace(
        usage="旧说明",
        extra={
            "menu_data": [
                {
                    "func": "牛牛唱歌",
                    "trigger_condition": "牛牛唱歌 歌曲名",
                    "detail_des": "翻唱。",
                }
            ]
        },
    )
    # join_usage 依赖 pallas.api.metadata；单测里 stub
    meta_api = types.ModuleType("pallas.api.metadata")
    meta_api.join_usage = lambda *lines: "\n".join(lines)
    meta_api.usage_line = lambda trigger, brief: f"{trigger} — {brief}"
    sys.modules["pallas.api.metadata"] = meta_api

    text = sing_config.sync_sing_help_menu({"牛牛": "pallas", "帕拉斯": "pallas"}, meta=meta)
    assert "pallas（牛牛、帕拉斯）" in text
    assert "可用音色" in meta.usage
    assert meta.extra["menu_data"][0]["trigger_condition"].startswith("〈音色〉")
    assert "可用音色：pallas（牛牛、帕拉斯）" in meta.extra["menu_data"][0]["detail_des"]
