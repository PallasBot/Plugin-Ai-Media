from nonebot import get_driver, logger
from nonebot.plugin import PluginMetadata
from pallas.api.commands import (
    bind_alias_handlers,
    command_limit_list,
    command_limit_row,
    command_perm_list,
    command_perm_row,
    message_command,
)
from pallas.api.logging import format_plugin_event
from pallas.api.metadata import (
    PLUGIN_EXTRA_VERSION,
    PLUGIN_HOMEPAGE,
    PLUGIN_MENU_TEMPLATE,
    SCENE_GROUP,
    join_usage,
    usage_line,
)
from pallas.api.platform import llm_command_tool_row
from pallas.product.llm.knowledge.declare import knowledge_source_row

from . import config as _config  # noqa: F401
from . import direct as _direct  # noqa: F401
from . import media_callback as _tts_media_callback  # noqa: F401
from .handlers import handle_speak


@get_driver().on_startup
async def _tts_ready() -> None:
    logger.info(format_plugin_event("ready", "Registered tts command and media task hooks"))


PLUGIN_ID = "tts"

__plugin_meta__ = PluginMetadata(
    name="牛牛说",
    description="把文字念成语音发出去。",
    usage=join_usage(
        usage_line("牛牛说 〈文本〉", "侧车 TTS 合成语音"),
    ),
    type="application",
    homepage=PLUGIN_HOMEPAGE,
    supported_adapters={"~onebot.v11"},
    extra={
        "help_tag": "fun",
        "version": PLUGIN_EXTRA_VERSION,
        "menu_template": PLUGIN_MENU_TEMPLATE,
        "ingress_route": {"lane": "remote"},
        "command_prefixes": ["牛牛说"],
        "command_permissions": command_perm_list(
            command_perm_row(f"{PLUGIN_ID}.speak", "牛牛说", "everyone"),
        ),
        "command_limits": command_limit_list(
            command_limit_row(f"{PLUGIN_ID}.speak", 5),
        ),
        "llm_tools": [
            llm_command_tool_row(
                name="tts.speak",
                command_id=f"{PLUGIN_ID}.speak",
                description="把指定文字念成语音发出去。用户明确要求念、说、读出来、语音播报时使用。",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": (
                                "要念出的正文。用户要念「上一句/你的话/引用内容」时，"
                                "填被回复或上下文中的原文，不要另编一句"
                            ),
                        },
                    },
                    "required": ["text"],
                },
                command_template="牛牛说 {text}",
                hints=[
                    "念一下",
                    "念出来",
                    "念一遍",
                    "读出来",
                    "读一下",
                    "语音播报",
                    "说出来",
                    "把你的话",
                    "牛牛说",
                ],
            ),
        ],
        "menu_data": [
            {
                "func": "牛牛说",
                "trigger_method": "on_command",
                "trigger_scene": SCENE_GROUP,
                "trigger_condition": "牛牛说 〈文本〉",
                "command_permission": f"{PLUGIN_ID}.speak",
                "brief_des": "文字转语音",
                "detail_des": (
                    "「牛牛说」后须加空格再跟正文。依赖 AI Runtime TTS；"
                    "酒后对话自动附带语音见智能对话配置，与本命令独立。"
                ),
            },
        ],
        "knowledge_sources": [
            knowledge_source_row(
                source_id="tts.faq",
                title="牛牛说说明",
                description="文字转语音口令",
                chunks=[
                    {
                        "title": "牛牛说",
                        "content": (
                            "发送「牛牛说 内容」（中间有空格）可将文字合成语音发出；"
                            "需安装 pallas-plugin-ai-media 并启用 TTS，配置侧车 AI Runtime。"
                            "酒后对话是否自动跟语音由智能对话里的「酒后附带语音」配置决定。"
                        ),
                        "keywords": "牛牛说,TTS,语音,念,读出来,念出来",
                    },
                ],
            ),
        ],
    },
)

speak_cmd = message_command(
    f"{PLUGIN_ID}.speak",
    "牛牛说",
    scene="group",
    cd_sec=5,
    priority=5,
    block=True,
)

bind_alias_handlers(speak_cmd, handle_speak)
