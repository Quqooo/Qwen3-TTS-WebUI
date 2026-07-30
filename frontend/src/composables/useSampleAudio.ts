export function generateSampleWav(durationSec = 2.0, sampleRate = 24000): Blob {
  const numSamples = Math.floor(sampleRate * durationSec)
  const freq = 440
  const volume = 0.3

  // PCM float32 samples
  const samples = new Float32Array(numSamples)
  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate
    const envelope = Math.min(1, (numSamples - i) / (sampleRate * 0.05))
    samples[i] = Math.sin(2 * Math.PI * freq * t) * volume * envelope
  }

  // WAV header + data
  const bytesPerSample = 2
  const numChannels = 1
  const dataLength = numSamples * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataLength)
  const view = new DataView(buffer)

  function writeString(offset: number, str: string) {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
  }

  writeString(0, "RIFF")
  view.setUint32(4, 36 + dataLength, true)
  writeString(8, "WAVE")
  writeString(12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true)
  view.setUint16(32, numChannels * bytesPerSample, true)
  view.setUint16(34, bytesPerSample * 8, true)
  writeString(36, "data")
  view.setUint32(40, dataLength, true)

  let offset = 44
  for (let i = 0; i < numSamples; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    const val = sample < 0 ? sample * 0x8000 : sample * 0x7FFF
    view.setInt16(offset, val, true)
    offset += 2
  }

  return new Blob([buffer], { type: "audio/wav" })
}

export function sampleAudioUrl(): string {
  return URL.createObjectURL(generateSampleWav(2.0))
}

export function sampleShortAudioUrl(): string {
  return URL.createObjectURL(generateSampleWav(0.5))
}
