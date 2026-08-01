import time

from nonebot import logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.exception import ActionFailed, FinishedException, NetworkError
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.typing import T_State
from pallas.api.config import GroupConfig, TaskManager
from pallas.api.limits import is_command_cooldown_ready, refresh_command_cooldown
from pallas.api.metadata import (
    PLUGIN_EXTRA_VERSION,
    PLUGIN_HOMEPAGE,
    PLUGIN_MENU_TEMPLATE,
    SCENE_GROUP,
    SCENE_PRIVATE,
    join_usage,
    usage_line,
)
from pallas.api.perm import group_message_permission_for_command
from pallas.api.platform import llm_command_tool_row
from pallas.core.foundation.db.modules import SingProgress
from pallas.core.shared.utils import HTTPXClient
from pallas.product.llm.knowledge.declare import knowledge_source_row
from ulid import ULID

from .config import (
    build_sing_command_prefixes,
    get_sing_config,
    sing_server_url,
    sync_sing_ingress_command_prefixes,
)
from .ncm_login import get_song_id, get_song_title

__plugin_meta__ = PluginMetadata(
    name="牛牛唱歌",
    description="群内 AI 翻唱、点歌与续唱。",
    usage=join_usage(
        usage_line("牛牛唱歌 〈歌曲名〉 [key=±N]", "AI 翻唱，可调音调"),
        usage_line("牛牛继续唱 / 牛牛接着唱", "续唱上一首"),
        usage_line("牛牛点歌 〈歌曲名〉", "播放网易云原曲"),
        usage_line("牛牛什么歌 / 牛牛哪首歌 / 牛牛啥歌", "查询当前曲目"),
    ),
    type="application",
    homepage=PLUGIN_HOMEPAGE,
    supported_adapters={"~onebot.v11"},
    extra={
        "help_tag": "fun",
        "version": PLUGIN_EXTRA_VERSION,
        "menu_template": PLUGIN_MENU_TEMPLATE,
        "ingress_route": {"lane": "remote"},
        # 启动后由 sync_sing_ingress_command_prefixes 按 sing_speakers 覆盖
        "command_prefixes": build_sing_command_prefixes({"帕拉斯": "pallas", "牛牛": "pallas"}),
        "command_permissions": [
            {
                "id": "sing.sing",
                "label": "牛牛唱歌 / 牛牛继续唱",
                "default": "everyone",
            },
            {"id": "sing.play", "label": "牛牛唱歌（随机）", "default": "everyone"},
            {"id": "sing.request_song", "label": "牛牛点歌", "default": "everyone"},
            {"id": "sing.song_title", "label": "牛牛什么歌", "default": "everyone"},
            {"id": "sing.ncm_login", "label": "网易云登录", "default": "superuser"},
            {"id": "sing.ncm_logout", "label": "网易云登出", "default": "superuser"},
        ],
        "command_limits": [
            {"id": "sing.sing", "cd_sec": 8},
            {"id": "sing.play", "cd_sec": 3},
            {"id": "sing.request_song", "cd_sec": 5},
            {"id": "sing.song_title", "cd_sec": 2},
            {"id": "sing.ncm_login", "cd_sec": 5},
            {"id": "sing.ncm_logout", "cd_sec": 5},
        ],
        "llm_tools": [
            llm_command_tool_row(
                name="sing.sing",
                command_id="sing.sing",
                description=(
                    "按歌名 AI 翻唱。用户明确要求唱歌、唱一首、翻唱、来一首、音乐翻唱时使用；与点播原曲不同。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "song": {
                            "type": "string",
                            "description": "歌曲名，尽量保留用户原话",
                        },
                    },
                    "required": ["song"],
                },
                command_template="牛牛唱歌 {song}",
                hints=["唱歌", "唱一首", "翻唱", "来一首", "来首歌", "音乐"],
            ),
            llm_command_tool_row(
                name="sing.continue",
                command_id="sing.sing",
                description="续唱上一首未完成的歌。用户说继续唱、接着唱时使用。",
                parameters={"type": "object", "properties": {}},
                command_template="牛牛继续唱",
                hints=["继续唱", "接着唱"],
            ),
            llm_command_tool_row(
                name="sing.request_song",
                command_id="sing.request_song",
                description=("点播网易云原曲。用户明确要求点歌、放歌、放首歌、听歌、播歌、牛牛音乐时使用。"),
                parameters={
                    "type": "object",
                    "properties": {
                        "song": {
                            "type": "string",
                            "description": "歌曲名，尽量保留用户原话",
                        },
                    },
                    "required": ["song"],
                },
                command_template="牛牛点歌 {song}",
                hints=[
                    "点歌",
                    "放歌",
                    "放首歌",
                    "放首",
                    "来首",
                    "听歌",
                    "播歌",
                    "播放歌曲",
                    "音乐",
                    "牛牛音乐",
                    "我想听",
                    "想听",
                    "听一下",
                    "来点音乐",
                    "想听歌",
                    "想听首",
                ],
            ),
            llm_command_tool_row(
                name="sing.song_title",
                command_id="sing.song_title",
                description="查询当前正在唱/播的歌名。用户问什么歌、哪首歌时使用。",
                parameters={"type": "object", "properties": {}},
                command_template="牛牛什么歌",
                hints=["什么歌", "哪首歌"],
            ),
        ],
        "menu_data": [
            {
                "func": "牛牛唱歌",
                "trigger_method": "on_message",
                "trigger_scene": SCENE_GROUP,
                "trigger_condition": "牛牛唱歌 歌曲名 [key=±N]",
                "command_permission": "sing.sing",
                "brief_des": "AI 翻唱指定歌曲",
                "detail_des": "按歌名搜索并翻唱，可用 key=±N 调整音调；每次会返回一段音频。",
            },
            {
                "func": "继续唱",
                "trigger_method": "on_message",
                "trigger_scene": SCENE_GROUP,
                "trigger_condition": "牛牛继续唱 / 牛牛接着唱",
                "command_permission": "sing.sing",
                "brief_des": "继续上次未完成的歌曲",
                "detail_des": "接着唱上一次没唱完的那首歌，继续返回下一段片段。",
            },
            {
                "func": "点歌",
                "trigger_method": "on_message",
                "trigger_scene": SCENE_GROUP,
                "trigger_condition": "牛牛点歌 歌曲名",
                "command_permission": "sing.request_song",
                "brief_des": "播放网易云原曲",
                "detail_des": "按歌名搜索原曲并播放；如果登录状态可用，也能点需要会员权限的歌。",
            },
            {
                "func": "牛牛什么歌",
                "trigger_method": "on_message",
                "trigger_scene": SCENE_GROUP,
                "trigger_condition": "牛牛什么歌 / 牛牛哪首歌 / 牛牛啥歌",
                "command_permission": "sing.song_title",
                "brief_des": "查询当前播放的歌曲名",
                "detail_des": "查看牛牛当前正在唱的是哪一首歌。",
            },
            {
                "func": "网易云登录",
                "trigger_method": "on_cmd",
                "trigger_scene": SCENE_PRIVATE,
                "trigger_condition": "网易云登录 / 网易云登出",
                "command_permissions": ["sing.ncm_login", "sing.ncm_logout"],
                "brief_des": "绑定或解绑网易云",
                "detail_des": "私聊按提示完成登录或登出，用于点歌和播放需要网易云登录支持的内容。",
            },
        ],
        "knowledge_sources": [
            knowledge_source_row(
                source_id="sing.faq",
                title="牛牛唱歌说明",
                description="AI 翻唱、点歌与续唱",
                chunks=[
                    {
                        "title": "AI 翻唱",
                        "content": ("发送「牛牛唱歌 歌曲名」可 AI 翻唱；可选 key=±N 调整音调（-12 到 12）。"),
                        "keywords": "唱歌,翻唱,牛牛唱歌,key,音调",
                    },
                    {
                        "title": "续唱与点歌",
                        "content": (
                            "「牛牛继续唱 / 牛牛接着唱」续唱上一首；"
                            "「牛牛点歌 歌曲名」播放网易云原曲；"
                            "「牛牛什么歌 / 牛牛哪首歌 / 牛牛啥歌」查询当前曲目。"
                        ),
                        "keywords": "继续唱,接着唱,点歌,什么歌,原曲",
                    },
                    {
                        "title": "网易云登录",
                        "content": (
                            "私聊「网易云登录 / 网易云登出」可绑定或解绑网易云账号，"
                            "用于播放需登录支持的内容（维护者向口令）。"
                        ),
                        "keywords": "网易云,登录,登出,会员",
                    },
                    {
                        "title": "与口令工具的分工",
                        "content": (
                            "闲聊中若用户要唱歌或点歌，可调用 sing.sing / sing.request_song 等工具；"
                            "效果与「牛牛唱歌 / 牛牛点歌」一致，不要编造其它入口。"
                        ),
                        "keywords": "工具,口令,唱歌,点歌",
                    },
                ],
            ),
        ],
    },
)

SING_CMD = "唱歌"
REQUEST_SONG_CMD = "点歌"
SING_CONTINUE_CMDS = {"继续唱", "接着唱"}
WHAT_SONG_CMDS = {"什么歌", "哪首歌", "啥歌"}


async def safe_finish(matcher, message: str | None = None) -> None:
    """发送收尾文案；协议拒发时降级为 warning，仍正常结束 matcher。"""
    if message is not None:
        try:
            await matcher.send(message)
        except (ActionFailed, NetworkError) as err:
            logger.warning("sing reply send failed: {}", err)
    raise FinishedException


async def guard_command_cooldown(
    matcher,
    event: GroupMessageEvent,
    command_id: str,
    *,
    speak: bool = True,
) -> bool:
    if not await is_command_cooldown_ready(event, command_id):
        if speak:
            await safe_finish(matcher, "牛牛还在回味上一首，稍等再点歌吧。")
        return False
    await refresh_command_cooldown(event, command_id)
    return True


async def sync_task_id_alias(
    local_task_id: str,
    remote_task_id: str,
    task_payload: dict,
) -> None:
    if not remote_task_id or remote_task_id == local_task_id:
        return
    logger.info(
        "sing task alias ignored request_id={} remote_task_id={} task_type={}",
        local_task_id,
        remote_task_id,
        task_payload.get("task_type", ""),
    )


def sing_debug_enabled() -> bool:
    return bool(get_sing_config().sing_rule_debug)


def log_rule_skip(
    rule_name: str,
    event: GroupMessageEvent | Event,
    reason: str,
    text: str | None = None,
) -> None:
    if not sing_debug_enabled():
        return
    logger.debug(
        "sing rule skip rule={} bot_id={} group_id={} user_id={} text={!r} reason={}",
        rule_name,
        getattr(event, "self_id", ""),
        getattr(event, "group_id", 0),
        getattr(event, "user_id", 0),
        (text or "").strip(),
        reason,
    )


def response_task_id(response) -> str:
    try:
        data = response.json() if response is not None else {}
    except Exception as e:
        logger.warning("sing response json parse failed: {}", e)
        return ""
    if not isinstance(data, dict):
        return ""
    raw = data.get("task_id")
    return str(raw).strip() if raw is not None else ""


def response_status_code(response) -> int | None:
    try:
        code = getattr(response, "status_code", None)
        return int(code) if code is not None else None
    except Exception:
        return None


async def finish_on_cooldown(matcher, event: GroupMessageEvent, command_id: str) -> bool:
    return await guard_command_cooldown(matcher, event, command_id)


async def is_to_sing(event: GroupMessageEvent, state: T_State) -> bool:
    plugin_config = get_sing_config()
    if not plugin_config.sing_enable:
        log_rule_skip("sing", event, "sing disabled")
        return False
    text = event.get_plaintext()
    if not text:
        log_rule_skip("sing", event, "empty text")
        return False

    if SING_CMD not in text and not any(cmd in text for cmd in SING_CONTINUE_CMDS):
        log_rule_skip("sing", event, "no sing keyword", text)
        return False

    if text.endswith(SING_CMD):
        log_rule_skip("sing", event, "endswith sing cmd -> play path", text)
        return False

    has_spk = False
    for name, speaker in plugin_config.sing_speakers.items():
        if not text.startswith(name):
            continue
        text = text.replace(name, "").strip()
        has_spk = True
        state["speaker"] = speaker
        break

    if not has_spk:
        log_rule_skip("sing", event, "no speaker prefix", text)
        return False

    if "key=" in text:
        key_pos = text.find("key=")
        key_val = text[key_pos + 4 :].strip()  # 获取key=后面的值
        text = text.replace("key=" + key_val, "")  # 去掉消息中的key信息
        try:
            key_int = int(key_val)  # 判断输入的key是不是整数
            if key_int < -12 or key_int > 12:
                log_rule_skip("sing", event, f"key out of range: {key_int}", text)
                return False  # 限制一下key的大小，一个八度应该够了
        except ValueError:
            log_rule_skip("sing", event, f"invalid key: {key_val}", text)
            return False
    else:
        key_val = 0
    state["key"] = key_val

    if text.startswith(SING_CMD):
        song_key = text.replace(SING_CMD, "").strip()
        if not song_key:
            log_rule_skip("sing", event, "empty song key after sing cmd", text)
            return False
        state["song_id"] = song_key
        state["chunk_index"] = 0
        return True

    if text in SING_CONTINUE_CMDS:
        progress = await GroupConfig(group_id=event.group_id).sing_progress()
        logger.info(f"bot [{event.self_id}] sing continue read progress in group [{event.group_id}]: {progress}")
        if not progress:
            log_rule_skip("sing", event, "continue without progress", text)
            return False

        song_id = str(progress.song_id)
        chunk_index = progress.chunk_index + 1
        key_val = progress.key
        if not song_id or chunk_index > 100:
            log_rule_skip(
                "sing",
                event,
                f"invalid continue progress song_id={song_id} chunk_index={chunk_index}",
                text,
            )
            return False
        state["song_id"] = song_id
        state["chunk_index"] = chunk_index
        state["key"] = key_val
        return True

    return False


sing_msg = on_message(
    rule=Rule(is_to_sing),
    priority=5,
    block=True,
    permission=group_message_permission_for_command("sing.sing"),
)


@sing_msg.handle()
async def handle_sing(bot: Bot, event: GroupMessageEvent, state: T_State):
    plugin_config = get_sing_config()
    if not await finish_on_cooldown(sing_msg, event, "sing.sing"):
        return
    config = GroupConfig(event.group_id)
    speaker = state["speaker"]
    song_id = await get_song_id(state["song_id"])
    if not song_id:
        await safe_finish(
            sing_msg,
            "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。",
        )
    key = state["key"]
    chunk_index = state["chunk_index"]
    request_id = str(ULID())
    task_payload = {
        "bot_id": bot.self_id,
        "group_id": event.group_id,
        "task_type": "sing",
        "start_time": time.time(),
    }
    await TaskManager.add_task(request_id, task_payload)

    url = f"{sing_server_url(plugin_config)}{plugin_config.sing_endpoint}/{request_id}"
    logger.info(
        "sing request dispatch mode=sing request_id={} bot_id={} group_id={} "
        "speaker={} song_id={} chunk_index={} key={} url={}",
        request_id,
        bot.self_id,
        event.group_id,
        speaker,
        song_id,
        chunk_index,
        key,
        url,
    )
    response = await HTTPXClient.post(
        url,
        json={
            "speaker": speaker,
            "song_id": song_id,
            "sing_length": plugin_config.sing_length,
            "chunk_index": chunk_index,
            "key": key,
        },
    )
    if not response:
        logger.warning(
            "sing request failed mode=sing request_id={} bot_id={} group_id={} url={}",
            request_id,
            bot.self_id,
            event.group_id,
            url,
        )
        await TaskManager.remove_task(request_id)
        await safe_finish(
            sing_msg,
            "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。",
        )
    task_id = response_task_id(response)
    logger.info(
        "sing request response mode=sing request_id={} task_id={} status_code={} bot_id={} group_id={}",
        request_id,
        task_id or "<missing>",
        response_status_code(response),
        bot.self_id,
        event.group_id,
    )
    if not task_id:
        await TaskManager.remove_task(request_id)
        await safe_finish(
            sing_msg,
            "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。",
        )
    await sync_task_id_alias(request_id, str(task_id), task_payload)

    if chunk_index == 0:
        await config.update_sing_progress(
            SingProgress(
                song_id=str(song_id),
                chunk_index=chunk_index,
                key=key,
            )
        )
    await safe_finish(sing_msg, "欢呼吧！")


async def is_play(bot: Bot, event: Event, state: T_State) -> bool:
    plugin_config = get_sing_config()
    text = event.get_plaintext()
    if not text or not text.endswith(SING_CMD):
        log_rule_skip("play", event, "not endswith sing cmd", text)
        return False

    for name, speaker in plugin_config.sing_speakers.items():
        if not text.startswith(name):
            continue
        state["speaker"] = speaker
        return True

    log_rule_skip("play", event, "no speaker prefix", text)
    return False


play_cmd = on_message(
    rule=Rule(is_play),
    permission=group_message_permission_for_command("sing.play"),
    priority=5,
    block=False,
)


@play_cmd.handle()
async def handle_play(bot: Bot, event: GroupMessageEvent, state: T_State):
    plugin_config = get_sing_config()
    if not await finish_on_cooldown(play_cmd, event, "sing.play"):
        return

    speaker = state["speaker"]
    request_id = str(ULID())
    task_payload = {
        "bot_id": bot.self_id,
        "group_id": event.group_id,
        "task_type": "play",
        "start_time": time.time(),
    }
    await TaskManager.add_task(request_id, task_payload)
    url = f"{sing_server_url(plugin_config)}{plugin_config.play_endpoint}/{request_id}"
    logger.info(
        "sing request dispatch mode=play request_id={} bot_id={} group_id={} speaker={} url={}",
        request_id,
        bot.self_id,
        event.group_id,
        speaker,
        url,
    )
    response = await HTTPXClient.post(url, json={"speaker": speaker})
    if not response:
        logger.warning(
            "sing request failed mode=play request_id={} bot_id={} group_id={} speaker={} url={}",
            request_id,
            bot.self_id,
            event.group_id,
            speaker,
            url,
        )
        await TaskManager.remove_task(request_id)
        await safe_finish(
            play_cmd,
            "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。",
        )
    task_id = response_task_id(response)
    logger.info(
        "sing request response mode=play request_id={} task_id={} status_code={} bot_id={} group_id={} speaker={}",
        request_id,
        task_id or "<missing>",
        response_status_code(response),
        bot.self_id,
        event.group_id,
        speaker,
    )
    if not task_id:
        await TaskManager.remove_task(request_id)
        await safe_finish(
            play_cmd,
            "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。",
        )
    await sync_task_id_alias(request_id, str(task_id), task_payload)
    await safe_finish(play_cmd, "欢呼吧！")


async def is_to_request_song(event: GroupMessageEvent, state: T_State) -> bool:
    plugin_config = get_sing_config()
    if not plugin_config.sing_enable:
        log_rule_skip("request", event, "sing disabled")
        return False
    text = event.get_plaintext()
    if not text:
        log_rule_skip("request", event, "empty text")
        return False

    if REQUEST_SONG_CMD not in text:
        log_rule_skip("request", event, "no request keyword", text)
        return False

    if not text.endswith(REQUEST_SONG_CMD):
        has_spk = False
        for name, speaker in plugin_config.sing_speakers.items():
            if not text.startswith(name):
                continue
            text = text.replace(name, "").strip()
            has_spk = True
            state["speaker"] = speaker
            break

        if not has_spk:
            log_rule_skip("request", event, "no speaker prefix", text)
            return False

        if text.startswith(REQUEST_SONG_CMD):
            song_name = text.replace(REQUEST_SONG_CMD, "").strip()
            if not song_name:
                log_rule_skip("request", event, "empty song name", text)
                return False
            state["song_name"] = song_name
            return True

    log_rule_skip("request", event, "request pattern not matched", text)
    return False


request_song_msg = on_message(
    rule=Rule(is_to_request_song),
    priority=5,
    block=True,
    permission=group_message_permission_for_command("sing.request_song"),
)


@request_song_msg.handle()
async def handle_request_song(bot: Bot, event: GroupMessageEvent, state: T_State):
    plugin_config = get_sing_config()
    if not await finish_on_cooldown(request_song_msg, event, "sing.request_song"):
        return

    song_name = state["song_name"]

    song_id = await get_song_id(song_name)
    if not song_id:
        return False

    request_id = str(ULID())
    url = f"{sing_server_url(plugin_config)}{plugin_config.request_endpoint}/{request_id}"
    logger.info(
        "sing request dispatch mode=request request_id={} bot_id={} group_id={} song_name={} song_id={} url={}",
        request_id,
        bot.self_id,
        event.group_id,
        song_name,
        song_id,
        url,
    )

    response = await HTTPXClient.post(
        url,
        json={
            "song_id": song_id,
        },
    )
    task_payload = {
        "bot_id": bot.self_id,
        "group_id": event.group_id,
        "task_type": "request",
        "start_time": time.time(),
    }
    await TaskManager.add_task(request_id, task_payload)

    if not response:
        logger.warning(
            "sing request failed mode=request request_id={} bot_id={} group_id={} song_id={} url={}",
            request_id,
            bot.self_id,
            event.group_id,
            song_id,
            url,
        )
        await TaskManager.remove_task(request_id)
        await safe_finish(
            request_song_msg,
            "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。",
        )
    task_id = response_task_id(response)
    logger.info(
        "sing request response mode=request request_id={} task_id={} status_code={} bot_id={} group_id={} song_id={}",
        request_id,
        task_id or "<missing>",
        response_status_code(response),
        bot.self_id,
        event.group_id,
        song_id,
    )
    if not task_id:
        await TaskManager.remove_task(request_id)
        await safe_finish(
            request_song_msg,
            "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。",
        )
    await sync_task_id_alias(request_id, str(task_id), task_payload)

    await GroupConfig(event.group_id).update_sing_progress(
        SingProgress(
            song_id=str(song_id),
            chunk_index=0,
            key=0,
        )
    )
    await safe_finish(request_song_msg, "欢呼吧！")


async def what_song(event: Event) -> bool:
    text = event.get_plaintext()
    speakers = get_sing_config().sing_speakers.keys()
    return any(text.startswith(spk) for spk in speakers) and any(key in text for key in WHAT_SONG_CMDS)


song_title_cmd = on_message(
    rule=Rule(what_song),
    priority=12,
    block=True,
    permission=group_message_permission_for_command("sing.song_title"),
)


@song_title_cmd.handle()
async def _(event: GroupMessageEvent):
    config = GroupConfig(event.group_id)
    progress = await config.sing_progress()
    logger.info(f"bot [{event.self_id}] sing song title query in group [{event.group_id}]: {progress}")

    if not progress:
        return
    if not await guard_command_cooldown(song_title_cmd, event, "sing.song_title", speak=False):
        return
    song_title = await get_song_title(progress.song_id)
    if not song_title:
        return

    await safe_finish(song_title_cmd, f"{song_title}")


# 按当前音频映射展开 ingress 前缀（否则自定义前缀进不了唱歌 matcher）
sync_sing_ingress_command_prefixes(get_sing_config().sing_speakers, meta=__plugin_meta__)
