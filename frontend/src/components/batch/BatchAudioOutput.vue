<script setup lang="ts">
import { Download, Archive, FileText } from "@lucide/vue"
import AudioPlayer from "../audio/AudioPlayer.vue"

defineProps<{
  generationTime: string
  rtf: string
  finalAudioUrl?: string
  subtitles?: string
  hasZip?: boolean
  hasSubtitles?: boolean
}>()

const emit = defineEmits<{
  downloadZip: []
  exportSubtitles: []
  downloadFinal: []
}>()
</script>

<template>
  <div class="border rounded-xl bg-card p-3 flex flex-col gap-2 h-full overflow-y-auto min-h-0">
    <h3 class="text-sm font-medium flex items-center">{{ $t('components.batchAudioOutput.title') }}</h3>

    <AudioPlayer :audio-url="finalAudioUrl" :subtitles="subtitles" class="shrink-0" />

    <div class="flex items-center gap-2 shrink-0">
      <div class="info-box">
        <span class="text-muted-foreground">{{ $t('components.batchAudioOutput.genTime') }}</span>
        <span class="font-mono font-medium" :class="generationTime === '--:--' ? 'text-muted-foreground/30' : 'text-foreground'">{{ generationTime }}</span>
      </div>
      <div class="info-box">
        <span class="text-muted-foreground">{{ $t('components.batchAudioOutput.rtf') }}</span>
        <span class="font-mono font-medium" :class="rtf === '--' ? 'text-muted-foreground/30' : 'text-foreground'">{{ rtf }}</span>
      </div>
    </div>

    <div class="flex flex-col gap-1">
      <div class="flex gap-2">
        <button
          class="flex-1 flex items-center justify-center gap-1.5 px-4 py-3 text-sm font-semibold rounded-xl border transition-colors"
          :class="hasZip ? 'hover:bg-accent' : 'opacity-30 cursor-not-allowed'"
          :disabled="!hasZip"
          @click="emit('downloadZip')"
        >
          <Archive class="w-4 h-4" /> {{ $t('components.batchAudioOutput.downloadZip') }}
        </button>
        <button
          class="flex-1 flex items-center justify-center gap-1.5 px-4 py-3 text-sm font-semibold rounded-xl border transition-colors"
          :class="hasSubtitles ? 'hover:bg-accent' : 'opacity-30 cursor-not-allowed'"
          :disabled="!hasSubtitles"
          @click="emit('exportSubtitles')"
        >
          <FileText class="w-4 h-4" /> {{ $t('components.batchAudioOutput.exportSubtitle') }}
        </button>
      </div>
      <button
        class="flex items-center justify-center gap-1.5 px-4 py-3 text-sm font-semibold rounded-xl border transition-colors"
        :class="finalAudioUrl ? 'hover:bg-accent' : 'opacity-30 cursor-not-allowed'"
        :disabled="!finalAudioUrl"
        @click="emit('downloadFinal')"
      >
        <Download class="w-4 h-4" /> {{ $t('components.batchAudioOutput.downloadFinal') }}
      </button>
    </div>
  </div>
</template>
