<script setup lang="ts">
import { ref } from "vue"
import { WandSparkles, Square, SquareX, RotateCcw, Settings } from "@lucide/vue"
import AppSelect from "../common/AppSelect.vue"
import { FORMAT_OPTIONS, SAMPLE_RATE_OPTIONS } from "../../constants/options"

const props = defineProps<{
  generating: boolean
  paused: boolean
  canRetry: boolean
}>()

const emit = defineEmits<{
  "update:format": [value: string]
  "update:sampleRate": [value: string]
  "update:gain": [value: number]
  toggleGenerate: []
  stopGenerate: []
  retryFailed: []
  openMoreConfig: []
}>()

const format = ref("wav")
const sampleRate = ref("24000")
const gain = ref(0)

const formatOptions = FORMAT_OPTIONS
const sampleRateOptions = SAMPLE_RATE_OPTIONS

function onGenerateClick() {
  emit("toggleGenerate")
}
</script>

<template>
  <div class="border rounded-xl bg-card p-3 flex flex-col gap-[11px] overflow-y-auto min-h-0">
    <div class="grid grid-cols-3 items-start gap-[7px]">
      <div class="min-w-0 space-y-1">
        <div class="flex h-4 items-center text-xs text-muted-foreground">{{ $t('components.batchGenerationControls.format') }}</div>
        <AppSelect class="[&_button]:h-10" v-model="format" :options="formatOptions" @update:model-value="emit('update:format', format)" />
      </div>
      <div class="min-w-0 space-y-1">
        <div class="flex h-4 items-center text-xs text-muted-foreground">{{ $t('components.batchGenerationControls.sampleRate') }}</div>
        <AppSelect class="[&_button]:h-10" v-model="sampleRate" :options="sampleRateOptions" @update:model-value="emit('update:sampleRate', sampleRate)" />
      </div>
      <div class="min-w-0 space-y-1">
        <div class="flex h-4 items-center text-xs text-muted-foreground">{{ $t('components.batchGenerationControls.gainDb') }}</div>
        <input
          v-model.number="gain"
          type="number"
          step="0.1"
          min="-10"
          max="10"
          class="h-10 w-full px-3 py-2 text-sm rounded-lg bg-background border"
          @wheel.prevent="(e: WheelEvent) => { const d = e.deltaY > 0 ? -0.1 : 0.1; gain = Number((Math.max(-10, Math.min(10, gain + d))).toFixed(1)) }"
          @input="emit('update:gain', gain)"
        />
      </div>
    </div>

    <button
      class="w-full flex items-center justify-center gap-1.5 px-4 py-3 text-sm font-semibold rounded-xl border hover:bg-accent transition-colors"
      @click="emit('openMoreConfig')"
    >
      <Settings class="w-4 h-4" /> {{ $t('components.batchGenerationControls.moreConfig') }}
    </button>

    <div class="relative">
      <button
        class="btn-generate"
        :class="paused
          ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/20'
          : generating
            ? 'bg-destructive text-destructive-foreground shadow-lg shadow-destructive/20'
            : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/20'"
        @click="onGenerateClick"
      >
        <span class="relative z-10 flex items-center gap-2">
          <component :is="generating ? Square : WandSparkles" class="w-4 h-4" />
          <template v-if="!generating && !paused">{{ $t('components.batchGenerationControls.batchGenerate') }}</template>
          <template v-else-if="!generating && paused">{{ $t('components.batchGenerationControls.resume') }}</template>
          <template v-else>{{ $t('components.batchGenerationControls.pause') }}</template>
        </span>
      </button>
    </div>

    <div class="flex gap-2">
      <button
        class="flex-1 flex items-center justify-center gap-1.5 px-4 py-3 text-sm font-semibold rounded-xl border transition-colors"
        :class="generating || paused
          ? 'bg-destructive/10 text-destructive hover:bg-destructive/20 border-destructive/20'
          : 'opacity-30 cursor-not-allowed'"
        :disabled="!generating && !paused"
        @click="emit('stopGenerate')"
      >
        <SquareX class="w-4 h-4" /> {{ $t('components.batchGenerationControls.abort') }}
      </button>
      <button
        class="flex-1 flex items-center justify-center gap-1.5 px-4 py-3 text-sm font-semibold rounded-xl border transition-colors"
        :class="canRetry
          ? 'hover:bg-accent'
          : 'opacity-30 cursor-not-allowed'"
        :disabled="!canRetry"
        @click="emit('retryFailed')"
      >
        <RotateCcw class="w-3 h-3" /> {{ $t('components.batchGenerationControls.retryFailed') }}
      </button>
    </div>
  </div>
</template>
