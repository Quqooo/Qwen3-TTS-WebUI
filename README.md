**简中** | [English](README_EN.md)

# Qwen3-TTS WebUI

> [!Warning]
>
> ** Vibe Coding 项目**

基于 **FastAPI + Vue 3** 的 Qwen3-TTS 全功能 Web 界面，替代原始 Gradio Demo，提供声音克隆、预设音色合成、自然语言声音设计、批量处理等能力。设计为受信任的本地工具，不适用于公共网络暴露。

---

## 功能特性

- **三种合成模式**
  - **基础（Base）** — 上传参考音频进行声音克隆，支持声纹（x-vector）模式
  - **预设音色（CustomVoice）** — 使用预训练说话人音色（Serena、Vivian 等）
  - **声音设计（VoiceDesign）** — 用自然语言描述生成声音（如 "温柔的女声"）
- **流式播放** — 支持实时 PCM 流式生成与边下边播
- **批量处理** — 表格化多任务编辑、时间轴对齐、SRT 字幕导入/生成、ZIP 备份导出
- **音色管理** — 音色文件 CRUD、预览、编辑
- **模型热管理** — 多模型并发控制、LRU 淘汰、空闲自动卸载
- **多后端分支** — 支持 3 种 Qwen3-TTS 实现（[QwenLM](https://github.com/QwenLM/Qwen3-TTS) / [streaming](https://github.com/rekuenkdr/Qwen3-TTS-streaming) / [faster](https://github.com/andimarafioti/faster-qwen3-tts)）

---

## 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.10+ |
| Node.js | 18+ |
| 包管理 | pnpm |
| ffmpeg | 可选，用于 MP3 / Opus / AAC 格式转换 |

---

## 快速开始

**Linux / macOS：**

```bash
chmod +x start.sh
./start.sh
```

**Windows：**

```bat
start.bat
```

### 手动启动

**后端：**

```bash
# 安装 Web 后端依赖
pip install -e .

# 启动服务
uvicorn backend.main:app --port 8000 --host localhost
```

**前端（开发模式）：**

```bash
cd frontend
pnpm install
pnpm dev
```

前端开发服务器默认监听 `http://localhost:5173`，API 请求自动代理至后端 8000 端口。

**前端（生产构建）：**

```bash
cd frontend
pnpm install
pnpm build
```

构建产物输出至 `backend/static/`，由 FastAPI 直接托管。

---

## 配置

编辑 `backend/settings.json`：

```json
{
  "max_concurrent_models": 1,
  "idle_unload_seconds": 600,
  "backend_branch": "andimarafioti/faster-qwen3-tts",
  "project_dir": "",
  "env_dir": "",
  "model_dir": "",
  "voice_dir": "",
  "max_seq_len": 2048,
  "batch_composer": {
    "max_segments": 1000,
    "max_output_samples": 100000000,
    "max_decoded_samples": 100000000,
    "max_total_decoded_samples": 100000000,
    "max_time_stretch_rate": 16.0,
    "max_audio_mib": 32,
    "max_total_audio_mib": 256,
    "min_sample_rate": 8000,
    "max_sample_rate": 192000
  }
}
```

| 字段 | 说明 |
|------|------|
| `max_concurrent_models` | 同时加载的最大模型数 |
| `idle_unload_seconds` | 空闲模型自动卸载时间（秒） |
| `backend_branch` | 后端分支（见下方可选值） |
| `project_dir` | Qwen3-TTS 项目目录 |
| `env_dir` | Qwen3-TTS 的 Python 虚拟环境路径 |
| `model_dir` | 模型权重目录 |
| `voice_dir` | 音色文件存储目录 |
| `max_seq_len` | Faster 分支静态 KV Cache 最大序列长度 |
| `batch_composer` | 批量音频合成限制（见下方子字段） |

`batch_composer` 子字段：

| 子字段 | 默认值 | 说明 |
|--------|--------|------|
| `max_segments` | 1000 | 单次合成允许的最大音频段数 |
| `max_output_samples` | 100000000 | 最终输出音频的最大采样点数 |
| `max_decoded_samples` | 100000000 | 单段音频解码后最大采样点数 |
| `max_total_decoded_samples` | 100000000 | 所有段解码后累计最大采样点数 |
| `max_time_stretch_rate` | 16.0 | 变速最大倍率（1/16 ~ 16x） |
| `max_audio_mib` | 32 | 单段音频 base64 编码后的最大体积（MiB） |
| `max_total_audio_mib` | 256 | 所有段 base64 编码后的累计最大体积（MiB） |
| `min_sample_rate` | 8000 | 允许的最低输出采样率（Hz） |
| `max_sample_rate` | 192000 | 允许的最高输出采样率（Hz） |

**可选后端分支：**

| 分支 ID | 特点 |
|---------|------|
| `QwenLM/Qwen3-TTS` | 官方实现 |
| `dffdeeq/Qwen3-TTS-streaming` | 社区流式优化（torch.compile） |
| `andimarafioti/faster-qwen3-tts` | CUDA Graph 6-10x 推理加速 |

---

## 技术架构

```
浏览器 (Vue 3 SPA)
    │
    ▼ HTTP/WebSocket
FastAPI Web Server (轻量，不加载 PyTorch)
    │
    ▼ TCP (length-prefixed JSON)
Worker 子进程 (加载 Qwen3-TTS 模型，处理 GPU 推理)
```

- **进程隔离** — Web 服务器和模型推理运行在不同进程中，Web 进程不导入 PyTorch，实现依赖分离
- **插件化分支** — `branches/` 目录通过动态扫描加载
- **统一 Worker** — 所有分支共用同一套 Worker TCP 协议，通过 `worker_provider.py` 插件适配
- **WebSocket 推送** — 模型缓存状态、Worker 状态、推理计数实时同步至前端