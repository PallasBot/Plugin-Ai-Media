"""「牛牛说」文本解析（无外部依赖，便于单测）。"""

from __future__ import annotations

SPEAK_PREFIXES = ("牛牛说",)


def is_speak_command_text(plain: str) -> bool:
    """是否为合法「牛牛说」口令（前缀后须结束或空白，避免「牛牛说啥呢」误触发）。"""
    text = (plain or "").strip()
    for prefix in SPEAK_PREFIXES:
        if text == prefix:
            return True
        if text.startswith(prefix) and len(text) > len(prefix) and text[len(prefix)].isspace():
            return True
    return False


def extract_speak_text(plain: str) -> str:
    text = (plain or "").strip()
    if not is_speak_command_text(text):
        return ""
    for prefix in SPEAK_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if "\n" in text:
        text = text.split("\n", 1)[0].strip()
    return text
