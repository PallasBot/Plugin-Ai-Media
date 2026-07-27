"""「牛牛说」文本解析（无外部依赖，便于单测）。"""

from __future__ import annotations

SPEAK_PREFIXES = ("牛牛说",)


def extract_speak_text(plain: str) -> str:
    text = (plain or "").strip()
    for prefix in SPEAK_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if "\n" in text:
        text = text.split("\n", 1)[0].strip()
    return text
