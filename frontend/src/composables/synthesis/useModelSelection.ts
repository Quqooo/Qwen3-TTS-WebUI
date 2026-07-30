import { ref, computed, watch, onMounted, type Ref, type ComputedRef } from "vue"
import { modelsApi } from "../../api/models"
import { buildLanguageOptions, buildSpeakerOptions, type OptionItem } from "../../constants/options"
import { useModelStore } from "../../stores/model"
import type { ModelKind } from "../../types"

export interface ModelSelectionOptions {
  kind: ModelKind
}

export function useModelSelection({ kind }: ModelSelectionOptions) {
  const modelStore = useModelStore()
  const selectedModel = ref("")
  const selectedLang = ref("Auto")
  const speakerOptions = ref<OptionItem[]>([])
  const languageOptions = ref<OptionItem[]>([])
  const selectedSpeaker = ref("serena")

  const modelsMap: Record<ModelKind, ComputedRef<{ value: string; label: string }[]>> = {
    base: computed(() => modelStore.baseModels.map(m => ({ value: m.id, label: m.id }))),
    custom_voice: computed(() => modelStore.customVoiceModels.map(m => ({ value: m.id, label: m.id }))),
    voice_design: computed(() => modelStore.voiceDesignModels.map(m => ({ value: m.id, label: m.id }))),
  }
  const models = modelsMap[kind]

  const modelsSource: Record<ModelKind, Ref<{ id: string }[]>> = {
    base: computed(() => modelStore.baseModels) as any,
    custom_voice: computed(() => modelStore.customVoiceModels) as any,
    voice_design: computed(() => modelStore.voiceDesignModels) as any,
  }

  async function fetchModelMeta(modelId: string) {
    if (!modelId) return
    try {
      const meta = await modelsApi.getMeta(modelId)
      if (meta.languages.length > 0) languageOptions.value = buildLanguageOptions(meta.languages)
      if (kind === "custom_voice" && meta.speakers.length > 0) speakerOptions.value = buildSpeakerOptions(meta.speakers)
    } catch {
      // keep defaults
    }
  }

  onMounted(() => { modelStore.fetchModels() })

  watch(selectedModel, (id) => { fetchModelMeta(id) })

  watch(() => (modelsSource[kind] as Ref<any>).value, (list: any[]) => {
    if (!list.length) return
    const exists = list.some((m: any) => m.id === selectedModel.value)
    if (!exists) selectedModel.value = list[0].id
  }, { immediate: true })

  if (kind === "custom_voice") {
    watch(speakerOptions, (options) => {
      if (!options.length) return
      const normalize = (s: string) => s.toLowerCase().replace(/[ _]/g, '_')
      const match = options.find(o => normalize(o.value) === normalize(selectedSpeaker.value))
      if (match) {
        if (match.value !== selectedSpeaker.value) selectedSpeaker.value = match.value
      } else {
        selectedSpeaker.value = options[0].value
      }
    })
  }

  watch(languageOptions, (options) => {
    const exists = options.some(o => o.value === selectedLang.value)
    if (!exists) selectedLang.value = "Auto"
  })

  return {
    selectedModel,
    models,
    selectedLang,
    speakerOptions,
    languageOptions,
    selectedSpeaker,
  }
}
