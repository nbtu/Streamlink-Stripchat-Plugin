# Streamlink Stripchat Plugin

一个用于 [Streamlink](https://streamlink.github.io/) 的 Stripchat 播放插件，支持解析 Stripchat 直播间以及 DoppioCDN HLS 直链，并针对 Mouflon v1/v2 播放列表进行处理。

> **适配版本：Streamlink 8.x**
> 更新日期：2026-08-25

最先发布在：[telegraph](https://telegra.ph/%E5%8F%AF%E5%BD%95%E5%88%B6stripchat%E7%9A%84streamlink%E6%8F%92%E4%BB%B6-11-25)

## ✨ Features

* 支持 Stripchat 直播间 URL
* 支持 DoppioCDN `.m3u8` 直链
* 支持 HLS Master Playlist / Variant Playlist
* 支持 Mouflon v1 播放列表
* 支持 Mouflon v2 播放列表
* 自动识别 Mouflon 版本
* 自动提取 Playlist 中的 `pkey`
* 支持从 HLS URL 参数中读取 `pkey`
* 对未知 `pkey` 提供白名单兜底机制
* 支持多码率自动解析
* 与 Streamlink 的 HLS 播放流程集成

## 📦 Installation

将 `stripchat.py` 放入 Streamlink 的插件目录。

例如：

```text
plugins/
└── stripchat.py
```

然后使用 Streamlink：

```bash
streamlink "https://stripchat.com/USERNAME" best
```

如果使用的是 DoppioCDN HLS 直链：

```bash
streamlink "https://edge-hls.doppiocdn.com/..." best
```

具体插件目录位置取决于你的 Streamlink 安装方式和操作系统。

## 🎥 Usage

### Stripchat 直播间

```bash
streamlink "https://stripchat.com/USERNAME" best
```

也可以选择指定画质：

```bash
streamlink "https://stripchat.com/USERNAME" 720p
```

查看当前可用画质：

```bash
streamlink "https://stripchat.com/USERNAME"
```

### DoppioCDN HLS 直链

插件同时支持包含 `.m3u8` 的 DoppioCDN HLS URL：

```bash
streamlink "https://edge-hls.doppiocdn.com/..." best
```

如果 URL 对应的是 Master Playlist，插件会自动解析其中的 Variant Playlist，并分别检测对应的 Mouflon 加密类型。

## 🔐 Mouflon v1 / v2

插件内部包含两套 Playlist 处理逻辑。

### Mouflon v1

v1 主要处理：

```text
#EXT-X-MOUFLON:PSCH:v1:<pkey>
```

以及：

```text
#EXT-X-MOUFLON:FILE:<encrypted>
```

插件会根据 Playlist 中的 `pkey` 选择对应的密钥，然后对加密内容进行处理，再交给 Streamlink 的 HLS 播放流程。

### Mouflon v2

v2 主要处理：

```text
#EXT-X-MOUFLON:PSCH:v2:<pkey>
```

以及：

```text
#EXT-X-MOUFLON:URI:<encrypted-uri>
```

v2 解密流程会对 Token 进行反转、Base64 解码以及基于 SHA-256 派生密钥的 XOR 处理。

## 🔑 PKEY White-list

插件使用 `KEY_MAP` 对已知 `pkey` 进行映射。

当 Playlist 或 URL 中出现未知 `pkey` 时，插件不会直接使用未知值，而是进入 fallback 流程。

当前 v2 fallback：

```text
Fq6m2TO2ZeBkRPm9
```

这样可以避免部分直链、Master Playlist、Variant Playlist 在不同链路中出现 `pkey` 不一致时导致插件无法继续解析。

## 🔄 Processing Flow

Stripchat 直播间模式的大致流程：

```text
Stripchat URL
     │
     ▼
获取 Model/User ID
     │
     ▼
查询 Cam 状态
     │
     ├── Offline ──► 返回无可用流
     │
     ▼
获取 DoppioCDN Master Playlist
     │
     ▼
检测 Mouflon / PKEY
     │
     ▼
解析 Variant Playlists
     │
     ├── Mouflon v1 ──► DecryptHLSStream
     │
     └── Mouflon v2 ──► DecryptHLSStreamV2
     │
     ▼
Streamlink HLS
```

直链模式：

```text
DoppioCDN URL
     │
     ▼
检查 / 修正 pkey
     │
     ▼
读取 M3U8
     │
     ├── Master Playlist
     │       │
     │       └──► 解析子码率
     │
     ├── Mouflon v2
     │       │
     │       └──► v2 Playlist Worker
     │
     └── Mouflon v1 / 普通 HLS
             │
             └──► v1 Playlist Worker
```

## 🛠 Debug

如果遇到播放失败，可以开启 Streamlink Debug 日志：

```bash
streamlink --loglevel debug "https://stripchat.com/USERNAME" best
```

重点关注：

```text
[plugin]
[v1]
[v2]
```

相关日志。

例如：

```text
[plugin] 主播在线
[plugin] 码率 720p 匹配为 v2 解密
[v2] Token解密
[v2] 最终 URI
```

如果出现：

```text
检测到未知 pkey
```

说明当前 Playlist 使用了插件白名单之外的 `pkey`，插件会尝试使用 v2 fallback。

## ⚠️ Compatibility

本插件针对：

* Streamlink 8.x
* Python 3.10+
* HLS
* Stripchat
* DoppioCDN
* Mouflon v1 / v2

进行设计。

由于 Stripchat / CDN 的 API、Playlist 格式、鉴权方式以及加密参数可能随时变化，因此插件可能需要随着上游服务更新而调整。

## 📝 Notes

本项目本质上是一个 Streamlink 播放插件，负责将特定格式的 HLS Playlist 转换为 Streamlink 可以处理的标准播放列表。

插件不会提供直播内容本身，也不会托管任何视频或媒体文件。

部分 API、CDN URL、Playlist 格式以及相关参数均属于第三方服务实现，未来可能发生变化。

## ⚖️ Disclaimer

本项目仅供技术研究、软件开发以及 Streamlink 插件开发学习使用。

请遵守所在地法律法规以及相关网站的 Terms of Service。

使用本插件访问第三方内容时，请确保你拥有相应的访问权限。

作者不对因使用本项目造成的任何直接或间接损失负责。

## 📄 License

* MIT


---

## ⭐ Star / Issues

如果插件对你有帮助，欢迎 Star。

如果遇到 Playlist 格式变化或兼容性问题，可以提交 Issue，并附上：

```text
Streamlink version:
Python version:
OS:
URL type: Stripchat / DoppioCDN
Mouflon version: v1 / v2 / unknown
Error log:
```

**请不要在 Issue 中提交账号密码、Cookie、Token 或其他私人信息。**
