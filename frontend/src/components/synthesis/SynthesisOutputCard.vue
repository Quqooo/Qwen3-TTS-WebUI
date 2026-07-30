<script setup lang="ts">
import { Download, Save } from "@lucide/vue"
import AudioPlayer from "../audio/AudioPlayer.vue"

defineProps<{
  i18nPrefix: string
  resultAudioUrl: string | null
  resultDuration?: number
  streamingEnabled: boolean
  isGenerating: boolean
  genElapsed: number
  genTime?: number
  rtf?: number
}>()

defineEmits<{
  download: []
  saveVoice: []
}>()
</script>

<template>
  <div class="card">
    <h3 class="text-sm font-medium mb-3">{{ $t(`${i18nPrefix}.outputAudio`) }}</h3>

    <AudioPlayer
      :audio-url="resultAudioUrl"
      :duration="resultDuration"
      :streaming="streamingEnabled"
      :is-generating="isGenerating && !resultAudioUrl"
    />

    <div class="flex items-center gap-2 mt-2">
      <div class="info-box">
        <span class="text-muted-foreground">{{ $t(`${i18nPrefix}.generationTime`) }}</span>
        <span class="font-mono font-medium" :class="isGenerating || genTime !== undefined ? 'text-foreground' : 'text-muted-foreground/30'">
          {{ ((isGenerating ? genElapsed : genTime) ?? 0).toFixed(2) }}s
        </span>
      </div>
      <div class="info-box">
        <span class="text-muted-foreground">{{ $t(`${i18nPrefix}.rtf`) }}</span>
        <span class="font-mono font-medium" :class="(isGenerating && !streamingEnabled) || (!isGenerating && rtf === undefined) ? 'text-muted-foreground/30' : 'text-foreground'">
          {{ (rtf ?? 0).toFixed(3) }}
        </span>
      </div>
    </div>

    <div class="flex gap-2 mt-3">
      <button
        class="btn-action"
        :class="resultAudioUrl ? 'btn-action-active' : 'btn-action-disabled'"
        :disabled="!resultAudioUrl"
        @click="$emit('download')"
      >
        <Download class="w-3.5 h-3.5" /> {{ $t(`${i18nPrefix}.download`) }}
      </button>
      <button
        class="btn-action"
        :class="resultAudioUrl ? 'btn-action-active' : 'btn-action-disabled'"
        :disabled="!resultAudioUrl"
        @click="$emit('saveVoice')"
      >
        <Save class="w-3.5 h-3.5" /> {{ $t(`${i18nPrefix}.saveVoice`) }}
      </button>
    </div>
  </div>
</template>
