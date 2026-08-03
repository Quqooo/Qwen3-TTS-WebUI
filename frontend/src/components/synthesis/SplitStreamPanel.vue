<script setup lang="ts">
import { computed } from "vue"
import type { Component } from "vue"
import { CircleHelp, Scissors, Radio } from "@lucide/vue"
import SegmentPanel from "./SegmentPanel.vue"
import type { Segment } from "./SegmentPanel.vue"
import { t } from "../../lang"

withDefaults(defineProps<{
  modelValue: string
  splitChars?: string
  emitEvery?: number
  decodeWindow?: number
  overlapSamples?: number
  maxFrames?: number
  chunkSize?: number
  parityMode?: boolean
  fasterBranch?: boolean
  allowParityMode?: boolean
}>(), {
  splitChars: t('components.splitStreamPanel.defaultSplitChars'),
  emitEvery: 8,
  decodeWindow: 80,
  overlapSamples: 0,
  maxFrames: 10000,
  chunkSize: 12,
  parityMode: false,
  fasterBranch: false,
  allowParityMode: false,
})

const emit = defineEmits<{
  (e: "update:modelValue", val: string): void
  (e: "update:splitChars", val: string): void
  (e: "update:emitEvery", val: number): void
  (e: "update:decodeWindow", val: number): void
  (e: "update:overlapSamples", val: number): void
  (e: "update:maxFrames", val: number): void
  (e: "update:chunkSize", val: number): void
  (e: "update:parityMode", val: boolean): void
}>()

const segments = computed<Segment[]>(() => [
  { value: "split", label: t('components.splitStreamPanel.split'), icon: Scissors as unknown as Component },
  { value: "stream", label: t('components.splitStreamPanel.stream'), icon: Radio as unknown as Component },
])
</script>

<template>
  <SegmentPanel
    :model-value="modelValue"
    :segments="segments"
    show-divider
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #split>
      <div class="space-y-1">
        <label class="text-[10px] text-muted-foreground">{{ $t('components.splitStreamPanel.splitChars') }}</label>
        <input
          type="text"
          :value="splitChars"
          class="w-full px-2 py-1.5 text-xs font-mono"
          placeholder='.。!！?？\n'
          @input="emit('update:splitChars', ($event.target as HTMLInputElement).value)"
        />
      </div>
    </template>
    <template #stream>
      <div v-if="fasterBranch" class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-1.5 text-xs whitespace-nowrap">
          <span class="text-muted-foreground">{{ $t('components.splitStreamPanel.chunk') }}</span>
          <input
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            :value="chunkSize"
            :size="String(chunkSize).length || 2"
            class="px-1.5 py-1 text-xs border rounded bg-background transition-colors duration-150 focus:border-primary focus:ring-0"
            @input="emit('update:chunkSize', parseInt(($event.target as HTMLInputElement).value) || 12)"
          />
        </div>
        <div v-if="allowParityMode" class="flex items-center gap-1.5 text-xs whitespace-nowrap">
          <span class="flex items-center gap-1 text-muted-foreground">
            {{ $t('components.splitStreamPanel.parityMode') }}
            <CircleHelp class="w-3.5 h-3.5" v-tooltip="$t('components.splitStreamPanel.parityTooltip')" />
          </span>
          <button
            type="button"
            role="switch"
            :aria-checked="parityMode"
            class="relative inline-flex h-4 w-7 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200"
            :class="parityMode ? 'bg-primary' : 'bg-secondary'"
            @click="emit('update:parityMode', !parityMode)"
          >
            <span class="pointer-events-none block h-3 w-3 rounded-full bg-white shadow transition-transform duration-200" :class="parityMode ? 'translate-x-3' : 'translate-x-0'" />
          </button>
        </div>
      </div>
      <div v-else class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-1.5 text-xs whitespace-nowrap">
          <span class="text-muted-foreground">{{ $t('components.splitStreamPanel.emit') }}</span>
          <input
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            :value="emitEvery"
            :size="String(emitEvery).length || 1"
            class="px-1.5 py-1 text-xs border rounded bg-background transition-colors duration-150 focus:border-primary focus:ring-0"
            @input="emit('update:emitEvery', parseInt(($event.target as HTMLInputElement).value) || 8)"
          />
        </div>
        <div class="flex items-center gap-1.5 text-xs whitespace-nowrap">
          <span class="text-muted-foreground">{{ $t('components.splitStreamPanel.window') }}</span>
          <input
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            :value="decodeWindow"
            :size="String(decodeWindow).length || 2"
            class="px-1.5 py-1 text-xs border rounded bg-background transition-colors duration-150 focus:border-primary focus:ring-0"
            @input="emit('update:decodeWindow', parseInt(($event.target as HTMLInputElement).value) || 80)"
          />
        </div>
        <div class="flex items-center gap-1.5 text-xs whitespace-nowrap">
          <span class="text-muted-foreground">{{ $t('components.splitStreamPanel.overlap') }}</span>
          <input
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            :value="overlapSamples"
            :size="String(overlapSamples).length || 1"
            class="px-1.5 py-1 text-xs border rounded bg-background transition-colors duration-150 focus:border-primary focus:ring-0"
            @input="emit('update:overlapSamples', parseInt(($event.target as HTMLInputElement).value) || 0)"
          />
        </div>
        <div class="flex items-center gap-1.5 text-xs whitespace-nowrap">
          <span class="text-muted-foreground">{{ $t('components.splitStreamPanel.maxFrames') }}</span>
          <input
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            :value="maxFrames"
            :size="String(maxFrames).length || 4"
            class="px-1.5 py-1 text-xs border rounded bg-background transition-colors duration-150 focus:border-primary focus:ring-0"
            @input="emit('update:maxFrames', parseInt(($event.target as HTMLInputElement).value) || 10000)"
          />
        </div>
      </div>
    </template>
  </SegmentPanel>
</template>