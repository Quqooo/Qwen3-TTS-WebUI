import type { SynthesisRequest, ComposeSegment, ComposeResponse } from "../types"
import { extractErrorText } from "./client"

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api"

export const synthesisApi = {
  synthesize: async (req: SynthesisRequest, signal?: AbortSignal): Promise<Blob> => {
    signal?.throwIfAborted()
    const res = await fetch(`${API_BASE}/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    })
    if (!res.ok) {
      const raw = await res.text().catch(() => "Unknown error")
      const msg = extractErrorText(raw)
      throw Object.assign(new Error(msg), { status: res.status })
    }
    const blob = await res.blob()
    signal?.throwIfAborted()
    return blob
  },

  synthesizePcmStream: async (
    req: SynthesisRequest,
    onChunk: (chunk: Uint8Array) => void,
    signal?: AbortSignal,
  ): Promise<Blob> => {
    signal?.throwIfAborted()
    const res = await fetch(`${API_BASE}/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    })
    if (!res.ok) {
      const raw = await res.text().catch(() => "Unknown error")
      const msg = extractErrorText(raw)
      throw Object.assign(new Error(msg), { status: res.status })
    }
    if (!res.body) throw new Error("Streaming response body is unavailable")

    const reader = res.body.getReader()
    const abortReader = () => { void reader.cancel(signal?.reason).catch(() => undefined) }
    signal?.addEventListener("abort", abortReader, { once: true })
    const chunks: Uint8Array[] = []
    let totalBytes = 0
    try {
      while (true) {
        signal?.throwIfAborted()
        const { done, value } = await reader.read()
        signal?.throwIfAborted()
        if (done) break
        if (!value?.length) continue
        chunks.push(value)
        totalBytes += value.length
        onChunk(value)
      }

      const pcm = new Uint8Array(totalBytes)
      let offset = 0
      for (const chunk of chunks) {
        pcm.set(chunk, offset)
        offset += chunk.length
      }
      signal?.throwIfAborted()
      return pcm16ToWav(pcm, req.output.sample_rate ?? 24000)
    } finally {
      signal?.removeEventListener("abort", abortReader)
      reader.releaseLock()
    }
  },
}

export class PcmStreamPlayer {
  private readonly context: AudioContext
  private readonly output: GainNode
  private readonly sampleRate: number
  private readonly sources = new Set<AudioBufferSourceNode>()
  private nextStartTime = 0
  private pendingByte: number | undefined

  constructor(sampleRate: number, volume = 1) {
    this.sampleRate = sampleRate
    this.context = new AudioContext()
    this.output = this.context.createGain()
    this.output.gain.value = Math.max(0, Math.min(1, volume))
    this.output.connect(this.context.destination)
    void this.context.resume()
  }

  push(chunk: Uint8Array): void {
    let bytes = chunk
    if (this.pendingByte !== undefined) {
      const joined = new Uint8Array(chunk.length + 1)
      joined[0] = this.pendingByte
      joined.set(chunk, 1)
      bytes = joined
      this.pendingByte = undefined
    }
    if (bytes.length % 2) {
      this.pendingByte = bytes[bytes.length - 1]
      bytes = bytes.subarray(0, bytes.length - 1)
    }
    if (!bytes.length) return

    const samples = bytes.length / 2
    const buffer = this.context.createBuffer(1, samples, this.sampleRate)
    const channel = buffer.getChannelData(0)
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    for (let i = 0; i < samples; i++) {
      channel[i] = view.getInt16(i * 2, true) / 32768
    }

    const source = this.context.createBufferSource()
    source.buffer = buffer
    source.connect(this.output)
    source.onended = () => this.sources.delete(source)
    this.sources.add(source)
    const startAt = Math.max(this.context.currentTime + 0.03, this.nextStartTime)
    source.start(startAt)
    this.nextStartTime = startAt + buffer.duration
  }

  stop(): void {
    for (const source of this.sources) {
      try { source.stop() } catch { /* already stopped */ }
    }
    this.sources.clear()
    void this.context.close()
  }
}

export function pcm16ToWav(pcm: Uint8Array, sampleRate: number): Blob {
  const evenLength = pcm.length - (pcm.length % 2)
  const buffer = new ArrayBuffer(44 + evenLength)
  const view = new DataView(buffer)
  const writeText = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }
  writeText(0, "RIFF")
  view.setUint32(4, 36 + evenLength, true)
  writeText(8, "WAVE")
  writeText(12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeText(36, "data")
  view.setUint32(40, evenLength, true)
  new Uint8Array(buffer, 44).set(pcm.subarray(0, evenLength))
  return new Blob([buffer], { type: "audio/wav" })
}

export const composeApi = {
  compose: async (segments: ComposeSegment[], mode: string, fmt: string, sampleRate: number, gainDb: number, minSilenceMs: number): Promise<ComposeResponse> => {
    const res = await fetch(`${API_BASE}/batch/compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segments, mode, format: fmt, sample_rate: sampleRate, gain_db: gainDb, min_silence_ms: minSilenceMs }),
    })
    if (!res.ok) {
      const raw = await res.text().catch(() => "Unknown error")
      const msg = extractErrorText(raw)
      throw Object.assign(new Error(msg), { status: res.status })
    }
    return res.json()
  },
}

export function getBlobDuration(blob: Blob): Promise<number> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(blob)
    const audio = new Audio()
    audio.onloadedmetadata = () => {
      URL.revokeObjectURL(url)
      resolve(audio.duration)
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(0)
    }
    audio.src = url
  })
}
