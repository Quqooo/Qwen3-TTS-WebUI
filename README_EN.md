[简中](README.md) | **English**

# Qwen3-TTS WebUI

> [!Warning]
>
> Vibe Coding Project

A full-featured web interface for Qwen3-TTS built with **FastAPI + Vue 3**, replacing the original Gradio demo. Provides voice cloning, preset voice synthesis, natural language voice design, batch processing, and more. Designed as a trusted local tool, not intended for public network exposure.

---

## Features

- **Three Synthesis Modes**
  - **Base** — Upload a reference audio for voice cloning, with x-vector mode support
  - **CustomVoice** — Use pre-trained speaker voices (Serena, Vivian, etc.)
  - **VoiceDesign** — Describe a voice in natural language (e.g. "a gentle female voice")
- **Streaming Playback** — Real-time PCM streaming generation with progressive playback
- **Batch Processing** — Tabular multi-task editing, timeline alignment, SRT subtitle import/generation, ZIP backup export
- **Voice Management** — Voice file CRUD, preview, and editing
- **Hot Model Management** — Multi-model concurrency control, LRU eviction, idle auto-unload
- **Multi-Backend Branches** — Supports 3 Qwen3-TTS implementations ([QwenLM](https://github.com/QwenLM/Qwen3-TTS) / [streaming](https://github.com/rekuenkdr/Qwen3-TTS-streaming) / [faster](https://github.com/andimarafioti/faster-qwen3-tts))

---

## Interface Preview

<table>
  <tr>
    <td><img width="100%" alt="Base-EN" src="https://github.com/user-attachments/assets/cfb861db-c0b7-4979-9183-d79d9af52672" /></td>
    <td><img width="100%" alt="Voices-EN" src="https://github.com/user-attachments/assets/e7c6d645-e0c5-44e4-99a3-7e4ac5071373" /></td>
    <td><img width="100%" alt="Batch-EN" src="https://github.com/user-attachments/assets/b3c6daa5-c432-4e57-86a9-fbe92334f2f6" /></td>
    <td><img width="100%" alt="Setting-EN" src="https://github.com/user-attachments/assets/aae11860-3422-484a-ac53-6ffe89e1e9fd" /></td>
  </tr>
</table>

---

## Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.10+ |
| Node.js | 18+ |
| Package Manager | pnpm |
| ffmpeg | Optional, for MP3 / Opus / AAC format conversion |

---

## Quick Start

**Linux / macOS:**

```bash
chmod +x start.sh
./start.sh
```

**Windows:**

```bat
start.bat
```

### Manual Start

**Backend:**

```bash
# Install web backend dependencies
pip install -e .

# Start server
uvicorn backend.main:app --port 8000 --host localhost
```

**Frontend (development):**

```bash
cd frontend
pnpm install
pnpm dev
```

The frontend dev server listens on `http://localhost:5173` by default, with API requests proxied to the backend on port 8000.

**Frontend (production build):**

```bash
cd frontend
pnpm install
pnpm build
```

Build output goes to `backend/static/` and is served directly by FastAPI.

---

## Configuration

Edit `backend/settings.json`:

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

| Field | Description |
|-------|-------------|
| `max_concurrent_models` | Maximum number of concurrently loaded models |
| `idle_unload_seconds` | Idle model auto-unload timeout (seconds) |
| `backend_branch` | Backend branch (see options below) |
| `project_dir` | Qwen3-TTS project directory |
| `env_dir` | Python virtual environment path for Qwen3-TTS |
| `model_dir` | Model weights directory |
| `voice_dir` | Voice file storage directory |
| `max_seq_len` | Static KV cache max sequence length (Faster branch only) |
| `batch_composer` | Batch audio composition limits (see sub-fields below) |

`batch_composer` sub-fields:

| Sub-Field | Default | Description |
|-----------|---------|-------------|
| `max_segments` | 1000 | Maximum audio segments per composition |
| `max_output_samples` | 100000000 | Maximum sample count for final output |
| `max_decoded_samples` | 100000000 | Maximum sample count per decoded segment |
| `max_total_decoded_samples` | 100000000 | Maximum total sample count across all decoded segments |
| `max_time_stretch_rate` | 16.0 | Maximum time-stretch rate (1/16 to 16x) |
| `max_audio_mib` | 32 | Maximum base64-encoded size per segment (MiB) |
| `max_total_audio_mib` | 256 | Maximum total base64-encoded size across all segments (MiB) |
| `min_sample_rate` | 8000 | Minimum allowed output sample rate (Hz) |
| `max_sample_rate` | 192000 | Maximum allowed output sample rate (Hz) |

**Available Backend Branches:**

| Branch ID | Characteristics |
|-----------|----------------|
| `QwenLM/Qwen3-TTS` | Official implementation |
| `dffdeeq/Qwen3-TTS-streaming` | Community streaming optimization (torch.compile) |
| `andimarafioti/faster-qwen3-tts` | CUDA Graph 6-10x inference acceleration |

---

## Architecture

```
Browser (Vue 3 SPA)
    │
    ▼ HTTP/WebSocket
FastAPI Web Server (lightweight, no PyTorch loaded)
    │
    ▼ TCP (length-prefixed JSON)
Worker Subprocess (loads Qwen3-TTS model, handles GPU inference)
```

- **Process Isolation** — Web server and model inference run in separate processes; the web process never imports PyTorch, keeping dependencies decoupled
- **Pluggable Branches** — The `branches/` directory is loaded via dynamic discovery
- **Unified Worker** — All branches share the same Worker TCP protocol, adapted via `worker_provider.py` plugins
- **WebSocket Push** — Model cache status, Worker status, and inference count are synced to the frontend in real time
