<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, nextTick } from "vue"
import { LoaderCircle, Upload, X, Check, Scissors, Play, Pause, Volume2, Undo2 } from "@lucide/vue"
import WaveSurfer from "wavesurfer.js"
import { trimAudioBlob } from "../../api/audio"
import { useToast } from "../../composables/useToast"
import { t } from "../../lang"
import { useUserConfig } from "../../composables/useUserConfig"
import { primaryColor, waveformGray } from "../../theme"
import { useTheme } from "../../composables/useTheme"

const { isDark } = useTheme()

const { globalVolume } = useUserConfig()

const props = defineProps<{
  audioUrl?: string | null
  audioName?: string
  trimStart?: number
  trimEnd?: number
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: "file", file: File | null): void
  (e: "update:trimStart", val: number): void
  (e: "update:trimEnd", val: number): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const overlayRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
const isDragOver = ref(false)
const isPlaying = ref(false)
const waveLoading = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const trimMode = ref(false)
const volume = ref(globalVolume.value / 100)

const localStart = ref(0)
const localEnd = ref(0)
const suppressLoop = ref(false)
const clipHistory = ref<Array<{ blob: Blob; start: number; end: number }>>([])
const savedTrimStart = ref(0)
const savedTrimEnd = ref(0)

let ws: WaveSurfer | null = null
let initToken = 0

const leftPct = computed(() => (duration.value ? (localStart.value / duration.value) * 100 : 0))
const rightPct = computed(() => (duration.value ? (localEnd.value / duration.value) * 100 : 0))

function syncDisplayedTime(time: number) {
  const clamped = duration.value > 0
    ? Math.max(0, Math.min(time, duration.value))
    : Math.max(0, time)
  // The label only displays whole seconds. Avoid invalidating the entire Vue
  // subtree on every WaveSurfer animation frame while keeping trim-loop checks
  // at the original frame rate.
  if (Math.floor(clamped) !== Math.floor(currentTime.value)) {
    currentTime.value = clamped
  }
}

async function initWaveSurfer(url: string) {
  const token = ++initToken
  destroyWaveSurfer()
  currentTime.value = 0
  isPlaying.value = false
  suppressLoop.value = false
  waveLoading.value = true
  let loopPending = false
  await nextTick()
  if (token !== initToken) return
  if (!containerRef.value) { waveLoading.value = false; return }
  ws = WaveSurfer.create({
    container: containerRef.value,
    waveColor: waveformGray(),
    progressColor: primaryColor(),
    cursorColor: primaryColor(),
    cursorWidth: 1,
    height: 72,
    barWidth: 3,
    barGap: 1,
    barRadius: 1,
    normalize: true,
    dragToSeek: { debounceTime: 0 },
  })
  ws.setVolume(volume.value)
  ws.load(url)
  ws.on("ready", () => {
    waveLoading.value = false
    duration.value = ws!.getDuration()
    localStart.value = props.trimStart ?? 0
    localEnd.value = props.trimEnd || duration.value
  })
  ws.on("timeupdate", (t) => {
    syncDisplayedTime(t)
    if (trimMode.value && duration.value > 0 && !suppressLoop.value && t >= localEnd.value && !loopPending) {
      loopPending = true
      const target = localStart.value / duration.value
      setTimeout(() => {
        loopPending = false
        if (trimMode.value && !suppressLoop.value) ws?.seekTo(target)
      }, 0)
    }
  })
  ws.on("interaction", (newTime: number) => {
    currentTime.value = newTime
    suppressLoop.value = newTime >= localEnd.value
  })
  ws.on("play", () => { isPlaying.value = true; suppressLoop.value = false })
  ws.on("play", () => { isPlaying.value = true })
  ws.on("pause", () => { isPlaying.value = false })
  ws.on("finish", () => { isPlaying.value = false; ws?.seekTo(0) })
}

function destroyWaveSurfer() {
  if (ws) {
    ws.destroy()
    ws = null
  }
}

function togglePlay() {
  if (!ws) return
  ws.playPause()
}

function removeAudio() {
  trimMode.value = false
  destroyWaveSurfer()
  currentTime.value = 0
  duration.value = 0
  isPlaying.value = false
  waveLoading.value = false
  clipHistory.value = []
  emit("file", null)
}

async function downloadAudio() {
  if (!props.audioUrl) return
  try {
    const resp = await fetch(props.audioUrl)
    const blob = await resp.blob()
    const a = document.createElement("a")
    a.href = URL.createObjectURL(blob)
    a.download = props.audioName ?? t('components.audioEditor.referenceWav')
    a.click()
    URL.revokeObjectURL(a.href)
  } catch {
    // ignore
  }
}

let dragSide: "left" | "right" | null = null

function timeFromClientX(clientX: number): number {
  const el = overlayRef.value
  if (!el) return 0
  const rect = el.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  return ratio * duration.value
}

function onHandleDown(side: "left" | "right", ev: PointerEvent) {
  ev.preventDefault()
  ev.stopPropagation()
  dragSide = side
  ;(ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId)
}

function onHandleMove(ev: PointerEvent) {
  if (!dragSide) return
  ev.preventDefault()
  const t = timeFromClientX(ev.clientX)
  if (dragSide === "left") {
    localStart.value = Math.max(0, Math.min(t, localEnd.value - 0.05))
  } else {
    localEnd.value = Math.min(duration.value, Math.max(t, localStart.value + 0.05))
  }
}

function onHandleUp(ev: PointerEvent) {
  if (dragSide) {
    ;(ev.currentTarget as HTMLElement).releasePointerCapture?.(ev.pointerId)
  }
  dragSide = null
}

function undoTrim() {
  if (clipHistory.value.length === 0) return
  const entry = clipHistory.value.pop()!
  savedTrimStart.value = entry.start
  savedTrimEnd.value = entry.end
  localStart.value = entry.start
  localEnd.value = entry.end
  // 恢复裁剪前的原始音频
  const file = new File([entry.blob], props.audioName ?? t('components.audioEditor.audioWav'), { type: "audio/wav" })
  emit("file", file)
  emit("update:trimStart", entry.start)
  emit("update:trimEnd", entry.end)
}

function cancelTrim() {
  localStart.value = savedTrimStart.value
  localEnd.value = savedTrimEnd.value
  emit("update:trimStart", savedTrimStart.value)
  emit("update:trimEnd", savedTrimEnd.value)
  trimMode.value = false
}

async function confirmClip() {
  if (!ws) return
  if (localStart.value >= localEnd.value) return
  if (localStart.value === savedTrimStart.value && localEnd.value === savedTrimEnd.value) {
    trimMode.value = false
    return
  }
  const { error: toastError } = useToast()
  let prevBlob: Blob | null = null
  try {
    const resp = await fetch(props.audioUrl!)
    prevBlob = await resp.blob()
  } catch { /* skip history on fetch failure */ }
  if (prevBlob) {
    clipHistory.value.push({
      blob: prevBlob,
      start: savedTrimStart.value,
      end: savedTrimEnd.value,
    })
  }
  try {
    const resp = await fetch(props.audioUrl!)
    const blob = await resp.blob()
    const clipped = await trimAudioBlob(blob, localStart.value, localEnd.value)
    const file = new File([clipped], props.audioName ?? t('components.audioEditor.audioWav'), { type: "audio/wav" })
    emit("file", file)
  } catch {
    toastError(t('components.audioEditor.clipFailed'))
    undoTrim()
    return
  }
  emit("update:trimStart", localStart.value)
  emit("update:trimEnd", localEnd.value)
  trimMode.value = false
}

let dragEnterCount = 0

function onDragOver(ev: DragEvent) {
  ev.preventDefault()
}
function onDragEnter() {
  if (dragEnterCount === 0) isDragOver.value = true
  dragEnterCount++
}
function onDragLeave() {
  dragEnterCount--
  if (dragEnterCount <= 0) { dragEnterCount = 0; isDragOver.value = false }
}
function onDrop(ev: DragEvent) {
  ev.preventDefault()
  dragEnterCount = 0
  isDragOver.value = false
  const file = ev.dataTransfer?.files[0]
  if (file) emit("file", file)
}
function onClickUpload() { inputRef.value?.click() }
function onInput(ev: Event) {
  const target = ev.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) emit("file", file)
  target.value = ""
}

watch(trimMode, (val) => {
  if (val) {
    savedTrimStart.value = localStart.value
    savedTrimEnd.value = localEnd.value
    localStart.value = 0
    localEnd.value = duration.value
  }
})

watch(volume, (val) => { if (ws) ws.setVolume(val) })

watch(isDark, () => {
  if (ws) {
    ws.setOptions({
      waveColor: waveformGray(),
      progressColor: primaryColor(),
      cursorColor: primaryColor(),
    })
  }
})

function onVolumeWheel(ev: WheelEvent) {
  const base = Number(volume.value) || 0
  const delta = ev.deltaY > 0 ? -0.05 : 0.05
  volume.value = Math.max(0, Math.min(1, base + delta))
}

watch(
  () => ({ url: props.audioUrl, loading: props.loading }),
  async ({ url, loading }) => {
    if (!url) {
      destroyWaveSurfer()
      currentTime.value = 0
      isPlaying.value = false
      duration.value = 0
      waveLoading.value = false
      trimMode.value = false
      clipHistory.value = []
      return
    }
    if (loading) return
    currentTime.value = 0
    isPlaying.value = false
    await nextTick()
    initWaveSurfer(url)
  },
  { immediate: true },
)

onBeforeUnmount(destroyWaveSurfer)

function formatTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, "0")}`
}
</script>

<template>
  <div class="space-y-2">
    <!-- Loading state -->
    <div
      v-if="loading"
      class="border rounded-lg flex items-center justify-center h-[177px]"
    >
      <div class="flex flex-col items-center gap-2 text-muted-foreground">
        <LoaderCircle class="w-6 h-6 animate-spin" />
        <span class="text-xs">{{ $t('components.audioEditor.decoding') }}</span>
      </div>
    </div>
    <!-- Upload area -->
    <div
      v-else-if="!audioUrl"
      ref="uploadRef"
      class="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors hover:border-primary/50 flex items-center justify-center h-[177px]"
      :class="isDragOver ? 'border-primary bg-primary/5' : 'border-border'"
      @drop.prevent="onDrop"
      @dragover.prevent="onDragOver"
      @dragenter="onDragEnter"
      @dragleave="onDragLeave"
      @click="onClickUpload"
    >
      <input ref="inputRef" type="file" accept="audio/*" class="hidden" @input="onInput" />
      <div class="flex flex-col items-center gap-1.5">
        <Upload class="w-5 h-5 text-muted-foreground" />
        <p class="text-xs text-muted-foreground">{{ $t('components.audioEditor.dropHint') }}</p>
      </div>
    </div>
    <!-- Audio player with waveform -->
    <div v-else class="border rounded-lg bg-card overflow-hidden transition-shadow duration-150 h-[177px] flex flex-col"
      :class="isDragOver ? 'shadow-[0_0_0_2px_hsl(var(--primary))]' : ''"
      @drop.prevent="onDrop"
      @dragover.prevent="onDragOver"
      @dragenter="onDragEnter"
      @dragleave="onDragLeave"
    >
      <!-- Header: name (left) + download / remove (right) -->
      <div class="flex items-center gap-2 px-3 py-2 border-b">
        <span class="text-xs text-foreground truncate min-w-0 flex-1">{{ audioName ?? $t('components.audioEditor.defaultFilename') }}</span>
        <button
          class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          v-tooltip="$t('components.audioEditor.download')"
          @click="downloadAudio"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
        </button>
        <button
          class="shrink-0 text-muted-foreground hover:text-destructive transition-colors"
          v-tooltip="$t('components.audioEditor.remove')"
          @click="removeAudio"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
      <!-- WaveSurfer container + trim overlay + loading overlay -->
      <div class="p-3 flex-1 flex flex-col justify-center">
        <div class="relative">
          <div ref="containerRef" class="audio-editor-waveform relative z-0 w-full" />
          <div v-show="waveLoading"
            class="absolute inset-0 flex items-center justify-center bg-card/80 rounded"
          >
            <div class="flex flex-col items-center gap-2 text-muted-foreground">
              <LoaderCircle class="w-6 h-6 animate-spin" />
              <span class="text-xs">{{ $t('components.audioEditor.loadingWaveform') }}</span>
            </div>
          </div>
          <div
            ref="overlayRef"
            v-show="trimMode && duration > 0"
            class="absolute inset-0 z-10 pointer-events-none select-none"
          >
            <!-- Selected region -->
            <div
              class="absolute top-0 bottom-0 bg-primary/20"
              :style="{ left: leftPct + '%', right: (100 - rightPct) + '%' }"
            />
            <!-- Left handle -->
            <div
              class="absolute top-0 bottom-0 w-4 -translate-x-1/2 flex items-stretch justify-center cursor-ew-resize pointer-events-auto touch-none z-10"
              :style="{ left: leftPct + '%' }"
              @pointerdown="onHandleDown('left', $event)"
              @pointermove="onHandleMove"
              @pointerup="onHandleUp"
              @pointercancel="onHandleUp"
            >
              <span class="w-0.5 bg-primary rounded-full" />
            </div>
            <!-- Right handle -->
            <div
              class="absolute top-0 bottom-0 w-4 -translate-x-1/2 flex items-stretch justify-center cursor-ew-resize pointer-events-auto touch-none z-10"
              :style="{ left: rightPct + '%' }"
              @pointerdown="onHandleDown('right', $event)"
              @pointermove="onHandleMove"
              @pointerup="onHandleUp"
              @pointercancel="onHandleUp"
            >
              <span class="w-0.5 bg-primary rounded-full" />
            </div>
          </div>
        </div>
      </div>
      <!-- Controls bar -->
      <div class="flex items-center gap-2 px-3 py-2 border-t shrink-0 overflow-x-auto">
        <button
          class="w-7 h-7 flex items-center justify-center rounded-full bg-primary text-primary-foreground hover:opacity-90 transition-opacity shrink-0"
          @click="togglePlay"
        >
          <component :is="isPlaying ? Pause : Play" class="w-3.5 h-3.5 fill-current" />
        </button>
        <span class="text-xs font-mono text-muted-foreground whitespace-nowrap tabular-nums shrink-0">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
        <div class="flex items-center gap-1 shrink-0">
          <Volume2 class="w-3 h-3 text-muted-foreground" />
          <input
            v-model.number="volume"
            type="range"
            min="0"
            max="1"
            step="0.01"
            class="w-16 h-1 bg-secondary rounded-full appearance-none cursor-pointer accent-primary"
            @wheel.prevent="onVolumeWheel"
          />
        </div>
        <div class="flex-1" />
        <div class="flex items-center gap-1 shrink-0">
          <template v-if="trimMode">
            <button
              class="w-6 h-6 flex items-center justify-center rounded text-xs text-green-600 hover:bg-green-100 dark:text-green-400 dark:hover:bg-green-950 transition-colors shrink-0"
              v-tooltip="$t('components.audioEditor.confirmClip')"
              @click="confirmClip"
            >
              <Check class="w-3.5 h-3.5" />
            </button>
            <button
              class="w-6 h-6 flex items-center justify-center rounded text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors shrink-0"
              v-tooltip="$t('components.audioEditor.cancel')"
              @click="cancelTrim"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </template>
          <button
            class="w-6 h-6 flex items-center justify-center rounded text-xs transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
            :class="clipHistory.length > 0 ? 'text-muted-foreground hover:text-foreground hover:bg-accent' : 'text-muted-foreground/30'"
            v-tooltip="$t('components.audioEditor.undoClip')"
            :disabled="clipHistory.length === 0"
            @click="undoTrim"
          >
            <Undo2 class="w-3.5 h-3.5" />
          </button>
          <button
            class="w-6 h-6 flex items-center justify-center rounded text-xs transition-colors shrink-0"
            :class="trimMode ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-accent'"
            v-tooltip="$t('components.audioEditor.clipMode')"
            @click="trimMode = !trimMode"
          >
            <Scissors class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.audio-editor-waveform ::part(progress) {
  contain: layout paint;
  will-change: width;
}

.audio-editor-waveform ::part(cursor) {
  will-change: left, transform;
}
</style>
