<script setup lang="ts">
import { Square, WandSparkles } from "@lucide/vue"
import AppSelect from "../common/AppSelect.vue"
import { FORMAT_OPTIONS, SAMPLE_RATE_OPTIONS } from "../../constants/options"

const props = defineProps<{
  i18nPrefix: string
  isGenerating: boolean
  streamingEnabled: boolean
  outputFormat: string
  sampleRate: string
  gain: number
}>()

const emit = defineEmits<{
  "update:outputFormat": [val: string]
  "update:sampleRate": [val: string]
  "update:gain": [val: number]
  generate: []
  stop: []
}>()

const formatOptions = FORMAT_OPTIONS
const sampleRateOptions = SAMPLE_RATE_OPTIONS

function onGainWheel(e: WheelEvent) {
  const d = e.deltaY > 0 ? -0.1 : 0.1
  const next = Number((Math.max(-10, Math.min(10, props.gain + d))).toFixed(1))
  emit("update:gain", next)
}
</script>

<template>
  <div class="card space-y-3">
    <div class="grid grid-cols-3 gap-2">
      <div class="space-y-1.5">
        <div class="text-xs text-muted-foreground">{{ $t(`${i18nPrefix}.format`) }}</div>
        <AppSelect
          :model-value="streamingEnabled ? 'pcm' : outputFormat"
          :options="formatOptions"
          :disabled="streamingEnabled"
          @update:model-value="$emit('update:outputFormat', $event)"
        />
      </div>
      <div class="space-y-1.5">
        <div class="text-xs text-muted-foreground">{{ $t(`${i18nPrefix}.sampleRate`) }}</div>
        <AppSelect :model-value="sampleRate" :options="sampleRateOptions" @update:model-value="$emit('update:sampleRate', $event)" />
      </div>
      <div class="space-y-1.5">
        <label for="synthesis-output-gain" class="text-xs text-muted-foreground">{{ $t(`${i18nPrefix}.gainDb`) }}</label>
        <input
          id="synthesis-output-gain"
          name="synthesis_output_gain"
          type="number"
          step="0.1"
          min="-10"
          max="10"
          :value="gain"
          class="w-full px-2 py-1.5 text-sm"
          @wheel.prevent="onGainWheel"
          @input="$emit('update:gain', parseFloat(($event.target as HTMLInputElement).value) || 0)"
        />
      </div>
    </div>

    <button
      class="btn-generate"
      :class="isGenerating
        ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-lg shadow-destructive/20'
        : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/20'"
      @click="isGenerating ? $emit('stop') : $emit('generate')"
    >
      <component :is="isGenerating ? Square : WandSparkles" class="w-4 h-4" />
      {{ isGenerating ? $t(`${i18nPrefix}.stop`) : $t(`${i18nPrefix}.generate`) }}
    </button>
  </div>
</template>
