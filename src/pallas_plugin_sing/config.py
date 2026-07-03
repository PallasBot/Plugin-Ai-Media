from pydantic import BaseModel, Field

from pallas.api.config import field_help, install_hot_reload_config


class Config(BaseModel, extra="ignore"):
    ai_server_host: str = Field(
        default="127.0.0.1",
        description=field_help(
            "点歌/唱歌服务所在机器的地址",
            "本机填 127.0.0.1；服务在别的机器上填其 IP 或域名",
        ),
    )
    ai_server_port: int = Field(
        default=9099,
        description=field_help(
            "点歌/唱歌服务监听的端口",
            "填整数，需与后端实际监听端口一致",
        ),
    )
    sing_enable: bool = Field(
        default=False,
        description=field_help(
            "是否启用唱歌与播放相关命令",
            "开启前请确认后端服务已部署且地址正确",
        ),
    )
    sing_endpoint: str = Field(
        default="/api/sing",
        description=field_help(
            "提交合成任务的接口路径",
            "以 / 开头的路径，会拼在「主机:端口」后面",
            "legacy 模式使用；media_task 模式改走 /api/media/tasks",
        ),
    )
    sing_runtime_mode: str = Field(
        default="legacy",
        description=field_help(
            "唱歌任务提交模式",
            "legacy 直连 /api/sing；media_task 走 AI 仓统一媒体任务 API",
        ),
    )
    play_endpoint: str = Field(
        default="/api/play",
        description=field_help(
            "触发播放任务的接口路径",
            "将以 POST /{request_id} 形式调用，并在 body 中传 speaker",
            "以 / 开头；留空或错误会导致播放失败",
        ),
    )
    request_endpoint: str = Field(
        default="/api/request",
        description=field_help(
            "唱歌排队请求的接口路径",
            "通用配置页「服务网关」主要使用此项做连通检测",
        ),
    )
    sing_length: int = Field(
        default=120, description="单次合成音频的默认最大时长（秒），具体以后端为准。"
    )
    sing_speakers: dict[str, str] = Field(
        default_factory=lambda: {
            "帕拉斯": "pallas",
            "牛牛": "pallas",
        },
        description="唱歌的音色映射",
    )
    sing_rule_debug: bool = Field(
        default=False,
        description=field_help(
            "是否在日志中输出每条消息的 rule 匹配跳过原因",
            "仅排障时开启；群消息量大时 INFO 级刷屏会拖慢 worker",
        ),
    )


def on_sing_config_reload(cfg: Config) -> None:
    from packages.help.plugin_availability import (
        invalidate_plugin_help_availability_cache,
    )

    invalidate_plugin_help_availability_cache()


plugin_webui = install_hot_reload_config(
    Config, config_module=__name__, on_reload=on_sing_config_reload
)
get_sing_config = plugin_webui.get
reload_sing_config = plugin_webui.reload
clear_sing_config_cache = plugin_webui.clear_cache


def sing_server_url(cfg: Config | None = None) -> str:
    c = cfg or get_sing_config()
    return f"http://{c.ai_server_host}:{c.ai_server_port}"


def sing_runtime_mode(cfg: Config | None = None) -> str:
    c = cfg or get_sing_config()
    raw = (c.sing_runtime_mode or "legacy").strip().lower()
    return "media_task" if raw == "media_task" else "legacy"
