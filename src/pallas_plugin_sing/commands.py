from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SING_CMD = "唱歌"
REQUEST_SONG_CMD = "点歌"
SING_CONTINUE_CMDS = frozenset({"继续唱", "接着唱"})
WHAT_SONG_CMDS = frozenset({"什么歌", "哪首歌", "啥歌"})


@dataclass(frozen=True, slots=True)
class ParseOutcome[T]:
    value: T | None = None
    rejection: str | None = None


@dataclass(frozen=True, slots=True)
class SingRequest:
    kind: Literal["sing", "continue"]
    speaker: str
    song_query: str | None = None
    key: int | str = 0
    chunk_index: int = 0


@dataclass(frozen=True, slots=True)
class PlayRequest:
    speaker: str


@dataclass(frozen=True, slots=True)
class SongRequest:
    speaker: str
    song_name: str


@dataclass(frozen=True, slots=True)
class SingCommandMatches:
    sing: SingRequest | None = None
    play: PlayRequest | None = None
    request_song: SongRequest | None = None
    song_title: bool = False


def parse_sing_commands(text: str, speakers: dict[str, str] | None) -> SingCommandMatches:
    plain = text or ""
    speaker_map = speakers or {}
    return SingCommandMatches(
        sing=parse_sing_request(plain, speaker_map).value,
        play=parse_play_request(plain, speaker_map),
        request_song=parse_song_request(plain, speaker_map).value,
        song_title=matches_song_title(plain, speaker_map),
    )


def parse_sing_request(text: str, speakers: dict[str, str]) -> ParseOutcome[SingRequest]:
    if not text or (SING_CMD not in text and not any(cmd in text for cmd in SING_CONTINUE_CMDS)):
        return ParseOutcome(rejection="no sing keyword")
    if text.endswith(SING_CMD):
        return ParseOutcome(rejection="endswith sing cmd -> play path")

    matched = match_speaker_in_order(text, speakers)
    if matched is None:
        return ParseOutcome(rejection="no speaker prefix")
    command_text, speaker = matched

    if "key=" in command_text:
        key_pos = command_text.find("key=")
        key: int | str = command_text[key_pos + 4 :].strip()
        command_text = command_text.replace("key=" + key, "")
        try:
            key_int = int(key)
        except ValueError:
            return ParseOutcome(rejection=f"invalid key: {key}")
        if key_int < -12 or key_int > 12:
            return ParseOutcome(rejection=f"key out of range: {key_int}")
    else:
        key = 0

    if command_text.startswith(SING_CMD):
        song_query = command_text.replace(SING_CMD, "").strip()
        if not song_query:
            return ParseOutcome(rejection="empty song key after sing cmd")
        return ParseOutcome(value=SingRequest(kind="sing", speaker=speaker, song_query=song_query, key=key))

    if command_text in SING_CONTINUE_CMDS:
        return ParseOutcome(value=SingRequest(kind="continue", speaker=speaker, key=key))
    return ParseOutcome(rejection="unmatched command")


def parse_play_request(text: str, speakers: dict[str, str]) -> PlayRequest | None:
    plain = text.strip()
    if not plain:
        return None
    for name, speaker in sorted(speakers.items(), key=lambda item: len(str(item[0] or "")), reverse=True):
        head = str(name or "").strip()
        voice = str(speaker or "").strip()
        if not head or not voice or not plain.startswith(head):
            continue
        if plain[len(head) :].strip() == SING_CMD:
            return PlayRequest(speaker=voice)
    return None


def parse_song_request(text: str, speakers: dict[str, str]) -> ParseOutcome[SongRequest]:
    if not text or REQUEST_SONG_CMD not in text:
        return ParseOutcome(rejection="no request keyword")
    if text.endswith(REQUEST_SONG_CMD):
        return ParseOutcome(rejection="request pattern not matched")
    matched = match_speaker_in_order(text, speakers)
    if matched is None:
        return ParseOutcome(rejection="no speaker prefix")
    command_text, speaker = matched
    if not command_text.startswith(REQUEST_SONG_CMD):
        return ParseOutcome(rejection="request pattern not matched")
    song_name = command_text.replace(REQUEST_SONG_CMD, "").strip()
    if not song_name:
        return ParseOutcome(rejection="empty song name")
    return ParseOutcome(value=SongRequest(speaker=speaker, song_name=song_name))


def matches_song_title(text: str, speakers: dict[str, str]) -> bool:
    return any(text.startswith(name) for name in speakers) and any(key in text for key in WHAT_SONG_CMDS)


def match_speaker_in_order(text: str, speakers: dict[str, str]) -> tuple[str, str] | None:
    for name, speaker in speakers.items():
        if text.startswith(name):
            return text.replace(name, "").strip(), speaker
    return None
