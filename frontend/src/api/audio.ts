import { api } from "./client"
import { t } from "../lang"

export interface TrimResult {
  ok: boolean
  audio: string
  sample_rate: number
  duration: number
}

export const audioApi = {
  trim: (data: { audio: string; start: number; end: number }) =>
    api.post<TrimResult>("/audio/trim", data),
}

/**
 * 纯前端裁剪音频（WAV），不依赖后端。
 * 使用 Web Audio API 解码并重新编码 WAV，保证在后端不可用或跨域时也能正常更新音频。
 */
export async function trimAudioBlob(
  blob: Blob,
  start: number,
  end: number,
  sampleRate?: number,
): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer()
  const Ctx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const ctx = new Ctx()
  try {
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
    const sr = sampleRate ?? audioBuffer.sampleRate
    const startSample = Math.max(0, Math.floor(start * sr))
    const endSample = Math.min(audioBuffer.length, Math.ceil(end * sr))
    if (endSample <= startSample) throw new Error(t('api.audio.invalidTrimRange'))

    const length = endSample - startSample
    const out = ctx.createBuffer(audioBuffer.numberOfChannels, length, sr)
    for (let ch = 0; ch < audioBuffer.numberOfChannels; ch++) {
      const src = audioBuffer.getChannelData(ch)
      out.copyToChannel(src.subarray(startSample, endSample), ch)
    }
    return encodeWav(out)
  } finally {
    ctx.close()
  }
}

function encodeWav(buffer: AudioBuffer): Blob {
  const numChannels = buffer.numberOfChannels
  const sr = buffer.sampleRate
  const numFrames = buffer.length
  const bytesPerSample = 2
  const blockAlign = numChannels * bytesPerSample
  const dataSize = numFrames * blockAlign
  const arrayBuffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(arrayBuffer)

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
  }

  writeStr(0, "RIFF")
  view.setUint32(4, 36 + dataSize, true)
  writeStr(8, "WAVE")
  writeStr(12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sr, true)
  view.setUint32(28, sr * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeStr(36, "data")
  view.setUint32(40, dataSize, true)

  let offset = 44
  for (let i = 0; i < numFrames; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      let s = buffer.getChannelData(ch)[i]
      s = Math.max(-1, Math.min(1, s))
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
      offset += 2
    }
  }
  return new Blob([arrayBuffer], { type: "audio/wav" })
}
