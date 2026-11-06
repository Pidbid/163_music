<div align="center">

# 🎵 163-music

**非官方网易云音乐网页版 Ubuntu 桌面封装**

把官方网页播放器装进一个无边框、带系统托盘、支持 MPRIS 和桌面歌词的第三方网易云音乐客户端。

[![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420?logo=ubuntu&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](#)
[![pywebview](https://img.shields.io/badge/pywebview-6.x-4B8BBE)](#)
[![License](https://img.shields.io/badge/License-MIT-22C55E)](#)
[![CI](https://github.com/Pidbid/163_music/actions/workflows/ci.yml/badge.svg)](https://github.com/Pidbid/163_music/actions/workflows/ci.yml)

</div>

> [!WARNING]
> 本项目与网易云音乐、网易公司无任何关联。
>
> 它只封装官方在线页面，**不提供也不支持任何破解音乐的功能**：不下载歌曲、不去广告、不绕过
> VIP、不破解版权或 DRM。页面里能播放什么，取决于网易云音乐官方页面和当前账号权限。

## 📸 界面

| 主窗口 | 桌面歌词 |
| :---: | :---: |
| ![主窗口](docs/screenshot-main.png) | ![桌面歌词](docs/screenshot-lyrics.png) |


## ✨ 功能

| 功能 | 说明 |
| --- | --- |
| 🪟 无边框窗口 | 标题栏拖动、双击最大化、四边四角缩放、最小化、最大化/还原、关闭到托盘 |
| 🎨 主题跟随 | 每秒采样页面顶部实际颜色，侧栏与主区域边界精确过渡；文字与按钮按对比度自动取深/浅色 |
| 🧹 干净页面 | 隐藏网页自带的左上角 logo 和标题，下方导航自动上移；标题栏保留本项目图标和文字 |
| 📌 系统托盘 | 显示/隐藏、当前歌曲（标题前 8 字）、上一曲、播放/暂停、下一曲、桌面歌词、退出 |
| 🎧 MPRIS | Ubuntu/GNOME 媒体控制、锁屏信息、媒体键；播放/暂停、上一曲、下一曲、Raise/Quit |
| 💬 桌面歌词 | 置顶透明歌词窗；悬停显示上一曲、暂停/播放、下一曲、固定位置、置顶 |
| 🔐 登录持久化 | QtWebEngine 独立 profile，页面内扫码登录；不读取/共享 Chrome cookie |
| 🔊 后台播放 | 关闭到托盘后音频继续，后台定时器节流已关闭 |
| 🖥️ 系统集成 | Ubuntu 音频输出、媒体键、托盘菜单；`apt install` 即用 |

## 📦 安装

首要产物是 DEB，提供 Ubuntu amd64 与 arm64（aarch64）构建：

```bash
# amd64
sudo apt install ./163-music_0.1.0_amd64.deb

# arm64 / aarch64
sudo apt install ./163-music_0.1.0_arm64.deb
```

启动方式：

```bash
163-music
```

或从应用菜单打开“网易云音乐”。

> [!NOTE]
> 托盘依赖 StatusNotifierItem / AppIndicator。Ubuntu GNOME 默认启用 “Ubuntu AppIndicators”；
> 没有托盘时关闭按钮会直接退出。
>
> 音频输出走 PipeWire/PulseAudio。若个别歌曲无声，安装 GStreamer 插件：
>
> ```bash
> sudo apt install gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
>   gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
> ```

## 🕹️ 使用说明

- 窗口顶部是应用标题栏：左侧为本项目图标和名称，右侧是最小化、最大化/还原、关闭到托盘。
- 拖动标题栏移动窗口；双击标题栏最大化/还原；从任意一条边或角拖拽缩放。
- 关闭窗口或点击关闭按钮会隐藏到托盘，音频继续播放；真正退出请使用托盘菜单“退出”。
- 托盘当前歌曲项只显示标题前 8 个字符，避免长标题把菜单撑宽；完整歌曲/歌手在托盘 tooltip 中。
- 桌面歌词开启后，鼠标悬停歌词窗口会显示五个图标：上一曲、暂停/播放、下一曲、固定位置、置顶。
- 媒体键由 MPRIS 接管：播放/暂停、上一曲、下一曲；GNOME 快捷设置/锁屏会显示当前歌曲。

## 🎤 桌面歌词说明

- 歌词来自网易云音乐公开的 `api/song/lyric` 接口；无歌词、纯音乐、接口不可用或歌曲 ID 读取
  失败时，歌词窗自动隐藏。
- 进度来自页面自己的进度条百分比，精度约 1 秒；不读取音频采样，也不修改页面播放器。
- 支持“固定位置”（锁定后不能拖动）和“置顶”开关；置顶默认开启。
- Wayland 下顶层窗口初始位置由合成器决定，无法保证精确摆放；窗口本身可拖拽，X11 下位置记忆
  正常。
- 页面 DOM/React 内部结构变化可能导致当前歌曲或进度读取失败；此时其他功能仍可用。

## 🚀 从源码运行

需要 Python 3.12 + [uv](https://docs.astral.sh/uv/)：

```bash
uv sync
uv run python main.py --debug
```

调试模式开启 QtWebEngine 远程调试（默认 `9229`），可连接 `http://127.0.0.1:9229`。
无托盘模式：

```bash
uv run python main.py --no-tray
```

## 🧪 测试与检查

```bash
uv run pytest
uv run ruff check .
```

测试覆盖 LRC 歌词解析/定位、播放状态归一化、单实例锁与本地命令 socket、托盘短标题。
窗口、托盘、MPRIS、主题采样、桌面歌词属于 Qt/网页 UI，需在 Ubuntu 图形会话中按“使用说明”
手动验证。

## 🛠️ 构建 DEB

```bash
./build_linux.sh
```

脚本使用 Nuitka onefile 编译 `main.py`，产物为 `dist/163-music`，再组装
`dist/163-music_<version>_<arch>.deb`。只重新打包已有二进制：

```bash
./build_linux.sh --deb-only
```

构建需要 `uv`、`dpkg-deb`、`desktop-file-validate`、C/C++ 工具链。

其他平台/格式：

```bat
:: Windows x64（Nuitka onefile）
build_windows.bat
```

```bash
# macOS（Nuitka app bundle，生成 dist/163-music-macos.zip）
./build_macos.sh

# AppImage（先执行 ./build_linux.sh 生成 dist/163-music）
APPIMAGETOOL=/path/to/appimagetool ./scripts/build_appimage.sh
```

产物：

- `dist/163-music`
- `dist/163-music_<version>_<arch>.deb`（amd64 / arm64）
- `dist/nuitka-windows/163-music.exe`（Windows）
- `dist/163-music-macos.zip`（macOS .app）
- `dist/163-music-<version>-x86_64.AppImage`（Linux）

## 🔄 持续集成

GitHub Actions 工作流位于 `.github/workflows/ci.yml`，覆盖五个目标：

| Job | 运行环境 | 产物 |
| --- | --- | --- |
| `linux` | Ubuntu 22.04 amd64 | `163-music_<version>_amd64.deb` |
| `linux-arm64` | Ubuntu 24.04 arm64 | `163-music_<version>_arm64.deb` |
| `appimage` | Ubuntu 22.04 x86_64 | `163-music-<version>-x86_64.AppImage` |
| `windows` | windows-latest x64 | `163-music.exe`（Nuitka onefile） |
| `macos` | macos-latest arm64 | `163-music-macos.zip`（Nuitka app bundle） |

每次 push / PR 会先跑 `ruff` 和 `pytest`，然后构建对应平台产物。arm64、Windows/macOS
目前是 CI 构建目标，主要交互仍以 Ubuntu amd64 版本为准。

## 🗂️ 项目结构

```text
main.py                 入口、单实例、托盘/网页进程编排
nm_shell/
  webview_app.py        pywebview 窗口、页面注入、播放状态与歌词抓取
  window_api.py         网页到 Python 的窗口/播放桥
  window_manager.py     Qt 窗口几何、系统拖动/缩放
  tray.py               系统托盘、桌面歌词窗口、Qt 事件循环
  mpris.py              dbus-next MPRIS 服务
  player.py             播放状态归一化
  lyrics.py             LRC 解析、歌词接口与缓存
  paths.py              XDG 路径与打包资源路径
  single_instance.py    单实例锁与 Unix socket 通知
ui/chrome.js            注入页面的标题栏、拖拽/缩放、播放状态与主题采样
assets/                 NetEase 图标（非官方引用）
docs/                   README 截图
tests/                  pytest 测试
build_linux.sh          Nuitka + DEB 构建
```

## ⚠️ 已知限制

- 运行时以 Ubuntu amd64 为主；arm64/Windows/macOS 有 CI 构建产物，但未做完整交互验证。
- QtWebEngine 的 profile 与系统 Chrome 独立，不能共享登录状态。
- 页面顶部颜色采样针对纯色和 CSS 渐变背景；位图自定义皮肤只能近似匹配。
- 网页是第三方在线页面，页面结构、接口和可用歌曲可能随时变化；不保证长期兼容。
- 桌面歌词在 Wayland 下的位置和层级受合成器策略影响。
- 截图中的账号/歌单区域已做隐私遮挡；实际界面以你的账号为准。

## 📄 许可

本项目代码使用 MIT 许可，见 [LICENSE](LICENSE)。该许可不覆盖网易云音乐的名称、图标、商标、
页面内容、歌词或音乐版权。
