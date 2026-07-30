<script setup lang="ts">
import { ref } from "vue"
import type { GenerationParams } from "../../types"
import { ChevronDown, ChevronUp, Settings2 } from "@lucide/vue"

const props = defineProps<{
  modelValue: GenerationParams
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: GenerationParams): void
}>()

const open = ref(false)

function update(key: keyof GenerationParams, value: number | boolean | undefined) {
  emit("update:modelValue", { ...props.modelValue, [key]: value })
}

function intFallback(v: string, fallback: number) {
  const n = parseInt(v)
  return Number.isNaN(n) ? fallback : n
}

function floatFallback(v: string, fallback: number) {
  const n = parseFloat(v)
  return Number.isNaN(n) ? fallback : n
}
</script>

<template>
  <div class="border rounded-xl bg-card transition-all duration-200">
    <button
      class="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-accent/30 rounded-xl transition-colors duration-150"
      @click="open = !open"
    >
      <span class="flex items-center gap-2">
        <Settings2 class="w-4 h-4 text-muted-foreground" />
        {{ $t('components.generationParams.title') }}
      </span>
      <component :is="open ? ChevronUp : ChevronDown" class="w-4 h-4 text-muted-foreground" />
    </button>
    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0 max-h-0"
      enter-to-class="opacity-100 max-h-[600px]"
      leave-active-class="transition-all duration-150 ease-in"
      leave-from-class="opacity-100 max-h-[600px]"
      leave-to-class="opacity-0 max-h-0"
    >
      <div v-if="open" class="overflow-hidden">
        <div class="px-4 pb-4 space-y-3 border-t pt-3">
          <div class="grid grid-cols-2 gap-x-6 gap-y-3">
            <div class="space-y-1.5">
              <label class="text-xs text-muted-foreground flex items-center gap-1.5" v-tooltip="$t('components.generationParams.temperatureTooltip')">
                <span>{{ $t('components.generationParams.temperature') }}</span>
                <span class="font-mono font-medium tabular-nums">{{ (modelValue.temperature ?? 0.9).toFixed(1) }}</span>
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                :value="modelValue.temperature ?? 0.9"
                class="w-full h-1.5 rounded-full cursor-pointer accent-primary"
                @input="update('temperature', parseFloat(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="space-y-1.5">
              <label class="text-xs text-muted-foreground flex items-center gap-1.5 empty-label" v-tooltip="$t('components.generationParams.topKTooltip')">
                <span>{{ $t('components.generationParams.topK') }}</span><span class="font-mono font-medium tabular-nums">{{ modelValue.top_k ?? 50 }}</span>
              </label>
              <input
                type="number"
                min="0"
                max="200"
                :value="modelValue.top_k ?? 50"
                class="w-full px-3 py-1.5 text-sm"
                @input="update('top_k', intFallback(($event.target as HTMLInputElement).value, 50))"
              />
            </div>
            <div class="space-y-1.5">
              <label class="text-xs text-muted-foreground flex items-center gap-1.5" v-tooltip="$t('components.generationParams.topPTooltip')">
                <span>{{ $t('components.generationParams.topP') }}</span>
                <span class="font-mono font-medium tabular-nums">{{ (modelValue.top_p ?? 1.0).toFixed(2) }}</span>
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                :value="modelValue.top_p ?? 1.0"
                class="w-full h-1.5 rounded-full cursor-pointer accent-primary"
                @input="update('top_p', parseFloat(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="space-y-1.5">
              <label class="text-xs text-muted-foreground flex items-center gap-1.5" v-tooltip="$t('components.generationParams.repPenaltyTooltip')">
                <span>{{ $t('components.generationParams.repPenalty') }}</span>
                <span class="font-mono font-medium tabular-nums">{{ (modelValue.repetition_penalty ?? 1.05).toFixed(2) }}</span>
              </label>
              <input
                type="range"
                min="1"
                max="2"
                step="0.05"
                :value="modelValue.repetition_penalty ?? 1.05"
                class="w-full h-1.5 rounded-full cursor-pointer accent-primary"
                @input="update('repetition_penalty', parseFloat(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>

          <div class="border-t pt-3 space-y-3">
            <div class="text-xs font-medium text-muted-foreground">{{ $t('components.generationParams.subtalkerSection') }}</div>
            <div class="grid grid-cols-3 gap-3">
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.subTopKTooltip')">{{ $t('components.generationParams.subTopK') }}</label>
                <input
                  type="number"
                  min="0"
                  max="200"
                  :value="modelValue.subtalker_top_k ?? 50"
                  class="w-full px-2 py-1.5 text-xs"
                  @input="update('subtalker_top_k', intFallback(($event.target as HTMLInputElement).value, 50))"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.subTopPTooltip')">{{ $t('components.generationParams.subTopP') }}</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  :value="modelValue.subtalker_top_p ?? 1.0"
                  class="w-full px-2 py-1.5 text-xs"
                  @input="update('subtalker_top_p', floatFallback(($event.target as HTMLInputElement).value, 1.0))"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.subTemperatureTooltip')">{{ $t('components.generationParams.subTemperature') }}</label>
                <input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  :value="modelValue.subtalker_temperature ?? 0.9"
                  class="w-full px-2 py-1.5 text-xs"
                  @input="update('subtalker_temperature', floatFallback(($event.target as HTMLInputElement).value, 0.9))"
                />
              </div>
            </div>
          </div>

          <div class="space-y-1.5">
            <label class="text-xs text-muted-foreground" v-tooltip="$t('components.generationParams.maxNewTokensTooltip')">{{ $t('components.generationParams.maxNewTokens') }}</label>
            <input
              type="number"
              min="1"
              max="32767"
              step="1"
              :value="modelValue.max_new_tokens ?? 8192"
              class="w-full px-3 py-1.5 text-sm"
              @input="update('max_new_tokens', intFallback(($event.target as HTMLInputElement).value, 8192))"
            />
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
