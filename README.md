<p align="center">
  <img src="./assets/brand-avatar.png" width="220" height="220" alt="牛牛唱歌">
</p>

<h1 align="center">牛牛唱歌 pallas-plugin-ai-media</h1>

<p align="center">提供牛牛唱歌能力（翻唱 / 点歌），依赖 Pallas-Bot-AI 媒体服务。</p>

<p align="center">
  <img alt="官方插件" src="https://img.shields.io/badge/%E5%AE%98%E6%96%B9%E6%8F%92%E4%BB%B6-FE7D37">
  <img alt="控制台插件商店" src="https://img.shields.io/badge/%E6%8E%A7%E5%88%B6%E5%8F%B0-%E6%8F%92%E4%BB%B6%E5%95%86%E5%BA%97-4EA94B">
  <img alt="安装命令" src="https://img.shields.io/badge/uv%20run%20pallas%20ext%20install%20pallas--plugin--ai--media-586069">
  <img alt="PyPI 版本" src="https://img.shields.io/pypi/v/pallas-plugin-ai-media?label=%E7%89%88%E6%9C%AC&color=2563EB">
</p>

## 安装方式

需已安装 [Pallas-Bot](https://github.com/PallasBot/Pallas-Bot) **≥ 4.0**，并部署 [Pallas-Bot-AI](https://github.com/PallasBot/Pallas-Bot-AI)。

推荐直接在控制台插件商店安装，或在本体项目中执行：

```bash
uv run pallas ext install pallas-plugin-ai-media
```

也可单独安装本包：

```bash
uv pip install pallas-plugin-ai-media
```

> 酒后对话已由本体 `llm_chat` 承接（含可选 AI 仓 TTS）。本包自 4.1.0 起不再包含 `chat` 子插件。

## 怎么使用

### 牛牛唱歌（sing）

AI 翻唱、续唱、点歌与查歌名；依赖 AI 仓与本体 `callback` 回传音频。

| 口令 / 触发 | 场景 | 说明 |
| --- | --- | --- |
| `牛牛唱歌 歌曲名 [key=±N]` | 群内 | AI 翻唱 |
| `牛牛继续唱` / `牛牛接着唱` | 群内 | 续唱上一首 |
| `牛牛点歌 歌曲名` | 群内 | 网易云原曲 |
| `牛牛什么歌` / `牛牛哪首歌` | 群内 | 查询当前曲目 |
| `网易云登录` / `网易云登出` | 私聊 | 超管维护 Cookie |

| 命令 ID | 默认等级 |
| --- | --- |
| `sing.ncm_login` | 仅超管 |
| `sing.ncm_logout` | 仅超管 |

> 详细用法、限制条件和可用范围以帮助为主。

## 配置项

> 可在控制台对应插件页中修改。

唱歌配置见 [`src/pallas_plugin_sing/config.py`](src/pallas_plugin_sing/config.py)。

## 排障

| 现象 | 处理 |
| --- | --- |
| 唱歌无语音 | 查 AI 服务、`/callback` 可达；**牛牛连通** 测唱歌网关 |

## 实现

源码位置：[`src/pallas_plugin_sing/`](src/pallas_plugin_sing/)

## 相关链接

| 说明 | 链接 |
| --- | --- |
| 唱歌 | [文档站 · sing](https://PallasBot.github.io/Pallas-Bot-Docs/plugins/sing) |
| 智能对话 / 酒后 | [文档站 · llm_chat](https://PallasBot.github.io/Pallas-Bot-Docs/plugins/llm_chat) |
| Pallas-Bot-AI | [GitHub](https://github.com/PallasBot/Pallas-Bot-AI) |
