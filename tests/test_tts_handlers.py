from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_text_module():
    path = SRC / "pallas_plugin_tts" / "text.py"
    spec = importlib.util.spec_from_file_location("pallas_plugin_tts.text", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pallas_plugin_tts.text"] = module
    spec.loader.exec_module(module)
    return module


text_mod = _load_text_module()
extract_speak_text = text_mod.extract_speak_text


def test_extract_speak_text_strips_prefix() -> None:
    assert extract_speak_text("牛牛说 你好呀") == "你好呀"
    assert extract_speak_text("牛牛说你好") == "你好"
    assert extract_speak_text("牛牛说 第一行\n第二行") == "第一行"
    assert extract_speak_text("随便说说") == "随便说说"
    assert extract_speak_text("") == ""
