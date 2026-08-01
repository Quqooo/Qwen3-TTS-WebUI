<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from "vue"
import { Volume2, Play, Pause } from "@lucide/vue"
import { useUserConfig } from "../../composables/useUserConfig"
import { primaryColor, waveformGray } from "../../theme"
import { useTheme } from "../../composables/useTheme"
import { parseSrtContent } from "../../utils/subtitleParser"

const props = defineProps<{
  audioUrl?: string | null
  duration?: number
  isGenerating?: boolean
  subtitles?: string
}>()

const { globalVolume } = useUserConfig()
const { isDark } = useTheme()

const audioRef = ref<HTMLAudioElement | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const volume = ref(globalVolume.value / 100)
const progressBar = ref<HTMLDivElement | null>(null)
const grayCanvas = ref<HTMLCanvasElement | null>(null)
const blueCanvas = ref<HTMLCanvasElement | null>(null)
const seeking = ref(false)
const peaks = ref<Float32Array | null>(null)
const audioDuration = ref(0)
let rafId = 0
let resizeObserver: ResizeObserver | null = null

const progressPct = computed(() => {
  const d = props.duration ?? audioDuration.value
  if (!d || !props.audioUrl) return 0
  return Math.min(100, (currentTime.value / d) * 100)
})

const progressClipPath = computed(() => `inset(0 ${100 - progressPct.value}% 0 0)`)

function updateProgress() {
  if (audioRef.value && !seeking.value) {
    currentTime.value = audioRef.value.ended ? 0 : audioRef.value.currentTime
  }
  rafId = requestAnimationFrame(updateProgress)
}

// ── 流式连续播放（Web Audio 调度器） ──────────────────────────
// 使用 AudioContext + AudioBufferSourceNode 顺序调度每个 PCM 块，
// 块之间无缝衔接；播放到已缓冲末尾时自然等待下一块，直到 endStream()。
interface StreamState {
  ctx: AudioContext
  gain: GainNode
  nextStartTime: number
  pendingByte: number | undefined
  sampleRate: number
  totalSamples: number
  rawChunks: Float32Array[]
  playing: boolean
  playedSamples: number
  ended: boolean
  stopped: boolean
  playbackStartCtxTime: number
  samplesPlayedAtStart: number
  nextScheduleSample: number
  sources: Set<AudioBufferSourceNode>
  buffers: AudioBuffer[]
}

let stream: StreamState | null = null
const streamPlayedSamples = ref(0)
const streamBufferedSamples = ref(0)
const streamActive = ref(false)
const streamFinished = ref(false)
const streamPeaks = ref<Float32Array | null>(null)
let keepStreamPeaks = false

function streamTimeFromSamples(samples: number): number {
  if (!stream) return 0
  return samples / stream.sampleRate
}
const streamCurrentTime = computed(() => streamTimeFromSamples(streamPlayedSamples.value))
const streamBufferedTime = computed(() => streamTimeFromSamples(streamBufferedSamples.value))
const streamMode = computed(() => streamActive.value || streamFinished.value)
const displayDuration = computed(() => {
  if (streamMode.value && streamBufferedSamples.value) {
    return streamBufferedTime.value
  }
  return props.duration ?? audioDuration.value
})
const streamProgressPct = computed(() => {
  const total = streamBufferedSamples.value
  if (!total) return 0
  return Math.min(100, (streamPlayedSamples.value / total) * 100)
})
const streamClipPath = computed(() => `inset(0 ${100 - streamProgressPct.value}% 0 0)`)
const displayCurrentTime = computed(() => streamMode.value ? streamCurrentTime.value : currentTime.value)
const subtitleSegments = computed(() => props.subtitles ? parseSrtContent(props.subtitles) : [])
const currentSubtitle = computed(() => {
  const time = displayCurrentTime.value
  if (time <= 0) return ""
  return subtitleSegments.value.find(segment => (
    segment.start !== undefined
    && segment.end !== undefined
    && time >= segment.start
    && time < segment.end
  ))?.text ?? ""
})

let playedRafId = 0
let lastPeaksBuild = 0
function trackPlayedSamples() {
  if (!stream) return
  const ctx = stream.ctx
  const playing = stream.playing && ctx.state === "running"
  let played: number
  if (playing) {
    const ctxElapsed = ctx.currentTime - stream.playbackStartCtxTime
    played = Math.floor(stream.samplesPlayedAtStart + ctxElapsed * stream.sampleRate)
  } else {
    played = stream.playedSamples
  }
  played = Math.max(stream.playedSamples, played)
  streamPlayedSamples.value = Math.max(0, Math.min(streamBufferedSamples.value, played))
  // 限制峰值重算频率（约每 200ms）
  const now = performance.now()
  if (now - lastPeaksBuild > 200) {
    lastPeaksBuild = now
    buildStreamPeaks()
  }
  // 全部缓冲已播放完毕且流已结束 → 保留完整流，便于再次播放和拖动。
  if (stream.ended && playing && streamPlayedSamples.value >= streamBufferedSamples.value) {
    stopScheduledSources()
    stream.playing = false
    stream.playedSamples = 0
    stream.samplesPlayedAtStart = 0
    stream.nextScheduleSample = 0
    streamPlayedSamples.value = 0
    void stream.ctx.suspend()
    isPlaying.value = false
  }
  playedRafId = requestAnimationFrame(trackPlayedSamples)
}

function buildStreamPeaks() {
  if (!stream || !streamBufferedSamples.value) {
    streamPeaks.value = null
    return
  }
  const numBars = computeNumBars()
  if (numBars <= 0) return
  const total = streamBufferedSamples.value
  const samplesPerBar = total / numBars
  const pks = new Float32Array(numBars)
  const chunks = stream.rawChunks
  // 计算每个 bar 的全局起点（样本）
  for (let i = 0; i < numBars; i++) {
    const startSample = Math.floor(i * samplesPerBar)
    const endSample = Math.min(total, Math.floor((i + 1) * samplesPerBar))
    let max = 0
    // 遍历 chunks 找到对应区间（chunks 按到达顺序累积）
    let cursor = 0
    for (const ch of chunks) {
      const chStart = cursor
      const chEnd = cursor + ch.length
      if (chEnd <= startSample) { cursor = chEnd; continue }
      if (chStart >= endSample) break
      const from = Math.max(0, startSample - chStart)
      const to = Math.min(ch.length, endSample - chStart)
      for (let j = from; j < to; j++) {
        const abs = Math.abs(ch[j])
        if (abs > max) max = abs
      }
      cursor = chEnd
    }
    pks[i] = max
  }
  let maxPeak = 0
  for (let i = 0; i < numBars; i++) { if (pks[i] > maxPeak) maxPeak = pks[i] }
  if (maxPeak > 0) { for (let i = 0; i < numBars; i++) { pks[i] /= maxPeak } }
  streamPeaks.value = pks
  drawStreamCanvases()
}

function drawStreamCanvases() {
  if (!streamPeaks.value || !progressBar.value) return
  const w = progressBar.value.clientWidth
  const h = progressBar.value.clientHeight
  drawOnCanvas(grayCanvas.value, streamPeaks.value, w, h, waveformGray())
  drawOnCanvas(blueCanvas.value, streamPeaks.value, w, h, primaryColor())
  if (progressBar.value) {
    resizeObserver?.disconnect()
    resizeObserver = new ResizeObserver(() => { if (streamPeaks.value) drawStreamCanvases() })
    resizeObserver.observe(progressBar.value)
  }
}

function startStream(sampleRate: number) {
  stopStream()
  const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
  const gainNode = ctx.createGain()
  gainNode.gain.value = Math.max(0, Math.min(1, volume.value))
  gainNode.connect(ctx.destination)
  // 创建后立即挂起，避免任何在「生成语音」点击手势下自动播放的可能。
  // 仅当用户点击播放按钮时才 resume 并开始调度音频。
  void ctx.suspend()
  stream = {
    ctx,
    gain: gainNode,
    nextStartTime: 0,
    pendingByte: undefined,
    sampleRate,
    totalSamples: 0,
    rawChunks: [],
    playing: false,
    playedSamples: 0,
    ended: false,
    stopped: false,
    playbackStartCtxTime: 0,
    samplesPlayedAtStart: 0,
    nextScheduleSample: 0,
    sources: new Set(),
    buffers: [],
  }
  streamBufferedSamples.value = 0
  streamPlayedSamples.value = 0
  streamActive.value = true
  streamFinished.value = false
  isPlaying.value = false
  playedRafId = requestAnimationFrame(trackPlayedSamples)
}

function startBufferNow(buffer: AudioBuffer, offsetSamples = 0) {
  if (!stream || offsetSamples >= buffer.length) return
  const owner = stream
  const source = owner.ctx.createBufferSource()
  source.buffer = buffer
  source.connect(owner.gain)
  const startAt = Math.max(owner.ctx.currentTime + 0.02, owner.nextStartTime)
  const offsetSeconds = offsetSamples / owner.sampleRate
  source.start(startAt, offsetSeconds)
  owner.sources.add(source)
  owner.nextStartTime = startAt + buffer.duration - offsetSeconds
  const playedLength = buffer.length - offsetSamples
  source.onended = () => {
    owner.sources.delete(source)
  }
  owner.nextScheduleSample += playedLength
}

function stopScheduledSources() {
  if (!stream) return
  for (const source of stream.sources) {
    source.onended = null
    try { source.stop() } catch { /* already stopped */ }
  }
  stream.sources.clear()
  stream.nextStartTime = 0
}

function scheduleFromSample(targetSample: number, shouldSchedule = true) {
  if (!stream) return
  const target = Math.max(0, Math.min(stream.totalSamples, Math.floor(targetSample)))
  stopScheduledSources()
  stream.playedSamples = target
  stream.samplesPlayedAtStart = target
  stream.playbackStartCtxTime = stream.ctx.currentTime
  stream.nextScheduleSample = target
  streamPlayedSamples.value = target
  if (!shouldSchedule) return

  let cursor = 0
  for (const buffer of stream.buffers) {
    const end = cursor + buffer.length
    if (end <= target) {
      cursor = end
      continue
    }
    startBufferNow(buffer, Math.max(0, target - cursor))
    cursor = end
  }
}

function appendStreamChunk(chunk: Uint8Array) {
  if (!stream || stream.stopped) return
  let bytes = chunk
  if (stream.pendingByte !== undefined) {
    const joined = new Uint8Array(chunk.length + 1)
    joined[0] = stream.pendingByte
    joined.set(chunk, 1)
    bytes = joined
    stream.pendingByte = undefined
  }
  if (bytes.length % 2) {
    stream.pendingByte = bytes[bytes.length - 1]
    bytes = bytes.subarray(0, bytes.length - 1)
  }
  if (!bytes.length) return

  const samples = bytes.length / 2
  const buffer = stream.ctx.createBuffer(1, samples, stream.sampleRate)
  const channel = buffer.getChannelData(0)
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const raw = new Float32Array(samples)
  for (let i = 0; i < samples; i++) {
    const v = view.getInt16(i * 2, true) / 32768
    channel[i] = v
    raw[i] = v
  }
  stream.rawChunks.push(raw)
  stream.buffers.push(buffer)

  // 仅在用户已点击播放（playing）时才真正调度并启动音频；
  // 否则仅累积缓冲，待 resume 时统一启动，避免首块到达即自动播放。
  if (stream.playing) {
    // 播放追上缓冲尾部后，下一块以新的上下文时间重新起算，
    // 避免网络等待时间被误计入播放进度。
    if (!stream.sources.size) {
      stream.playedSamples = stream.totalSamples
      stream.samplesPlayedAtStart = stream.totalSamples
      stream.playbackStartCtxTime = stream.ctx.currentTime
      stream.nextStartTime = 0
      stream.nextScheduleSample = stream.totalSamples
    }
    startBufferNow(buffer)
  }
  stream.totalSamples += samples
  streamBufferedSamples.value = stream.totalSamples
}

function startPlayback() {
  if (!stream) return
  const startSample = streamPlayedSamples.value >= streamBufferedSamples.value
    ? 0
    : streamPlayedSamples.value
  scheduleFromSample(startSample)
  stream.playing = true
  void stream.ctx.resume()
}

function pausePlayback() {
  if (!stream) return
  stream.playing = false
  void stream.ctx.suspend()
  // 固定当前样本位置，避免暂停后的刷新帧退回上一次调度起点。
  stream.playedSamples = streamPlayedSamples.value
  stream.samplesPlayedAtStart = streamPlayedSamples.value
}

function endStream() {
  if (!stream) return
  stream.ended = true
  streamActive.value = false
  streamFinished.value = true
  // 仅接收、尚未播放时，不应让处于 suspended 的 AudioContext 被视为正在播放。
  if (!stream.playing) {
    stream.playedSamples = streamPlayedSamples.value
    stream.samplesPlayedAtStart = streamPlayedSamples.value
  }
  buildStreamPeaks()
}

function stopStream() {
  cancelAnimationFrame(playedRafId)
  if (stream) {
    stream.stopped = true
    try {
      stream.ctx.close()
    } catch {
      /* already closed */
    }
    stream = null
  }
  streamActive.value = false
  streamFinished.value = false
  // 流式完成后将已计算的波形保留为最终波形，避免空白
  if (streamPeaks.value) {
    peaks.value = streamPeaks.value
    keepStreamPeaks = true
    nextTick(() => {
      drawCanvases()
      if (progressBar.value) {
        resizeObserver?.disconnect()
        resizeObserver = new ResizeObserver(() => { if (peaks.value) drawCanvases() })
        resizeObserver.observe(progressBar.value)
      }
    })
  }
  streamPeaks.value = null
  isPlaying.value = false
}

// ── 普通播放（blob URL�?─────────────────────────────────────

watch(() => props.audioUrl, (val) => {
  // 流式接收结束后父组件会写入最终 Blob URL，供下载和后备播放使用。
  // 此时 Web Audio 流可能仍在播放，不能重置其播放按钮和时间轴。
  if (streamMode.value) {
    if (val && audioRef.value) audioRef.value.volume = volume.value
    return
  }
  isPlaying.value = false
  currentTime.value = 0
  if (keepStreamPeaks) {
    // 流式完成后的首次 blob 设置：保留已计算波形，无需重新解码
    keepStreamPeaks = false
    if (val) {
      rafId = requestAnimationFrame(updateProgress)
      if (audioRef.value) audioRef.value.volume = volume.value
    }
    return
  }
  peaks.value = null
  if (val) {
    rafId = requestAnimationFrame(updateProgress)
    if (audioRef.value) audioRef.value.volume = volume.value
    loadAndRenderWaveform(val)
  }
}, { immediate: true })

watch(audioRef, (el) => {
  if (el) el.volume = volume.value
})

watch(isDark, () => {
  if (streamMode.value && streamPeaks.value) {
    drawStreamCanvases()
  }
  if (peaks.value) {
    drawCanvases()
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  cancelAnimationFrame(playedRafId)
  resizeObserver?.disconnect()
  stopStream()
})

async function loadAndRenderWaveform(url: string) {
  try {
    const response = await fetch(url)
    const arrayBuffer = await response.arrayBuffer()
    const audioCtx = getWaveformAudioCtx()
    const audioBuffer = await decodeAudioDataSafe(audioCtx, arrayBuffer)
    computeAndDrawPeaks(audioBuffer.getChannelData(0))
  } catch {
    // 解码失败（如 AudioContext 受限）：退化为元素采样，仍保证波形+进度层可见
    try { await renderPeaksViaElement() } catch { /* 最终退化为纯进度条 */ }
  }
}

let _waveformCtx: AudioContext | null = null
function getWaveformAudioCtx(): AudioContext {
  if (!_waveformCtx) {
    _waveformCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
  }
  return _waveformCtx
}

function decodeAudioDataSafe(ctx: AudioContext, data: ArrayBuffer): Promise<AudioBuffer> {
  // 部分浏览器在 suspended 状态下会拒绝解码，先 resume
  if (ctx.state === "suspended") {
    ctx.resume().catch(() => {})
  }
  return new Promise<AudioBuffer>((resolve, reject) => {
    // 优先使用 promise 形式
    const p = ctx.decodeAudioData(data)
    if (p && typeof p.then === "function") {
      p.then(resolve, () => {
        // 回退到回调形式（同一份 ArrayBuffer 已消费，需重新传入副本）
        try {
          ctx.decodeAudioData(data.slice(0), resolve, reject)
        } catch (err) {
          reject(err)
        }
      })
    } else {
      // 旧式回调 API
      ;(ctx as any).decodeAudioData(data, resolve, reject)
    }
  })
}

let _elemSource: MediaElementAudioSourceNode | null = null
function seekTo(audio: HTMLAudioElement, t: number): Promise<void> {
  return new Promise((resolve) => {
    const onSeeked = () => { audio.removeEventListener("seeked", onSeeked); resolve() }
    audio.addEventListener("seeked", onSeeked)
    audio.currentTime = Math.max(0, Math.min(t, (audio.duration || t) - 0.001))
  })
}

// 当 decodeAudioData 不可用时，借助 <audio> 元素 + AnalyserNode 采样整段波形
async function renderPeaksViaElement(): Promise<void> {
  const audio = audioRef.value
  if (!audio) throw new Error("no audio element")
  const ctx = getWaveformAudioCtx()
  if (ctx.state === "suspended") { try { await ctx.resume() } catch {} }
  if (!audio.duration || isNaN(audio.duration)) {
    await new Promise<void>((resolve, reject) => {
      const onMeta = () => { audio.removeEventListener("loadedmetadata", onMeta); audio.removeEventListener("error", onErr); resolve() }
      const onErr = () => { audio.removeEventListener("loadedmetadata", onMeta); audio.removeEventListener("error", onErr); reject(new Error("meta")) }
      audio.addEventListener("loadedmetadata", onMeta)
      audio.addEventListener("error", onErr)
      audio.load()
    })
  }
  const duration = audio.duration
  if (!duration || isNaN(duration) || duration <= 0) throw new Error("no duration")
  if (!_elemSource) _elemSource = ctx.createMediaElementSource(audio)
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 1024
  _elemSource.connect(analyser)
  analyser.connect(ctx.destination)
  const numBars = computeNumBars()
  if (numBars <= 0) { analyser.disconnect(); _elemSource.disconnect(); _elemSource = null; throw new Error("zero width") }
  const data = new Float32Array(analyser.fftSize)
  const pks = new Float32Array(numBars)
  const prevMuted = audio.muted
  const wasPaused = audio.paused
  audio.muted = true
  for (let i = 0; i < numBars; i++) {
    const t = ((i + 0.5) / numBars) * duration
    await seekTo(audio, t)
    analyser.getFloatTimeDomainData(data)
    let max = 0
    for (let j = 0; j < data.length; j++) { const a = Math.abs(data[j]); if (a > max) max = a }
    pks[i] = max
  }
  audio.muted = prevMuted
  if (wasPaused) audio.pause()
  analyser.disconnect()
  let maxPeak = 0
  for (let i = 0; i < numBars; i++) if (pks[i] > maxPeak) maxPeak = pks[i]
  if (maxPeak > 0) for (let i = 0; i < numBars; i++) pks[i] /= maxPeak
  peaks.value = pks
  drawCanvases()
  if (progressBar.value) {
    resizeObserver?.disconnect()
    resizeObserver = new ResizeObserver(() => { if (peaks.value) drawCanvases() })
    resizeObserver.observe(progressBar.value)
  }
}


function computeAndDrawPeaks(channelData: Float32Array) {
  const render = () => {
    const numBars = computeNumBars()
    if (numBars <= 0) return false
    const samplesPerBar = Math.floor(channelData.length / numBars)
    const pks = new Float32Array(numBars)
    for (let i = 0; i < numBars; i++) {
      let max = 0
      const start = i * samplesPerBar
      const end = Math.min(start + samplesPerBar, channelData.length)
      for (let j = start; j < end; j++) {
        const abs = Math.abs(channelData[j])
        if (abs > max) max = abs
      }
      pks[i] = max
    }
    let maxPeak = 0
    for (let i = 0; i < numBars; i++) { if (pks[i] > maxPeak) maxPeak = pks[i] }
    if (maxPeak > 0) { for (let i = 0; i < numBars; i++) { pks[i] /= maxPeak } }
    peaks.value = pks
    drawCanvases()
    if (progressBar.value) {
      resizeObserver?.disconnect()
      resizeObserver = new ResizeObserver(() => { if (peaks.value) drawCanvases() })
      resizeObserver.observe(progressBar.value)
    }
    return true
  }
  nextTick(() => {
    if (!render()) {
      // 容器尚未布局（宽度为 0）：待其具备宽度后重试
      const ro = new ResizeObserver(() => {
        if (render()) ro.disconnect()
      })
      if (progressBar.value) ro.observe(progressBar.value)
    }
  })
}

function computeNumBars(): number {
  return progressBar.value ? Math.floor(progressBar.value.clientWidth / 4) : 0
}



function drawCanvases() {
  if (!peaks.value || !progressBar.value) return
  const w = progressBar.value.clientWidth
  const h = progressBar.value.clientHeight
  drawOnCanvas(grayCanvas.value, peaks.value, w, h, waveformGray())
  drawOnCanvas(blueCanvas.value, peaks.value, w, h, primaryColor())
}

function drawOnCanvas(
  canvas: HTMLCanvasElement | null,
  pks: Float32Array,
  w: number,
  h: number,
  color: string,
) {
  if (!canvas || w <= 0 || h <= 0) return
  const ctx = canvas.getContext("2d")
  if (!ctx) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)
  const numBars = pks.length
  const barWidth = 3
  const barSpacing = 4
  const scaleX = w / (numBars * barSpacing)
  ctx.fillStyle = color
  for (let i = 0; i < numBars; i++) {
    const x = i * barSpacing * scaleX
    const barHeight = Math.max(1, pks[i] * (h * 0.9))
    const y = (h - barHeight) / 2
    const bw = Math.max(1, barWidth * scaleX)
    const c = ctx as CanvasRenderingContext2D & { roundRect?: (x: number, y: number, w: number, h: number, r: number) => void }
    c.beginPath()
    if (c.roundRect) {
      c.roundRect(x, y, bw, barHeight, 1)
    } else {
      c.rect(x, y, bw, barHeight)
    }
    c.fill()
  }
}

function togglePlay() {
  if (stream) {
    // 流式播放：仅在用户点击播放后才 resume 并开始调度音频，
    // 点击暂停则挂起上下文（保留已调度缓冲，resume 时无缝继续）。
    if (isPlaying.value) {
      pausePlayback()
      isPlaying.value = false
    } else {
      startPlayback()
      isPlaying.value = true
    }
    return
  }
  if (!audioRef.value) return
  if (isPlaying.value) {
    audioRef.value.pause()
  } else {
    audioRef.value.play()
  }
}

function onEnded() {
  isPlaying.value = false
  currentTime.value = 0
}

function onLoadedMetadata() {
  if (audioRef.value) {
    audioDuration.value = audioRef.value.duration
  }
}

function onPlayEvent() {
  // 仅 blob 模式（非流式）下由 audio 元素驱动播放状态，
  // 避免流式结束后 audioRef 事件与流式状态相互干扰。
  if (streamMode.value) return
  isPlaying.value = true
}

function onPauseEvent() {
  if (streamMode.value) return
  isPlaying.value = false
}

function onSeek(ev: MouseEvent) {
  if (!progressBar.value) return
  const rect = progressBar.value.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
  if (stream && streamBufferedSamples.value) {
    scheduleFromSample(
      ratio * streamBufferedSamples.value,
      stream.playing,
    )
    if (stream.playing && stream.ctx.state === "suspended") {
      void stream.ctx.resume()
    }
    return
  }
  if (!audioRef.value) return
  const seekTime = ratio * (props.duration ?? audioDuration.value)
  audioRef.value.currentTime = seekTime
  currentTime.value = seekTime
}

function onSeekStart(ev: MouseEvent) {
  seeking.value = true
  onSeek(ev)
}

function onSeekEnd() {
  seeking.value = false
}

function onWheel(ev: WheelEvent) {
  ev.preventDefault()
  const delta = ev.deltaY > 0 ? -0.05 : 0.05
  volume.value = Math.max(0, Math.min(1, volume.value + delta))
  if (audioRef.value) audioRef.value.volume = volume.value
  if (stream) stream.gain.gain.value = volume.value
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, "0")}`
}

function resetVisual() {
  keepStreamPeaks = false
  peaks.value = null
  streamPeaks.value = null
  streamFinished.value = false
}

defineExpose({
  appendChunk: (chunk: Uint8Array, sampleRate: number) => {
    if (!stream) startStream(sampleRate)
    appendStreamChunk(chunk)
  },
  endStream: () => endStream(),
  stopStream: () => stopStream(),
  resetVisual: () => resetVisual(),
})
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center gap-3">
      <button
        class="w-8 h-8 flex items-center justify-center rounded-full shrink-0 transition-all duration-150"
        :class="[
          isGenerating && !streamMode
            ? 'bg-primary/10 text-primary cursor-default'
            : (audioUrl || streamMode)
              ? 'bg-primary text-primary-foreground hover:opacity-90 cursor-pointer'
              : 'bg-secondary text-muted-foreground/30 cursor-default'
        ]"
        :disabled="!audioUrl && !streamMode && !isGenerating"
        @click="togglePlay()"
      >
        <span v-if="isGenerating && !streamMode" class="block w-4 h-4">
          <span class="block w-full h-full rounded-full border-2 border-current border-t-transparent animate-spin" style="will-change: transform" />
        </span>
        <component :is="isPlaying ? Pause : Play" v-else class="w-4 h-4 fill-current" />
      </button>

      <div
        ref="progressBar"
        class="flex-1 h-8 rounded relative overflow-hidden cursor-pointer select-none"
        :class="(audioUrl || streamMode) ? 'bg-secondary' : 'bg-secondary/40'"
        @mousedown="onSeekStart"
        @mousemove="seeking ? onSeek($event) : null"
        @mouseup="onSeekEnd"
        @mouseleave="onSeekEnd"
      >
        <template v-if="streamMode && streamPeaks">
          <canvas
            ref="grayCanvas"
            class="absolute inset-0 w-full h-full pointer-events-none"
          />
          <div
            class="absolute inset-0 pointer-events-none"
            :style="{ clipPath: streamClipPath }"
          >
            <canvas ref="blueCanvas" class="w-full h-full" />
          </div>
          <div
            class="h-full bg-primary/15"
            :style="{ transform: `translateX(${streamProgressPct - 100}%)` }"
          />
        </template>
        <template v-else-if="peaks">
          <canvas
            ref="grayCanvas"
            class="absolute inset-0 w-full h-full pointer-events-none"
          />
          <div
            class="absolute inset-0 pointer-events-none"
            :style="{ clipPath: progressClipPath }"
          >
            <canvas ref="blueCanvas" class="w-full h-full" />
          </div>
          <div
            class="h-full"
            :class="audioUrl ? 'bg-primary/15' : 'bg-transparent'"
            :style="{ transform: `translateX(${progressPct - 100}%)` }"
          />
        </template>
        <template v-else>
          <div
            class="absolute inset-0 bg-primary/15 pointer-events-none"
            :style="{ transform: `translateX(${(streamMode ? streamProgressPct : progressPct) - 100}%)` }"
          />
        </template>
      </div>

      <div
        class="flex items-center gap-1 text-xs shrink-0 select-none"
        :class="audioUrl ? 'text-muted-foreground' : 'text-muted-foreground/30'"
        @wheel.prevent="onWheel"
        v-tooltip="$t('components.audioPlayer.scrollForVolume')"
      >
        <Volume2 class="w-3 h-3" />
        <span>{{ Math.round(volume * 100) }}%</span>
      </div>
    </div>

    <div
      class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 text-xs"
      :class="audioUrl || streamMode ? 'text-muted-foreground' : 'text-muted-foreground/20'"
    >
      <span>{{ formatTime(displayCurrentTime) }}</span>
      <div class="min-w-0 flex justify-center">
        <span
          v-if="currentSubtitle"
          class="max-w-[80%] truncate text-center text-foreground"
          :title="currentSubtitle"
        >{{ currentSubtitle }}</span>
      </div>
      <span v-if="streamFinished">{{ formatTime(displayDuration) }}</span>
      <span v-else-if="duration !== undefined">{{ formatTime(duration) }}</span>
      <span v-else-if="streamActive" class="italic text-muted-foreground/40">{{ formatTime(streamBufferedTime) }}</span>
      <span v-else>{{ formatTime(audioDuration) }}</span>
    </div>

    <audio
      ref="audioRef"
      :src="audioUrl ?? undefined"
      preload="auto"
      @ended="onEnded"
      @loadedmetadata="onLoadedMetadata"
      @play="onPlayEvent"
      @pause="onPauseEvent"
      class="hidden"
    />
  </div>
</template>
