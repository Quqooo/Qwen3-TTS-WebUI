import { computed, ref, type Ref } from "vue"
import { useStorage } from "@vueuse/core"
import type { ModelConfig } from "../components/batch/ModelConfigPanel.vue"
import type { GenerationParams, ModelKind } from "../types"
import type { useModelStore } from "../stores/model"
import type { useVoiceStore } from "../stores/voice"

type ModelStore = ReturnType<typeof useModelStore>
type VoiceStore = ReturnType<typeof useVoiceStore>
type DefaultParams = Record<ModelKind, GenerationParams>
type ConfigStore = Record<ModelKind, Ref<ModelConfig>>

export interface BatchModelConfigOptions {
  modelStore: ModelStore
  voiceStore: VoiceStore
  defaultParams: Ref<DefaultParams>
}

function createDefaultConfig(
  kind: ModelKind,
  { modelStore, voiceStore, defaultParams }: BatchModelConfigOptions,
): ModelConfig {
  const models = kind === "base"
    ? modelStore.baseModels
    : kind === "custom_voice"
      ? modelStore.customVoiceModels
      : modelStore.voiceDesignModels

  return {
    text: "",
    modelKind: kind,
    model: models[0]?.id ?? "",
    speaker: "",
    instruct: "",
    voiceDescription: "",
    voiceFile: voiceStore.voices[0]?.name ?? "",
    refText: "",
    xvecOnly: false,
    cloneSource: kind === "base" ? "voice_file" : "upload",
    refAudioUrl: "",
    refAudioName: "",
    timelineEnabled: false,
    timelineStart: 0,
    timelineEnd: 0,
    language: "Auto",
    generationParams: { ...defaultParams.value[kind] },
  }
}

function createStoredConfig(
  key: string,
  kind: ModelKind,
  options: BatchModelConfigOptions,
): Ref<ModelConfig> {
  const fallback = () => createDefaultConfig(kind, options)
  return useStorage<ModelConfig>(key, fallback(), localStorage, {
    serializer: {
      read: (value: string) => {
        try {
          const parsed = JSON.parse(value) as Partial<ModelConfig>
          const defaults = fallback()
          return {
            ...defaults,
            ...parsed,
            modelKind: kind,
            generationParams: {
              ...defaults.generationParams,
              ...(parsed.generationParams ?? {}),
            },
          }
        } catch {
          return fallback()
        }
      },
      write: (value) => JSON.stringify(value),
    },
  })
}

function createKindConfig(
  keyPrefix: string,
  options: BatchModelConfigOptions,
) {
  const store: ConfigStore = {
    base: createStoredConfig(`${keyPrefix}:base`, "base", options),
    custom_voice: createStoredConfig(`${keyPrefix}:custom_voice`, "custom_voice", options),
    voice_design: createStoredConfig(`${keyPrefix}:voice_design`, "voice_design", options),
  }
  const currentKind = ref<ModelKind>("base")
  const config = computed<ModelConfig>({
    get: () => store[currentKind.value].value,
    set: (value) => {
      if (value.modelKind !== currentKind.value) {
        currentKind.value = value.modelKind
      } else {
        store[currentKind.value].value = { ...value }
      }
    },
  })

  return { config, currentKind, store }
}

export function useBatchModelConfigs(options: BatchModelConfigOptions) {
  const importState = createKindConfig("qwen-tts:batch:import-config", options)
  const batchState = createKindConfig("qwen-tts:batch:batch-config", options)

  return {
    importConfig: importState.config,
    batchConfig: batchState.config,
    batchCurrentKind: batchState.currentKind,
    batchKindStore: batchState.store,
  }
}
