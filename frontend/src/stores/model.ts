import { defineStore } from "pinia"
import { ref, computed } from "vue"
import type { ModelInfo, ModelKind, ModelCacheStatus, WorkerStatus, TrackerStatus } from "../types"
import { modelsApi } from "../api/models"
import { settingsApi } from "../api/settings"
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
  const trackerStatus = ref<TrackerStatus>({
    inference_counts: {},
    inference_gpus: {},
    inference_total: 0,
  })
  const wsConnected = ref(false)
  const backendBranch = ref("")
  const isFasterBranch = computed(() => backendBranch.value === "andimarafioti/faster-qwen3-tts")

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
        else if (msg.type === "tracker") trackerStatus.value = msg.data
        else if (msg.type === "backend") backendBranch.value = msg.data.backend_branch
      },
      (connected) => {
        wsConnected.value = connected
      },
    )
  }

  async function fetchModels() {
    loading.value = true
    try {
      const [modelsResult, settingsResult] = await Promise.allSettled([
        modelsApi.list(),
        settingsApi.get(),
      ])
      if (modelsResult.status === "fulfilled") {
        availableModels.value = modelsResult.value.models
      }
      if (settingsResult.status === "fulfilled") {
        backendBranch.value = settingsResult.value.backend_branch
      }
    } finally {
      loading.value = false
    }
  }

  function setModels(models: ModelInfo[]) {
    availableModels.value = models
  }

  function setBackendBranch(branch: string) {
    backendBranch.value = branch
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
    trackerStatus,
    wsConnected,
    backendBranch,
    isFasterBranch,
    activeModel,
    activeModelKind,
    baseModels,
    customVoiceModels,
    voiceDesignModels,
    loading,
    startCacheWatcher,
    fetchModels,
    setModels,
    setBackendBranch,
    setActiveModel,
    refreshCacheStatus,
  }
})
