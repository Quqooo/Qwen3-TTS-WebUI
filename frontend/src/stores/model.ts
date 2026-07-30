import { defineStore } from "pinia"
import { ref, computed } from "vue"
import type { ModelInfo, ModelKind, ModelCacheStatus, WorkerStatus } from "../types"
import { modelsApi } from "../api/models"
import { createCacheWebSocket } from "../api/ws"

export const useModelStore = defineStore("model", () => {
  const availableModels = ref<ModelInfo[]>([])
  const activeModelId = ref<string | null>(null)
  const cacheStatus = ref<ModelCacheStatus>({
    loaded: [],
    max_concurrent: 1,
    usage_order: [],
  })
  const workerStatus = ref<WorkerStatus>({ alive: false, error: null })
  const wsConnected = ref(false)

  const activeModel = computed(() =>
    availableModels.value.find((m) => m.id === activeModelId.value) ?? null
  )

  const activeModelKind = computed<ModelKind | null>(() =>
    activeModel.value?.kind ?? null
  )

  const baseModels = computed(() =>
    availableModels.value.filter((m) => m.kind === "base")
  )

  const customVoiceModels = computed(() =>
    availableModels.value.filter((m) => m.kind === "custom_voice")
  )

  const voiceDesignModels = computed(() =>
    availableModels.value.filter((m) => m.kind === "voice_design")
  )

  const loading = ref(false)
  let _wsCleanup: (() => void) | null = null

  function startCacheWatcher() {
    if (_wsCleanup) return
    _wsCleanup = createCacheWebSocket(
      (msg) => {
        if (msg.type === "cache") cacheStatus.value = msg.data
        else if (msg.type === "worker") workerStatus.value = msg.data
      },
      (connected) => {
        wsConnected.value = connected
      },
    )
  }

  async function fetchModels() {
    loading.value = true
    try {
      const res = await modelsApi.list()
      availableModels.value = res.models
    } catch {
      // keep current
    } finally {
      loading.value = false
    }
  }

  function setModels(models: ModelInfo[]) {
    availableModels.value = models
  }

  function setActiveModel(id: string | null) {
    activeModelId.value = id
  }

  async function refreshCacheStatus() {
    try {
      const status = await modelsApi.cacheStatus()
      cacheStatus.value = status
    } catch {
      // keep current
    }
  }

  return {
    availableModels,
    activeModelId,
    cacheStatus,
    workerStatus,
    wsConnected,
    activeModel,
    activeModelKind,
    baseModels,
    customVoiceModels,
    voiceDesignModels,
    loading,
    startCacheWatcher,
    fetchModels,
    setModels,
    setActiveModel,
    refreshCacheStatus,
  }
})
