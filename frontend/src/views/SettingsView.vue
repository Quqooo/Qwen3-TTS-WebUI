<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { Save, Info, FolderOpen, Volume2, ExternalLink, XCircle, RefreshCw } from "@lucide/vue"
import type { ModelKind, GenerationParams as GenParams } from "../types"
import { settingsApi } from "../api/settings"
import { modelsApi } from "../api/models"
import { api } from "../api/client"
import { useModelStore } from "../stores/model"
import { useUserConfig } from "../composables/useUserConfig"
import { useToast } from "../composables/useToast"
import AppSelect from "../components/common/AppSelect.vue"
import Skeleton from "../components/common/Skeleton.vue"
import { t } from "../lang"

interface SettingsData {
  gpuDevices: string
  maxConcurrent: number
  idleTimeout: number
  workerIdleTimeout: number
  backendBranch: string
  backendBranchOptions: string[]
  projectDir: string
  envDir: string
  modelDir: string
  voiceDir: string
  maxSeqLen: number
}

let settingsCache: SettingsData | null = null

function applySettings(data: SettingsData) {
  gpuDevices.value = data.gpuDevices
  maxConcurrent.value = data.maxConcurrent
  idleTimeout.value = data.idleTimeout
  workerIdleTimeout.value = data.workerIdleTimeout
  backendBranch.value = data.backendBranch
  backendBranchOptions.value = data.backendBranchOptions
  projectDir.value = data.projectDir
  envDir.value = data.envDir
  modelDir.value = data.modelDir
  voiceDir.value = data.voiceDir
  maxSeqLen.value = data.maxSeqLen
}

function updateParam(key: keyof GenParams, raw: string) {
  const num = parseFloat(raw)
  if (!isNaN(num)) defaultParams.value[selectedKind.value] = { ...defaultParams.value[selectedKind.value], [key]: num }
}

const { defaultParams, globalVolume } = useUserConfig()
const modelStore = useModelStore()

const loading = ref(true)
const gpuDevices = ref("")
const maxConcurrent = ref(0)
const idleTimeout = ref(0)
const workerIdleTimeout = ref(0)
const { success: toastSuccess } = useToast()
const inferenceGpus = ref<Record<string, Record<string, number>>>({})

// 推理队列展示行：模型 × GPU 实例
const inferenceRows = computed(() => {
  const rows: { id: string; gpu: string; count: number }[] = []
  for (const [mid, gpus] of Object.entries(inferenceGpus.value)) {
    for (const [gpu, count] of Object.entries(gpus)) {
      if (count > 0) rows.push({ id: mid, gpu, count })
    }
  }
  return rows
})

const backendBranch = ref("")
const backendBranchOptions = ref<string[]>([])
const branchSelectOptions = computed(() =>
  backendBranchOptions.value.map(v => ({ value: v, label: v })),
)
const projectDir = ref("")
const envDir = ref("")
const modelDir = ref("")
const voiceDir = ref("")
const maxSeqLen = ref(2048)
const isFasterBranch = computed(() => backendBranch.value === "andimarafioti/faster-qwen3-tts")

const selectedKind = ref<ModelKind>("base")

// 缓存实例行：usage_order 提供 {id, gpu} 顺序；缺失时回退 loaded
const loadedInstances = computed(() => {
  const order = modelStore.cacheStatus.usage_order ?? []
  if (order.length) return order
  return modelStore.cacheStatus.loaded.map((m) => ({ id: m.id, gpu: m.gpu }))
})
const loadedCount = computed(() => loadedInstances.value.length)

const kindOptions = computed(() => [
  { value: "base" as ModelKind, label: t('views.settings.tabBase') },
  { value: "custom_voice" as ModelKind, label: t('views.settings.tabCustomVoice') },
  { value: "voice_design" as ModelKind, label: t('views.settings.tabVoiceDesign') },
])

async function saveSettings() {
  try {
    const res = await settingsApi.update({
      gpu_devices: gpuDevices.value,
      max_concurrent_models: maxConcurrent.value,
      idle_unload_seconds: idleTimeout.value,
      worker_idle_unload_seconds: workerIdleTimeout.value,
      backend_branch: backendBranch.value,
      project_dir: projectDir.value,
      env_dir: envDir.value,
      model_dir: modelDir.value,
      voice_dir: voiceDir.value,
      max_seq_len: maxSeqLen.value,
    })
    settingsCache = {
      gpuDevices: res.gpu_devices,
      maxConcurrent: res.max_concurrent_models,
      idleTimeout: res.idle_unload_seconds,
      workerIdleTimeout: res.worker_idle_unload_seconds,
      backendBranch: res.backend_branch,
      backendBranchOptions: res.backend_branch_options,
      projectDir: res.project_dir,
      envDir: res.env_dir,
      modelDir: res.model_dir,
      voiceDir: res.voice_dir,
      maxSeqLen: res.max_seq_len,
    }
    toastSuccess(t('views.settings.saved'))
  } catch {
  }
}

async function refreshInferenceStatus() {
  try {
    const res = await api.get<{ inference_gpus: Record<string, Record<string, number>> }>("/tracker/status")
    inferenceGpus.value = res.inference_gpus ?? {}
  } catch {
    // ignore
  }
}

async function unloadModel(modelId: string) {
  try {
    await modelsApi.unload(modelId)
    modelStore.refreshCacheStatus()
  } catch {
    // ignore
  }
}

function onConcurrentWheel(ev: WheelEvent) {
  ev.preventDefault()
  const d = ev.deltaY > 0 ? -1 : 1
  maxConcurrent.value = Math.max(1, maxConcurrent.value + d)
}

function resetDefaultParams() {
  const defaults = {
    temperature: 0.9,
    top_k: 50,
    top_p: 1.0,
    repetition_penalty: 1.05,
    max_new_tokens: 8192,
    subtalker_top_k: 50,
    subtalker_top_p: 1.0,
    subtalker_temperature: 0.9,
  }
  defaultParams.value[selectedKind.value] = { ...defaults }
}

onMounted(async () => {
  loading.value = true
  try {
    const [s] = await Promise.all([
      settingsApi.get(),
      modelStore.refreshCacheStatus(),
      refreshInferenceStatus(),
    ])
    const data: SettingsData = {
      gpuDevices: s.gpu_devices ?? "0",
      maxConcurrent: s.max_concurrent_models,
      idleTimeout: s.idle_unload_seconds,
      workerIdleTimeout: s.worker_idle_unload_seconds ?? 600,
      backendBranch: s.backend_branch,
      backendBranchOptions: s.backend_branch_options,
      projectDir: s.project_dir,
      envDir: s.env_dir,
      modelDir: s.model_dir,
      voiceDir: s.voice_dir,
      maxSeqLen: s.max_seq_len ?? 2048,
    }
    settingsCache = data
    applySettings(data)
  } catch {
    if (settingsCache) {
      applySettings(settingsCache)
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-7xl mx-auto py-6 px-8">
      <Transition name="fade" mode="out-in">
        <!-- Skeleton loading -->
        <div v-if="loading" key="skeleton" class="space-y-4">
          <div class="flex gap-6">
            <div class="flex-[5] space-y-4">
              <Skeleton class="h-4 w-28" />
              <Skeleton class="h-3 w-64" />
              <div class="grid grid-cols-2 gap-4">
                <div class="space-y-4">
                  <div class="border rounded-xl p-4 space-y-4">
                    <Skeleton class="h-5 w-24" />
                    <Skeleton class="h-8 w-full" />
                    <Skeleton class="h-8 w-full" />
                    <Skeleton class="h-24 w-full" />
                    <Skeleton class="h-20 w-full" />
                  </div>
                </div>
                <div class="border rounded-xl p-4 space-y-4">
                  <Skeleton class="h-5 w-28" />
                  <Skeleton class="h-3 w-48" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                </div>
              </div>
            </div>
            <div class="flex-[3] space-y-4">
              <Skeleton class="h-4 w-24" />
              <Skeleton class="h-3 w-48" />
              <div class="border rounded-xl p-4 space-y-4">
                <Skeleton class="h-5 w-32" />
                <Skeleton class="h-10 w-full" />
                <div class="grid grid-cols-2 gap-4">
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                  <Skeleton class="h-8 w-full" />
                </div>
              </div>
              <div class="border rounded-xl p-4 space-y-4">
                <Skeleton class="h-5 w-16" />
                <Skeleton class="h-8 w-full" />
              </div>
              <Skeleton class="h-10 w-full" />
            </div>
          </div>
          <Skeleton class="h-10 w-28" />
        </div>

        <!-- Content -->
        <div v-else key="content" class="space-y-4">
          <div class="flex gap-6">
            <!-- Left: Global Config -->
            <div class="flex-[5] min-w-0 space-y-4">
              <div class="space-y-4">
                <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wider">{{ $t('views.settings.globalConfig') }}</h2>
                <p class="text-[10px] text-muted-foreground -mt-3">{{ $t('views.settings.globalConfigHint') }}</p>

                <div class="grid grid-cols-2 gap-4 min-h-[26rem]">
                  <!-- Left: 模型缓存 -->
                   <div class="border rounded-xl p-4 space-y-4 bg-card h-full">
                      <h3 class="text-sm font-medium flex items-center gap-2">
                        <Info class="w-4 h-4 text-muted-foreground" /> {{ $t('views.settings.modelCache') }}
                      </h3>
                      <div class="space-y-3">
                        <div class="space-y-1.5">
                          <label class="text-xs text-muted-foreground">{{ $t('views.settings.gpuDevices') }}</label>
                          <input
                            v-model="gpuDevices"
                            type="text"
                            class="w-full px-3 py-2 text-sm"
                            :placeholder="$t('views.settings.gpuDevicesPlaceholder')"
                          />
                          <p class="text-[10px] text-muted-foreground">{{ $t('views.settings.gpuDevicesHint') }}</p>
                        </div>
                        <div class="space-y-1.5">
                          <label class="text-xs text-muted-foreground">{{ $t('views.settings.maxConcurrent') }}</label>
                          <input
                            v-model.number="maxConcurrent"
                            type="number"
                            min="1"
                            class="w-full px-3 py-2 text-sm"
                            @wheel.prevent="onConcurrentWheel"
                          />
                          <p class="text-[10px] text-muted-foreground">{{ $t('views.settings.maxConcurrentHint') }}</p>
                        </div>
                          <div class="flex gap-3">
                            <div class="flex-1 space-y-1.5">
                              <label class="text-xs text-muted-foreground">{{ $t('views.settings.idleUnload') }}</label>
                              <input v-model="idleTimeout" type="number" min="0" step="60" class="w-full px-3 py-2 text-sm" />
                            </div>
                            <div class="flex-1 space-y-1.5">
                              <label class="text-xs text-muted-foreground">{{ $t('views.settings.workerIdleUnload') }}</label>
                              <input v-model="workerIdleTimeout" type="number" min="0" step="60" class="w-full px-3 py-2 text-sm" />
                            </div>
                          </div>
                          <p class="text-[10px] text-muted-foreground">{{ $t('views.settings.idleTimeoutHint') }}</p>
                      </div>
                      <div class="border rounded-lg p-3 bg-secondary/20 space-y-2">
                        <div class="flex items-center justify-between">
                          <div class="flex items-center gap-1.5">
                            <Info class="w-3.5 h-3.5 text-muted-foreground" />
                            <span class="text-xs font-medium">{{ $t('views.settings.cacheStatus') }}</span>
                          </div>
                          <button
                            class="shrink-0 p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                            v-tooltip="$t('views.settings.refreshCache')"
                            @click="modelStore.refreshCacheStatus()"
                          >
                            <RefreshCw class="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <div v-if="loadedCount === 0" class="text-xs text-muted-foreground">{{ $t('views.settings.noCache') }}</div>
                        <div v-else class="space-y-1 max-h-40 overflow-y-auto">
                          <div
                            v-for="inst in loadedInstances"
                            :key="`${inst.id}@${inst.gpu}`"
                            class="flex items-center gap-2 py-1 px-1.5 rounded-md hover:bg-secondary/40 transition-colors group"
                          >
                            <span class="text-xs truncate font-mono" :title="inst.id">{{ inst.id }}</span>
                            <span class="text-[10px] font-mono text-muted-foreground ml-auto shrink-0">GPU {{ inst.gpu }}</span>
                            <button
                              class="shrink-0 p-0.5 rounded-full text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                              v-tooltip="$t('views.settings.unloadModel')"
                              @click="unloadModel(inst.id)"
                            >
                              <XCircle class="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      </div>
                      <div class="border rounded-lg p-3 bg-secondary/20 space-y-2">
                        <div class="flex items-center justify-between">
                          <div class="flex items-center gap-1.5">
                            <Info class="w-3.5 h-3.5 text-muted-foreground" />
                            <span class="text-xs font-medium">{{ $t('views.settings.inferenceQueue') }}</span>
                          </div>
                          <button
                            class="shrink-0 p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                            v-tooltip="$t('views.settings.refreshInference')"
                            @click="refreshInferenceStatus()"
                          >
                            <RefreshCw class="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <div v-if="inferenceRows.length === 0" class="text-xs text-muted-foreground">{{ $t('views.settings.noInference') }}</div>
                        <div v-else class="space-y-1 max-h-40 overflow-y-auto">
                          <div
                            v-for="row in inferenceRows"
                            :key="`${row.id}@${row.gpu}`"
                            class="flex items-center justify-between py-1 px-1.5 rounded-md"
                          >
                            <span class="text-xs truncate font-mono">{{ row.id }} <span class="text-muted-foreground">(#{{ row.gpu }})</span></span>
                            <span class="text-xs font-mono tabular-nums ml-2">{{ row.count }}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                  <!-- Right: QwenTTS 后端 -->
                   <div class="border rounded-xl p-4 space-y-4 bg-card">
                    <h3 class="text-sm font-medium flex items-center gap-2">
                      <FolderOpen class="w-4 h-4 text-muted-foreground" /> {{ $t('views.settings.qwenBackend') }}
                    </h3>
                    <p class="text-[10px] text-muted-foreground -mt-2">{{ $t('views.settings.qwenBackendHint') }}</p>
                    <div class="space-y-3">
                      <div class="space-y-1.5">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.branch') }}</label>
                        <AppSelect v-model="backendBranch" :options="branchSelectOptions" />
                      </div>
                      <div class="space-y-1.5">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.projectDir') }}</label>
                        <input v-model="projectDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.projectDirPlaceholder')" />
                      </div>
                      <div class="space-y-1.5">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.envDir') }}</label>
                        <input v-model="envDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.envDirPlaceholder')" />
                      </div>
                      <div class="space-y-1.5">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.modelDir') }}</label>
                        <input v-model="modelDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.modelDirPlaceholder')" />
                      </div>
                      <div class="space-y-1.5">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.voiceDir') }}</label>
                        <input v-model="voiceDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.voiceDirPlaceholder')" />
                      </div>
                      <div
                        class="space-y-1.5 border-t pt-3"
                        :class="{ 'invisible pointer-events-none': !isFasterBranch }"
                        :aria-hidden="!isFasterBranch"
                      >
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.maxSeqLen') }}</label>
                        <input
                          v-model.number="maxSeqLen"
                          type="number"
                          min="1"
                          max="32767"
                          step="1"
                          class="w-full px-3 py-2 text-sm"
                        />
                        <p class="text-[10px] text-muted-foreground">{{ $t('views.settings.maxSeqLenHint') }}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right: User Config + Save -->
            <div class="flex-[3] min-w-0 space-y-4">
              <div class="space-y-4">
                <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wider">{{ $t('views.settings.userConfig') }}</h2>
                <p class="text-[10px] text-muted-foreground -mt-3">{{ $t('views.settings.userConfigHint') }}</p>

                <div class="border rounded-xl p-4 space-y-4 bg-card">
                  <div class="flex items-center justify-between">
                    <h3 class="text-sm font-medium">{{ $t('views.settings.defaultGenParams') }}</h3>
                    <button
                      class="text-xs text-muted-foreground hover:text-foreground underline transition-colors"
                      @click="resetDefaultParams"
                    >{{ $t('views.settings.resetToDefault') }}</button>
                  </div>
                  <div class="flex p-0.5 gap-0.5 border rounded-lg">
                    <button
                      v-for="opt in kindOptions"
                      :key="opt.value"
                      class="flex-1 flex items-center justify-center px-3 py-2 text-sm rounded-md font-medium transition-all"
                      :class="selectedKind === opt.value
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
                      @click="selectedKind = opt.value"
                    >{{ opt.label }}</button>
                  </div>
                  <div :key="selectedKind" class="border-t pt-3 mt-3 space-y-3">
                    <div class="grid grid-cols-2 gap-x-4 gap-y-3">
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.temperature') }}</label>
                        <input type="number" step="0.1" min="0" max="2" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].temperature" @input="updateParam('temperature', ($event.target as HTMLInputElement).value)" />
                      </div>
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.topK') }}</label>
                        <input type="number" min="0" max="200" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].top_k" @input="updateParam('top_k', ($event.target as HTMLInputElement).value)" />
                      </div>
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.topP') }}</label>
                        <input type="number" step="0.05" min="0" max="1" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].top_p" @input="updateParam('top_p', ($event.target as HTMLInputElement).value)" />
                      </div>
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.repPenalty') }}</label>
                        <input type="number" step="0.05" min="1" max="2" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].repetition_penalty" @input="updateParam('repetition_penalty', ($event.target as HTMLInputElement).value)" />
                      </div>
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.maxNewTokens') }}</label>
                        <input type="number" min="1" max="32767" step="1" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].max_new_tokens" @input="updateParam('max_new_tokens', ($event.target as HTMLInputElement).value)" />
                      </div>
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.subTopK') }}</label>
                        <input type="number" min="0" max="200" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].subtalker_top_k" @input="updateParam('subtalker_top_k', ($event.target as HTMLInputElement).value)" />
                      </div>
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.subTopP') }}</label>
                        <input type="number" step="0.05" min="0" max="1" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].subtalker_top_p" @input="updateParam('subtalker_top_p', ($event.target as HTMLInputElement).value)" />
                      </div>
                      <div class="space-y-1">
                        <label class="text-xs text-muted-foreground">{{ $t('views.settings.subTemperature') }}</label>
                        <input type="number" step="0.1" min="0" max="2" class="w-full px-3 py-1.5 text-sm" :value="defaultParams[selectedKind].subtalker_temperature" @input="updateParam('subtalker_temperature', ($event.target as HTMLInputElement).value)" />
                      </div>
                    </div>
                  </div>
                </div>

                <div class="border rounded-xl p-4 space-y-4 bg-card">
                  <h3 class="text-sm font-medium">{{ $t('views.settings.other') }}</h3>
                  <div class="flex items-center gap-3">
                    <Volume2 class="w-4 h-4 text-muted-foreground" />
                    <span class="text-xs text-muted-foreground w-20 shrink-0">{{ $t('views.settings.globalVolume') }}</span>
                    <input
                      v-model.number="globalVolume"
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      class="flex-1 h-1.5 rounded-full cursor-pointer accent-primary"
                    />
                    <span class="text-sm font-mono tabular-nums w-10 text-right">{{ globalVolume }}%</span>
                  </div>
                </div>
              </div>

              <a
                href="/docs"
                target="_blank"
                class="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm border hover:bg-accent transition-colors"
              >
                <ExternalLink class="w-4 h-4" /> {{ $t('views.settings.apiDocs') }}
              </a>
            </div>
          </div>

          <div class="max-w-7xl mx-auto px-8">
            <button
              class="flex items-center gap-1.5 px-6 py-2.5 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all duration-150 active:scale-[0.98]"
              @click="saveSettings"
            >
              <Save class="w-4 h-4" /> {{ $t('views.settings.save') }}
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
