<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from "vue"
import WaveSurfer from "wavesurfer.js"
import { primaryColor, waveformGray } from "../../theme"
import { useTheme } from "../../composables/useTheme"
import {
  getBatchWaveform,
  getBatchWaveformRevision,
  setBatchWaveform,
} from "../../utils/batchWaveformCache"

const { isDark } = useTheme()

const props = withDefaults(defineProps<{
  rowId: string
  audioUrl?: string
  progress?: number
}>(), {
  progress: 0,
})

const emit = defineEmits<{
  (e: "seek", progress: number): void
}>()

const wrapper = ref<HTMLDivElement | null>(null)
const container = ref<HTMLDivElement | null>(null)

let ws: WaveSurfer | null = null
let initToken = 0

const progressPct = computed(() => Math.min(1, Math.max(0, props.progress)))

function destroy() {
  if (ws) { ws.destroy(); ws = null }
}

async function init(rowId: string, url: string) {
  const token = ++initToken
  const cacheRevision = getBatchWaveformRevision(rowId)
  destroy()
  await nextTick()
  await new Promise(r => requestAnimationFrame(r))
  if (token !== initToken || !wrapper.value) return

  const cached = getBatchWaveform(rowId)
  const instance = WaveSurfer.create({
    container: wrapper.value,
    waveColor: waveformGray(),
    progressColor: primaryColor(),
    height: 24,
    barWidth: 3,
    barGap: 1,
    barRadius: 1,
    normalize: true,
    cursorWidth: 0,
    interact: false,
  })
  ws = instance
  instance.on("ready", () => {
    if (token !== initToken || ws !== instance) return
    instance.seekTo(props.progress)
    if (!cached && getBatchWaveformRevision(rowId) === cacheRevision) {
      setBatchWaveform(rowId, {
        peaks: instance.exportPeaks({ channels: 1, maxLength: 2000, precision: 1000 }),
        duration: instance.getDuration(),
      })
    }
  })
  try {
    await instance.load(url, cached?.peaks, cached?.duration)
  } catch {
    // Audio may be replaced or revoked while a virtual row is being recycled.
  }
}

watch(
  () => [props.rowId, props.audioUrl] as const,
  ([rowId, url]) => {
    if (url) init(rowId, url)
    else { initToken++; destroy() }
  },
  { immediate: true },
)

watch(() => props.progress, (val) => {
  if (ws) ws.seekTo(val)
})

watch(isDark, () => {
  if (ws) {
    ws.setOptions({
      waveColor: waveformGray(),
      progressColor: primaryColor(),
    })
  }
})

let dragLock = false

function seekFromEvent(ev: MouseEvent) {
  const el = container.value
  if (!el) return 0
  const rect = el.getBoundingClientRect()
  const x = ev.clientX - rect.left
  return Math.min(1, Math.max(0, x / rect.width))
}

function onMouseDown(ev: MouseEvent) {
  dragLock = true
  emit("seek", seekFromEvent(ev))
  window.addEventListener("mousemove", onMouseMove)
  window.addEventListener("mouseup", onMouseUp)
}

function onMouseMove(ev: MouseEvent) {
  if (!dragLock) return
  emit("seek", seekFromEvent(ev))
}

function onMouseUp() {
  dragLock = false
  window.removeEventListener("mousemove", onMouseMove)
  window.removeEventListener("mouseup", onMouseUp)
}

onUnmounted(() => {
  initToken++
  destroy()
  window.removeEventListener("mousemove", onMouseMove)
  window.removeEventListener("mouseup", onMouseUp)
})
</script>

<template>
  <div
    ref="container"
    class="bg-secondary rounded overflow-hidden relative cursor-pointer"
    style="height: 24px;"
    @mousedown.prevent="onMouseDown"
  >
    <div ref="wrapper" class="absolute inset-0 pointer-events-none" />
    <div
      class="absolute inset-y-0 left-0 bg-primary/15 pointer-events-none"
      :style="{ width: `${progressPct * 100}%` }"
    />
  </div>
</template>
