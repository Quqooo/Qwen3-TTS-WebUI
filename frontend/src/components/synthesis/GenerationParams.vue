<script setup lang="ts">
import { computed, ref } from "vue"
import { ChevronDown, ChevronUp, CircleHelp, Settings2 } from "@lucide/vue"
import AppSelect from "../common/AppSelect.vue"
import type { GenerationParamsConfig } from "../../types"
import { useModelStore } from "../../stores/model"
import { t } from "../../lang"

const props = withDefaults(defineProps<{
  modelValue: GenerationParamsConfig
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  (e: "update:modelValue", val: GenerationParamsConfig): void
}>()

const open = ref(false)
const modelStore = useModelStore()
const isFasterBranch = computed(() => modelStore.isFasterBranch)
const customParamsEnabled = computed(() => !props.disabled && props.modelValue.enabled)

const samplingOptions = computed(() => [
  { value: "true", label: t("components.generationParams.randomSampling") },
  { value: "false", label: t("components.generationParams.greedyDecoding") },
])
const triStateOptions = computed(() => [
  { value: "default", label: t("components.generationParams.defaultMode") },
  { value: "true", label: t("components.generationParams.enabledMode") },
  { value: "false", label: t("components.generationParams.disabledMode") },
])

function patch(partial: Partial<GenerationParamsConfig>) {
  if (props.disabled) return
  emit("update:modelValue", { ...props.modelValue, ...partial })
}

function setSampling(key: "do_sample" | "subtalker_dosample", value: string) {
  patch({ [key]: value === "true" } as Partial<GenerationParamsConfig>)
}

function setTriState(value: string) {
  patch({ non_streaming_mode: value === "default" ? undefined : value === "true" })
}

function setNumber(
  key: keyof GenerationParamsConfig,
  raw: string,
  min: number,
  max: number,
  integer = false,
) {
  if (!raw.trim()) {
    patch({ [key]: undefined } as Partial<GenerationParamsConfig>)
    return
  }
  const parsed = integer ? Number.parseInt(raw, 10) : Number.parseFloat(raw)
  if (!Number.isFinite(parsed)) return
  const value = Math.min(max, Math.max(min, parsed))
  const normalized = integer ? Math.trunc(value) : Number(value.toFixed(4))
  patch({ [key]: normalized } as Partial<GenerationParamsConfig>)
}

function valueOf(key: keyof GenerationParamsConfig): string {
  const value = props.modelValue[key]
  return typeof value === "number" ? String(value) : ""
}

function samplingValue(value: boolean | undefined): string {
  return value === false ? "false" : "true"
}

function triStateValue(value: boolean | undefined): string {
  return value === undefined ? "default" : String(value)
}
</script>

<template>
  <div class="border rounded-xl bg-card transition-all duration-200">
    <div
      role="button"
      tabindex="0"
      class="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-accent/30 rounded-xl transition-colors duration-150"
      @click="open = !open"
      @keydown.enter="open = !open"
      @keydown.space.prevent="open = !open"
    >
      <span class="flex items-center gap-2">
        <Settings2 class="w-4 h-4 text-muted-foreground" />
        {{ $t('components.generationParams.title') }}
        <CircleHelp class="w-3.5 h-3.5 text-muted-foreground" v-tooltip="$t('components.generationParams.disabledTooltip')" />
        <button
          type="button"
          role="switch"
          :aria-checked="modelValue.enabled"
          class="relative inline-flex h-4 w-7 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200"
          :class="modelValue.enabled ? 'bg-primary cursor-pointer' : 'bg-secondary cursor-pointer'"
          :disabled="disabled"
          @click.stop="patch({ enabled: !modelValue.enabled })"
        >
          <span class="pointer-events-none block h-3 w-3 rounded-full bg-white shadow transition-transform duration-200" :class="modelValue.enabled ? 'translate-x-3' : 'translate-x-0'" />
        </button>
      </span>
      <component :is="open ? ChevronUp : ChevronDown" class="w-4 h-4 text-muted-foreground" />
    </div>

    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0 max-h-0"
      enter-to-class="opacity-100 max-h-[900px]"
      leave-active-class="transition-all duration-150 ease-in"
      leave-from-class="opacity-100 max-h-[900px]"
      leave-to-class="opacity-0 max-h-0"
    >
      <div v-if="open" class="overflow-hidden">
        <div class="px-4 pb-4 space-y-4 border-t pt-3" :class="!customParamsEnabled ? 'opacity-60' : ''">
          <section class="space-y-3">
            <div class="text-xs font-medium text-muted-foreground">{{ $t('components.generationParams.talkerSection') }}</div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.doSample') }}</label>
                <AppSelect
                  compact
                  :model-value="samplingValue(modelValue.do_sample)"
                  :options="samplingOptions"
                  :disabled="!customParamsEnabled"
                  @update:model-value="setSampling('do_sample', $event)"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.repPenaltyTooltip')">{{ $t('components.generationParams.repPenalty') }}</label>
                <input
                  type="number" min="0.01" max="10" step="0.01"
                  :value="valueOf('repetition_penalty')" placeholder="1.05"
                  :disabled="!customParamsEnabled"
                  class="w-full px-2 py-1.5 text-xs border rounded-lg bg-background disabled:cursor-not-allowed"
                  @change="setNumber('repetition_penalty', ($event.target as HTMLInputElement).value, 0.01, 10)"
                />
              </div>
            </div>
            <section class="border-t pt-1 space-y-1">
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.topK') }}</label>
                <input type="number" min="0" max="32767" step="1" :value="valueOf('top_k')" placeholder="50" :disabled="!customParamsEnabled || modelValue.do_sample === false" class="param-input" @change="setNumber('top_k', ($event.target as HTMLInputElement).value, 0, 32767, true)" />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.topPTooltip')">{{ $t('components.generationParams.topP') }}</label>
                <input type="number" min="0.01" max="1" step="0.01" :value="valueOf('top_p')" placeholder="1.0" :disabled="!customParamsEnabled || modelValue.do_sample === false" class="param-input" @change="setNumber('top_p', ($event.target as HTMLInputElement).value, 0.01, 1)" />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.temperatureTooltip')">{{ $t('components.generationParams.temperature') }}</label>
                <input type="number" min="0.1" max="10" step="0.1" :value="valueOf('temperature')" placeholder="0.9" :disabled="!customParamsEnabled || modelValue.do_sample === false" class="param-input" @change="setNumber('temperature', ($event.target as HTMLInputElement).value, 0.1, 10)" />
              </div>
            </section>
          </section>

          <section class="border-t pt-3 space-y-3">
            <div class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              {{ $t('components.generationParams.subtalkerSection') }}
              <CircleHelp v-if="isFasterBranch" class="w-3.5 h-3.5" v-tooltip="$t('components.generationParams.subtalkerTooltip')" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.doSample') }}</label>
                <AppSelect compact :model-value="samplingValue(modelValue.subtalker_dosample)" :options="samplingOptions" :disabled="!customParamsEnabled" @update:model-value="setSampling('subtalker_dosample', $event)" />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.topK') }}</label>
                <input type="number" min="0" max="32767" step="1" :value="valueOf('subtalker_top_k')" placeholder="50" :disabled="!customParamsEnabled || modelValue.subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_top_k', ($event.target as HTMLInputElement).value, 0, 32767, true)" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.topPTooltip')">{{ $t('components.generationParams.topP') }}</label>
                <input type="number" min="0.01" max="1" step="0.01" :value="valueOf('subtalker_top_p')" placeholder="1.0" :disabled="!customParamsEnabled || modelValue.subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_top_p', ($event.target as HTMLInputElement).value, 0.01, 1)" />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.temperatureTooltip')">{{ $t('components.generationParams.temperature') }}</label>
                <input type="number" min="0.1" max="10" step="0.1" :value="valueOf('subtalker_temperature')" placeholder="0.9" :disabled="!customParamsEnabled || modelValue.subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_temperature', ($event.target as HTMLInputElement).value, 0.1, 10)" />
              </div>
            </div>
          </section>

          <section class="border-t pt-3 space-y-3">
            <div class="text-xs font-medium text-muted-foreground">{{ $t('components.generationParams.lengthSection') }}</div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.minNewTokens') }}</label>
                <input type="number" min="1" max="32767" step="1" :value="valueOf('min_new_tokens')" :placeholder="$t('components.generationParams.notSet')" :disabled="!customParamsEnabled" class="param-input" @change="setNumber('min_new_tokens', ($event.target as HTMLInputElement).value, 1, 32767, true)" />
              </div>
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.maxNewTokens') }}</label>
                <input type="number" min="1" max="32767" step="1" :value="valueOf('max_new_tokens')" placeholder="2048" :disabled="!customParamsEnabled" class="param-input" @change="setNumber('max_new_tokens', ($event.target as HTMLInputElement).value, 1, 32767, true)" />
              </div>
            </div>
            <div class="flex items-center justify-between gap-3">
              <label class="text-xs text-muted-foreground">{{ $t('components.generationParams.nonStreamingMode') }}</label>
              <AppSelect compact :model-value="triStateValue(modelValue.non_streaming_mode)" :options="triStateOptions" :disabled="!customParamsEnabled" @update:model-value="setTriState" />
            </div>
          </section>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.param-input {
  @apply w-full px-2 py-1.5 text-xs border rounded-lg bg-background transition-colors duration-150 focus:border-primary focus:ring-1 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50;
}
</style>
