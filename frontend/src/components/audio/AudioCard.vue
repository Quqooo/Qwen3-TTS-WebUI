<script setup lang="ts">
import { ref, onBeforeUnmount } from "vue"
import { Play, Pause, Volume2, X } from "@lucide/vue"
import { useUserConfig } from "../../composables/useUserConfig"

const props = defineProps<{
  audioUrl: string
  audioName: string
}>()

const emit = defineEmits<{
  file: [file: File | null]
}>()

const { globalVolume } = useUserConfig()

const audioRef = ref<HTMLAudioElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
const isPlaying = ref(false)
const volume = ref(globalVolume.value / 100)
const progress = ref(0)
let dragCounter = 0
const isDragOver = ref(false)
let rafId = 0

function tickProgress() {
  const el = audioRef.value
  if (el && el.duration) {
    progress.value = el.currentTime / el.duration
    rafId = requestAnimationFrame(tickProgress)
  } else {
    progress.value = 0
  }
}
function startProgress() {
  cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(tickProgress)
}
function stopProgress() {
  cancelAnimationFrame(rafId)
  rafId = 0
}

function togglePlay() {
  const el = audioRef.value
  if (!el) return
  if (isPlaying.value) {
    el.pause()
  } else {
    el.play()
  }
}

onBeforeUnmount(stopProgress)

function removeAudio() {
  emit("file", null)
}

function onVolumeWheel(ev: WheelEvent) {
  ev.preventDefault()
  const delta = ev.deltaY > 0 ? -0.05 : 0.05
  volume.value = Math.max(0, Math.min(1, volume.value + delta))
  const el = audioRef.value
  if (el) el.volume = volume.value
}

function onDragOver(ev: DragEvent) { ev.preventDefault() }
function onDragEnter() {
  if (dragCounter === 0) isDragOver.value = true
  dragCounter++
}
function onDragLeave() {
  dragCounter--
  if (dragCounter <= 0) { dragCounter = 0; isDragOver.value = false }
}
function onDrop(ev: DragEvent) {
  ev.preventDefault()
  dragCounter = 0
  isDragOver.value = false
  const file = ev.dataTransfer?.files[0]
  if (file) emit("file", file)
}
function onClickUpload() { inputRef.value?.click() }
function onInput(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  if (file) emit("file", file);
  (ev.target as HTMLInputElement).value = ""
}
</script>

<template>
  <div
    class="relative border rounded-lg bg-card px-3 py-2 transition-shadow duration-150 overflow-hidden"
    :class="isDragOver ? 'shadow-[0_0_0_2px_hsl(var(--primary))]' : ''"
    @drop.prevent="onDrop"
    @dragover.prevent="onDragOver"
    @dragenter="onDragEnter"
    @dragleave="onDragLeave"
    @click="onClickUpload"
  >
    <div
      class="absolute inset-y-0 left-0 bg-primary/15 pointer-events-none transition-[width] duration-300 ease-out"
      :class="{ 'duration-0': isPlaying }"
      :style="{ width: (progress * 100) + '%' }"
    />
    <input ref="inputRef" type="file" accept="audio/*" class="hidden" @input="onInput" />
    <div class="relative flex items-center gap-2 text-xs leading-none z-10">
      <button
        class="w-7 h-7 flex items-center justify-center rounded-full bg-primary text-primary-foreground hover:opacity-90 transition-opacity shrink-0"
        @click.stop="togglePlay"
      >
        <component :is="isPlaying ? Pause : Play" class="w-3.5 h-3.5 fill-current" />
      </button>
      <span class="truncate min-w-0 flex-1">{{ audioName }}</span>
      <span
        class="flex items-center gap-0.5 text-muted-foreground shrink-0 cursor-ns-resize select-none"
        @wheel.stop.prevent="onVolumeWheel"
        v-tooltip="$t('components.audioCard.scrollForVolume')"
      >
        <Volume2 class="w-3 h-3" />
        {{ Math.round(volume * 100) }}%
      </span>
      <button class="shrink-0 flex items-center justify-center text-muted-foreground hover:text-destructive transition-colors" @click.stop="removeAudio">
        <X class="w-4 h-4" />
      </button>
    </div>
    <audio
      ref="audioRef"
      :src="audioUrl"
      :volume="volume"
      preload="auto"
      class="hidden"
      @ended="isPlaying = false; stopProgress(); progress = 0"
      @play="isPlaying = true; startProgress()"
      @pause="isPlaying = false; stopProgress()"
    />
  </div>
</template>
