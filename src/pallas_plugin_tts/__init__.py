from nonebot.plugin import PluginMetadata
from pallas.api.commands import (
    bind_alias_handlers,
    command_limit_list,
    command_limit_row,
    command_perm_list,
    command_perm_row,
    message_command,
)
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
from .handlers import handle_speak

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
                            "description": "要念出的正文，尽量保留用户原话",
                        },
                    },
                    "required": ["text"],
                },
                command_template="牛牛说 {text}",
                hints=["念一下", "读出来", "语音播报", "说出来", "牛牛说"],
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
                "detail_des": "依赖 AI Runtime TTS；在插件页配置侧车地址与通路。",
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
                            "发送「牛牛说 内容」可将文字合成语音发出；"
                            "需安装 pallas-plugin-ai-media 并启用 TTS，配置侧车 AI Runtime。"
                        ),
                        "keywords": "牛牛说,TTS,语音,念,读出来",
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
