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
const subtalkerHeaderTooltip = computed(() => {
  const base = t("components.generationParams.subtalkerSectionTooltip")
  return isFasterBranch.value
    ? `${base}\n${t("components.generationParams.subtalkerTooltip")}`
    : base
})

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

function randomSeed() {
  if (props.disabled) return
  patch({ seed: Math.floor(Math.random() * 0xffffffff) })
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
            <div class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              {{ $t('components.generationParams.talkerSection') }}
              <CircleHelp class="w-3.5 h-3.5" v-tooltip="$t('components.generationParams.talkerSectionTooltip')" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <div class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.doSampleTooltip')">{{ $t('components.generationParams.doSample') }}</div>
                <AppSelect
                  compact
                  class="[&_button]:h-8"
                  :model-value="samplingValue(modelValue.do_sample)"
                  :options="samplingOptions"
                  :disabled="!customParamsEnabled"
                  @update:model-value="setSampling('do_sample', $event)"
                />
              </div>
              <div class="space-y-1.5">
                <label for="generation-repetition-penalty" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.repPenaltyTooltip')">{{ $t('components.generationParams.repPenalty') }}</label>
                <input
                  id="generation-repetition-penalty" name="generation_repetition_penalty"
                  type="number" min="0.01" max="10" step="0.01"
                  :value="valueOf('repetition_penalty')" placeholder="1.05"
                  :disabled="!customParamsEnabled"
                  class="h-8 w-full px-2 py-1.5 text-xs border rounded-lg bg-background disabled:cursor-not-allowed"
                  @change="setNumber('repetition_penalty', ($event.target as HTMLInputElement).value, 0.01, 10)"
                />
              </div>
            </div>
            <section class="grid grid-cols-3 gap-3">
              <div class="space-y-1.5">
                <label for="generation-top-k" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.topKTooltip')">{{ $t('components.generationParams.topK') }}</label>
                <input id="generation-top-k" name="generation_top_k" type="number" min="0" max="32767" step="1" :value="valueOf('top_k')" placeholder="50" :disabled="!customParamsEnabled || modelValue.do_sample === false" class="param-input" @change="setNumber('top_k', ($event.target as HTMLInputElement).value, 0, 32767, true)" />
              </div>
              <div class="space-y-1.5">
                <label for="generation-top-p" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.topPTooltip')">{{ $t('components.generationParams.topP') }}</label>
                <input id="generation-top-p" name="generation_top_p" type="number" min="0.01" max="1" step="0.01" :value="valueOf('top_p')" placeholder="1.0" :disabled="!customParamsEnabled || modelValue.do_sample === false" class="param-input" @change="setNumber('top_p', ($event.target as HTMLInputElement).value, 0.01, 1)" />
              </div>
              <div class="space-y-1.5">
                <label for="generation-temperature" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.temperatureTooltip')">{{ $t('components.generationParams.temperature') }}</label>
                <input id="generation-temperature" name="generation_temperature" type="number" min="0.1" max="10" step="0.1" :value="valueOf('temperature')" placeholder="0.9" :disabled="!customParamsEnabled || modelValue.do_sample === false" class="param-input" @change="setNumber('temperature', ($event.target as HTMLInputElement).value, 0.1, 10)" />
              </div>
            </section>
            <div class="grid grid-cols-[1fr_auto] gap-3">
              <div class="space-y-1.5">
                <label for="generation-seed" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.seedTooltip')">{{ $t('components.generationParams.seed') }}</label>
                <input id="generation-seed" name="generation_seed" type="number" min="0" max="4294967295" step="1" :value="valueOf('seed')" :placeholder="$t('components.generationParams.seedRandom')" :disabled="!customParamsEnabled" class="param-input" @change="setNumber('seed', ($event.target as HTMLInputElement).value, 0, 4294967295, true)" />
              </div>
              <div class="flex items-end pb-0.5">
                <button
                  type="button"
                  class="h-8 px-3 text-xs border rounded-lg bg-secondary text-secondary-foreground transition-colors duration-150 hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="!customParamsEnabled"
                  @click="randomSeed"
                >{{ $t('components.generationParams.seedRandomize') }}</button>
              </div>
            </div>
          </section>

          <section class="border-t pt-3 space-y-3">
            <div class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              {{ $t('components.generationParams.subtalkerSection') }}
              <CircleHelp class="w-3.5 h-3.5" v-tooltip="subtalkerHeaderTooltip" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <div class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.doSampleTooltip')">{{ $t('components.generationParams.doSample') }}</div>
                <AppSelect compact class="[&_button]:h-8" :model-value="samplingValue(modelValue.subtalker_dosample)" :options="samplingOptions" :disabled="!customParamsEnabled" @update:model-value="setSampling('subtalker_dosample', $event)" />
              </div>
              <div class="space-y-1.5">
                <label for="generation-subtalker-top-k" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.topKTooltip')">{{ $t('components.generationParams.topK') }}</label>
                <input id="generation-subtalker-top-k" name="generation_subtalker_top_k" type="number" min="0" max="32767" step="1" :value="valueOf('subtalker_top_k')" placeholder="50" :disabled="!customParamsEnabled || modelValue.subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_top_k', ($event.target as HTMLInputElement).value, 0, 32767, true)" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <label for="generation-subtalker-top-p" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.topPTooltip')">{{ $t('components.generationParams.topP') }}</label>
                <input id="generation-subtalker-top-p" name="generation_subtalker_top_p" type="number" min="0.01" max="1" step="0.01" :value="valueOf('subtalker_top_p')" placeholder="1.0" :disabled="!customParamsEnabled || modelValue.subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_top_p', ($event.target as HTMLInputElement).value, 0.01, 1)" />
              </div>
              <div class="space-y-1.5">
                <label for="generation-subtalker-temperature" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.temperatureTooltip')">{{ $t('components.generationParams.temperature') }}</label>
                <input id="generation-subtalker-temperature" name="generation_subtalker_temperature" type="number" min="0.1" max="10" step="0.1" :value="valueOf('subtalker_temperature')" placeholder="0.9" :disabled="!customParamsEnabled || modelValue.subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_temperature', ($event.target as HTMLInputElement).value, 0.1, 10)" />
              </div>
            </div>
          </section>

          <section class="border-t pt-3 space-y-3">
            <div class="text-xs font-medium text-muted-foreground">{{ $t('components.generationParams.lengthSection') }}</div>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <label for="generation-min-new-tokens" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.minNewTokensTooltip')">{{ $t('components.generationParams.minNewTokens') }}</label>
                <input id="generation-min-new-tokens" name="generation_min_new_tokens" type="number" min="1" max="32767" step="1" :value="valueOf('min_new_tokens')" :placeholder="$t('components.generationParams.notSet')" :disabled="!customParamsEnabled" class="param-input" @change="setNumber('min_new_tokens', ($event.target as HTMLInputElement).value, 1, 32767, true)" />
              </div>
              <div class="space-y-1.5">
                <label for="generation-max-new-tokens" class="flex h-4 items-center text-[10px] text-muted-foreground" v-tooltip="$t('components.generationParams.maxNewTokensTooltip')">{{ $t('components.generationParams.maxNewTokens') }}</label>
                <input id="generation-max-new-tokens" name="generation_max_new_tokens" type="number" min="1" max="32767" step="1" :value="valueOf('max_new_tokens')" placeholder="2048" :disabled="!customParamsEnabled" class="param-input" @change="setNumber('max_new_tokens', ($event.target as HTMLInputElement).value, 1, 32767, true)" />
              </div>
            </div>
            <div class="flex items-center justify-between gap-3">
              <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
                {{ $t('components.generationParams.nonStreamingMode') }}
                <CircleHelp class="w-3.5 h-3.5" v-tooltip="$t('components.generationParams.nonStreamingModeTooltip')" />
              </div>
              <AppSelect compact class="[&_button]:h-8" :model-value="triStateValue(modelValue.non_streaming_mode)" :options="triStateOptions" :disabled="!customParamsEnabled" @update:model-value="setTriState" />
            </div>
          </section>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.param-input {
  @apply h-8 w-full px-2 py-1.5 text-xs border rounded-lg bg-background transition-colors duration-150 focus:border-primary focus:ring-1 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50;
}
</style>
