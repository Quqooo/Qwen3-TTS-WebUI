<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { Save, FolderOpen, Volume2, ExternalLink, XCircle, RefreshCw, Server, SlidersHorizontal, User, Shield, Settings2, Gauge } from "@lucide/vue"
import type { ModelKind, GenerationParamsConfig as GenParams } from "../types"
import type { BatchComposerSettings } from "../api/settings"
import { settingsApi } from "../api/settings"
import { modelsApi } from "../api/models"
import { api } from "../api/client"
import { useModelStore } from "../stores/model"
import { useUserConfig } from "../composables/useUserConfig"
import { useToast } from "../composables/useToast"
import AppSelect from "../components/common/AppSelect.vue"
import AppSlider from "../components/common/AppSlider.vue"
import Skeleton from "../components/common/Skeleton.vue"
import { t } from "../lang"

type SettingsSection = "server" | "batch" | "user"

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
  batchComposer: BatchComposerSettings
}

const DEFAULT_BATCH: BatchComposerSettings = {
  max_segments: 1000,
  max_output_samples: 100000000,
  max_decoded_samples: 100000000,
  max_total_decoded_samples: 100000000,
  max_time_stretch_rate: 16,
  max_audio_mib: 32,
  max_total_audio_mib: 256,
  min_sample_rate: 8000,
  max_sample_rate: 192000,
}

let settingsCache: SettingsData | null = null
const { defaultParams, globalVolume } = useUserConfig()
const modelStore = useModelStore()
const { success: toastSuccess } = useToast()

const loading = ref(true)
const saving = ref(false)
const activeSection = ref<SettingsSection>("server")
const gpuDevices = ref("")
const maxConcurrent = ref(1)
const idleTimeout = ref(600)
const workerIdleTimeout = ref(600)
const backendBranch = ref("")
const backendBranchOptions = ref<string[]>([])
const projectDir = ref("")
const envDir = ref("")
const modelDir = ref("")
const voiceDir = ref("")
const maxSeqLen = ref(2048)
const batchComposer = ref<BatchComposerSettings>({ ...DEFAULT_BATCH })
const selectedKind = ref<ModelKind>("base")

const sections = computed(() => [
  { id: "server" as const, label: t("views.settings.sectionServer"), hint: t("views.settings.sectionServerHint"), icon: Server },
  { id: "batch" as const, label: t("views.settings.sectionBatch"), hint: t("views.settings.sectionBatchHint"), icon: Shield },
  { id: "user" as const, label: t("views.settings.sectionUser"), hint: t("views.settings.sectionUserHint"), icon: User },
])
const currentSection = computed(() => sections.value.find(section => section.id === activeSection.value) ?? sections.value[0])
const branchSelectOptions = computed(() => backendBranchOptions.value.map(value => ({ value, label: value })))
const isFasterBranch = computed(() => backendBranch.value === "andimarafioti/faster-qwen3-tts")
const cacheRows = computed(() => {
  const gpus = modelStore.trackerStatus.inference_gpus
  return [...modelStore.cacheStatus.loaded]
    .sort((a, b) => (b.last_used ?? 0) - (a.last_used ?? 0))
    .map(entry => ({
      id: entry.id,
      gpu: entry.gpu,
      count: gpus[entry.id]?.[entry.gpu] ?? 0,
    }))
})
const kindOptions = computed(() => [
  { value: "base" as ModelKind, label: t("views.settings.tabBase") },
  { value: "custom_voice" as ModelKind, label: t("views.settings.tabCustomVoice") },
  { value: "voice_design" as ModelKind, label: t("views.settings.tabVoiceDesign") },
])

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
  batchComposer.value = { ...DEFAULT_BATCH, ...data.batchComposer }
}

const samplingOptions = computed(() => [
  { value: "true", label: t("components.generationParams.randomSampling") },
  { value: "false", label: t("components.generationParams.greedyDecoding") },
])
const triStateOptions = computed(() => [
  { value: "default", label: t("components.generationParams.defaultMode") },
  { value: "true", label: t("components.generationParams.enabledMode") },
  { value: "false", label: t("components.generationParams.disabledMode") },
])

function patchParams(partial: Partial<GenParams>) {
  defaultParams.value[selectedKind.value] = { ...defaultParams.value[selectedKind.value], ...partial }
}

function setSampling(key: "do_sample" | "subtalker_dosample", value: string) {
  patchParams({ [key]: value === "true" } as Partial<GenParams>)
}

function setTriState(value: string) {
  patchParams({ non_streaming_mode: value === "default" ? undefined : value === "true" })
}

function setNumber(key: keyof GenParams, raw: string, min: number, max: number, integer = false) {
  if (!raw.trim()) {
    patchParams({ [key]: undefined } as Partial<GenParams>)
    return
  }
  const parsed = integer ? Number.parseInt(raw, 10) : Number.parseFloat(raw)
  if (!Number.isFinite(parsed)) return
  const value = Math.min(max, Math.max(min, parsed))
  const normalized = integer ? Math.trunc(value) : Number(value.toFixed(4))
  patchParams({ [key]: normalized } as Partial<GenParams>)
}

function paramValue(key: keyof GenParams): string {
  const value = defaultParams.value[selectedKind.value][key]
  return typeof value === "number" ? String(value) : ""
}

function samplingValue(value: boolean | undefined): string {
  return value === false ? "false" : "true"
}

function triStateValue(value: boolean | undefined): string {
  return value === undefined ? "default" : String(value)
}

function resetDefaultParams() {
  defaultParams.value[selectedKind.value] = {
    enabled: false,
    do_sample: true,
    temperature: 0.9,
    top_k: 50,
    top_p: 1.0,
    repetition_penalty: 1.05,
    subtalker_dosample: true,
    subtalker_top_k: 50,
    subtalker_top_p: 1.0,
    subtalker_temperature: 0.9,
    min_new_tokens: undefined,
    max_new_tokens: 2048,
    non_streaming_mode: undefined,
  }
}

async function saveSettings() {
  saving.value = true
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
      batch_composer: { ...batchComposer.value },
    })
    modelStore.setBackendBranch(res.backend_branch)
    settingsCache = fromResponse(res)
    toastSuccess(t("views.settings.saved"))
  } catch {
  } finally {
    saving.value = false
  }
}

function fromResponse(data: Awaited<ReturnType<typeof settingsApi.get>>): SettingsData {
  return {
    gpuDevices: data.gpu_devices ?? "0",
    maxConcurrent: data.max_concurrent_models,
    idleTimeout: data.idle_unload_seconds,
    workerIdleTimeout: data.worker_idle_unload_seconds ?? 600,
    backendBranch: data.backend_branch,
    backendBranchOptions: data.backend_branch_options,
    projectDir: data.project_dir,
    envDir: data.env_dir,
    modelDir: data.model_dir,
    voiceDir: data.voice_dir,
    maxSeqLen: data.max_seq_len ?? 2048,
    batchComposer: { ...DEFAULT_BATCH, ...data.batch_composer },
  }
}

async function refreshInferenceStatus() {
  try {
    const res = await api.get<{ inference_gpus: Record<string, Record<string, number>> }>("/tracker/status")
    modelStore.trackerStatus.inference_gpus = res.inference_gpus ?? {}
  } catch {
  }
}

function refreshStatus() {
  modelStore.refreshCacheStatus()
  refreshInferenceStatus()
}

async function unloadModel(modelId: string) {
  try {
    await modelsApi.unload(modelId)
    modelStore.refreshCacheStatus()
  } catch {
  }
}

function onConcurrentWheel(event: WheelEvent) {
  event.preventDefault()
  maxConcurrent.value = Math.max(1, maxConcurrent.value + (event.deltaY > 0 ? -1 : 1))
}

onMounted(async () => {
  loading.value = true
  try {
    const [settings] = await Promise.all([settingsApi.get(), modelStore.refreshCacheStatus(), refreshInferenceStatus()])
    settingsCache = fromResponse(settings)
    applySettings(settingsCache)
  } catch {
    if (settingsCache) applySettings(settingsCache)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="h-full min-h-0 flex flex-col overflow-hidden">
    <Transition name="fade" mode="out-in">
      <div v-if="loading" key="skeleton" class="flex-1 min-h-0 flex gap-4">
        <div class="w-52 shrink-0 border rounded-xl bg-card p-3 space-y-3">
          <Skeleton class="h-4 w-24" /><Skeleton class="h-9 w-full" /><Skeleton class="h-9 w-full" /><Skeleton class="h-9 w-full" />
        </div>
        <div class="flex-1 border rounded-xl bg-card p-5 space-y-4">
          <Skeleton class="h-5 w-40" /><Skeleton class="h-3 w-72" /><Skeleton class="h-10 w-full" /><Skeleton class="h-10 w-full" /><Skeleton class="h-10 w-2/3" />
        </div>
      </div>

      <div v-else key="content" class="flex-1 min-h-0 flex gap-4">
        <aside class="w-56 shrink-0 border rounded-xl bg-card p-2 flex flex-col overflow-hidden">
          <div class="px-3 py-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <SlidersHorizontal class="w-4 h-4" />
            {{ $t("views.settings.categories") }}
          </div>
          <nav class="space-y-1 overflow-y-auto">
            <button
              v-for="section in sections"
              :key="section.id"
              class="w-full flex items-start gap-2.5 text-left px-3 py-2.5 rounded-lg transition-colors"
              :class="activeSection === section.id ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'"
              @click="activeSection = section.id"
            >
              <component :is="section.icon" class="w-4 h-4 mt-0.5 shrink-0" />
              <span class="min-w-0">
                <span class="block text-xs font-medium">{{ section.label }}</span>
                <span class="block text-[10px] mt-0.5 opacity-70 truncate">{{ section.hint }}</span>
              </span>
            </button>
          </nav>
          <div class="mt-auto space-y-1">
            <a href="/docs" target="_blank" class="flex items-center justify-center gap-1.5 w-full px-3 py-2.5 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-secondary/60 transition-colors">
              <ExternalLink class="w-3.5 h-3.5" /> {{ $t("views.settings.apiDocs") }}
            </a>
            <button
              class="flex items-center justify-center gap-1.5 w-full px-3 py-2.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              :disabled="loading || saving"
              @click="saveSettings"
            >
              <Save class="w-3.5 h-3.5" />
              {{ saving ? $t("views.settings.saving") : $t("views.settings.save") }}
            </button>
          </div>
        </aside>

        <section class="flex-1 min-w-0 min-h-0 border rounded-xl bg-card overflow-hidden relative flex flex-col">
          <div class="shrink-0 px-5 py-3 border-b">
            <h2 class="text-base font-medium">{{ currentSection.label }}</h2>
          </div>

          <div class="flex-1 min-h-0 overflow-y-auto px-5 py-5">
            <div v-if="activeSection === 'server'" class="flex flex-col xl:flex-row gap-10 items-start">
              <section class="flex-1 min-w-0 space-y-4">
                <h3 class="text-sm font-medium flex items-center gap-2"><Server class="w-4 h-4 text-muted-foreground" /> {{ $t("views.settings.modelCache") }}</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-4">
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.gpuDevices") }}</label><input v-model="gpuDevices" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.gpuDevicesPlaceholder')" /><p class="text-[10px] text-muted-foreground">{{ $t("views.settings.gpuDevicesHint") }}</p></div>
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.maxConcurrent") }}</label><input v-model.number="maxConcurrent" type="number" min="1" max="16" class="w-full px-3 py-2 text-sm" @wheel="onConcurrentWheel" /><p class="text-[10px] text-muted-foreground">{{ $t("views.settings.maxConcurrentHint") }}</p></div>
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.idleUnload") }}</label><input v-model.number="idleTimeout" type="number" min="0" max="86400" step="60" class="w-full px-3 py-2 text-sm" /></div>
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.workerIdleUnload") }}</label><input v-model.number="workerIdleTimeout" type="number" min="0" max="86400" step="60" class="w-full px-3 py-2 text-sm" /></div>
                  <p class="text-[10px] text-muted-foreground md:col-span-2">{{ $t("views.settings.idleTimeoutHint") }}</p>
                </div>
                <div class="border rounded-lg p-3 bg-secondary/20 flex flex-col min-h-[21.5rem]">
                  <div class="flex items-center justify-between shrink-0"><span class="text-xs font-medium">{{ $t("views.settings.modelCacheStatus") }}</span><button class="shrink-0 p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors" v-tooltip="$t('views.settings.refreshCache')" @click="refreshStatus"><RefreshCw class="w-3.5 h-3.5" /></button></div>
                  <div class="mt-2 flex-1 min-h-0 border border-border rounded-lg overflow-hidden">
                    <table class="w-full h-full table-fixed border-collapse text-xs">
                      <colgroup>
                        <col class="w-[66.67%]" />
                        <col class="w-[16.67%]" />
                        <col class="w-[16.67%]" />
                      </colgroup>
                      <thead>
                        <tr class="text-muted-foreground">
                          <th class="text-center font-medium py-1.5 px-2 border-b border-border">{{ $t("views.settings.colModel") }}</th>
                          <th class="text-center font-medium py-1.5 px-2 border-b border-border border-l border-l-border/25">{{ $t("views.settings.colTasks") }}</th>
                          <th class="text-center font-medium py-1.5 px-2 border-b border-border border-l border-l-border/25">{{ $t("views.settings.colGpu") }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-if="cacheRows.length === 0" class="h-9 border-b border-border/25 last:border-b-0">
                          <td colspan="3" class="text-center text-muted-foreground/50">{{ $t("views.settings.noCache") }}</td>
                        </tr>
                        <tr v-for="row in cacheRows" :key="`${row.id}@${row.gpu}`" class="h-9 border-b border-border/25 last:border-b-0">
                          <td class="px-2 min-w-0">
                            <span class="flex items-center gap-2 min-w-0 text-left"><button class="shrink-0 p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors hover:text-destructive" v-tooltip="$t('views.settings.unloadModel')" @click="unloadModel(row.id)"><XCircle class="w-4 h-4" /></button><span class="truncate font-mono" :title="row.id">{{ row.id }}</span></span>
                          </td>
                          <td class="px-2 text-center font-mono tabular-nums border-l border-l-border/25">{{ row.count }}</td>
                          <td class="px-2 text-center font-mono text-muted-foreground border-l border-l-border/25">GPU {{ row.gpu }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>

              <section class="flex-1 min-w-0 space-y-4">
                <div class="space-y-1"><h3 class="text-sm font-medium flex items-center gap-2"><FolderOpen class="w-4 h-4 text-muted-foreground" /> {{ $t("views.settings.qwenBackend") }}</h3><p class="text-xs text-muted-foreground">{{ $t("views.settings.qwenBackendHint") }}</p></div>
                <div class="space-y-4">
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.branch") }}</label><AppSelect v-model="backendBranch" :options="branchSelectOptions" /></div>
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.projectDir") }}</label><input v-model="projectDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.projectDirPlaceholder')" /></div>
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.envDir") }}</label><input v-model="envDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.envDirPlaceholder')" /></div>
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.modelDir") }}</label><input v-model="modelDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.modelDirPlaceholder')" /></div>
                  <div class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.voiceDir") }}</label><input v-model="voiceDir" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.settings.voiceDirPlaceholder')" /></div>
                  <div v-if="isFasterBranch" class="space-y-1.5"><label class="label-sm">{{ $t("views.settings.maxSeqLen") }}</label><input v-model.number="maxSeqLen" type="number" min="1" max="32767" step="1" class="w-full px-3 py-2 text-sm" /><p class="text-[10px] text-muted-foreground">{{ $t("views.settings.maxSeqLenHint") }}</p></div>
                </div>
              </section>
            </div>

            <div v-else-if="activeSection === 'batch'" class="max-w-4xl space-y-4">
              <div class="space-y-1"><h3 class="text-sm font-medium flex items-center gap-2"><Gauge class="w-4 h-4 text-muted-foreground" /> {{ $t("views.settings.batchLimits") }}</h3><p class="text-xs text-muted-foreground">{{ $t("views.settings.batchLimitsHint") }}</p></div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-4"><div v-for="field in [
                ['max_segments', 'maxSegments', 1, 100000, 1],
                ['max_output_samples', 'maxOutputSamples', 1, 2000000000, 1],
                ['max_decoded_samples', 'maxDecodedSamples', 1, 2000000000, 1],
                ['max_total_decoded_samples', 'maxTotalDecodedSamples', 1, 2000000000, 1],
                ['max_time_stretch_rate', 'maxTimeStretchRate', 1, 100, 0.1],
                ['max_audio_mib', 'maxAudioMib', 1, 4096, 1],
                ['max_total_audio_mib', 'maxTotalAudioMib', 1, 16384, 1],
                ['min_sample_rate', 'minSampleRate', 1000, 768000, 1],
                ['max_sample_rate', 'maxSampleRate', 1000, 768000, 1],
              ]" :key="field[0]" class="space-y-1.5" :class="field[0] === 'max_segments' && 'md:col-span-2'"><label class="text-xs text-muted-foreground">{{ $t(`views.settings.${field[1]}`) }}</label><input v-model.number="batchComposer[field[0] as keyof BatchComposerSettings]" type="number" :min="field[2]" :max="field[3]" :step="field[4]" class="w-full px-3 py-2 text-sm" /></div></div>
            </div>

            <div v-else class="grid grid-cols-1 xl:grid-cols-[3fr_2fr] gap-10 items-start">
              <section class="space-y-4 min-w-0">
                <div class="flex items-center justify-between"><h3 class="text-sm font-medium flex items-center gap-2"><Settings2 class="w-4 h-4 text-muted-foreground" /> {{ $t("views.settings.defaultGenParams") }}</h3><button class="text-xs text-muted-foreground hover:text-foreground underline" @click="resetDefaultParams">{{ $t("views.settings.resetToDefault") }}</button></div>
                <div class="border rounded-xl bg-card p-4 space-y-4">
                  <div class="flex p-0.5 gap-0.5 border rounded-lg"><button v-for="option in kindOptions" :key="option.value" class="flex-1 px-3 py-2 text-sm rounded-md font-medium transition-all" :class="selectedKind === option.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'" @click="selectedKind = option.value">{{ option.label }}</button></div>
                  <div class="space-y-4">
                  <section class="space-y-3">
                    <div class="text-xs font-medium text-muted-foreground">{{ $t('components.generationParams.talkerSection') }}</div>
                    <div class="grid grid-cols-2 gap-3">
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.doSample') }}</label><AppSelect compact :model-value="samplingValue(defaultParams[selectedKind].do_sample)" :options="samplingOptions" @update:model-value="setSampling('do_sample', $event)" /></div>
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.repPenalty') }}</label><input type="number" min="0.01" max="10" step="0.01" :value="paramValue('repetition_penalty')" placeholder="1.05" class="param-input" @change="setNumber('repetition_penalty', ($event.target as HTMLInputElement).value, 0.01, 10)" /></div>
                    </div>
                    <div class="grid grid-cols-3 gap-3">
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.topK') }}</label><input type="number" min="0" max="32767" step="1" :value="paramValue('top_k')" placeholder="50" :disabled="defaultParams[selectedKind].do_sample === false" class="param-input" @change="setNumber('top_k', ($event.target as HTMLInputElement).value, 0, 32767, true)" /></div>
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.topP') }}</label><input type="number" min="0.01" max="1" step="0.01" :value="paramValue('top_p')" placeholder="1.0" :disabled="defaultParams[selectedKind].do_sample === false" class="param-input" @change="setNumber('top_p', ($event.target as HTMLInputElement).value, 0.01, 1)" /></div>
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.temperature') }}</label><input type="number" min="0.1" max="10" step="0.1" :value="paramValue('temperature')" placeholder="0.9" :disabled="defaultParams[selectedKind].do_sample === false" class="param-input" @change="setNumber('temperature', ($event.target as HTMLInputElement).value, 0.1, 10)" /></div>
                    </div>
                  </section>
                  <section class="border-t pt-3 space-y-3">
                    <div class="text-xs font-medium text-muted-foreground">{{ $t('components.generationParams.subtalkerSection') }}</div>
                    <div class="grid grid-cols-2 gap-3">
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.doSample') }}</label><AppSelect compact :model-value="samplingValue(defaultParams[selectedKind].subtalker_dosample)" :options="samplingOptions" @update:model-value="setSampling('subtalker_dosample', $event)" /></div>
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.topK') }}</label><input type="number" min="0" max="32767" step="1" :value="paramValue('subtalker_top_k')" placeholder="50" :disabled="defaultParams[selectedKind].subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_top_k', ($event.target as HTMLInputElement).value, 0, 32767, true)" /></div>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.topP') }}</label><input type="number" min="0.01" max="1" step="0.01" :value="paramValue('subtalker_top_p')" placeholder="1.0" :disabled="defaultParams[selectedKind].subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_top_p', ($event.target as HTMLInputElement).value, 0.01, 1)" /></div>
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.temperature') }}</label><input type="number" min="0.1" max="10" step="0.1" :value="paramValue('subtalker_temperature')" placeholder="0.9" :disabled="defaultParams[selectedKind].subtalker_dosample === false" class="param-input" @change="setNumber('subtalker_temperature', ($event.target as HTMLInputElement).value, 0.1, 10)" /></div>
                    </div>
                  </section>
                  <section class="border-t pt-3 space-y-3">
                    <div class="text-xs font-medium text-muted-foreground">{{ $t('components.generationParams.lengthSection') }}</div>
                    <div class="grid grid-cols-2 gap-3">
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.minNewTokens') }}</label><input type="number" min="1" max="32767" step="1" :value="paramValue('min_new_tokens')" :placeholder="$t('components.generationParams.notSet')" class="param-input" @change="setNumber('min_new_tokens', ($event.target as HTMLInputElement).value, 1, 32767, true)" /></div>
                      <div class="space-y-1.5"><label class="text-[10px] text-muted-foreground">{{ $t('components.generationParams.maxNewTokens') }}</label><input type="number" min="1" max="32767" step="1" :value="paramValue('max_new_tokens')" placeholder="2048" class="param-input" @change="setNumber('max_new_tokens', ($event.target as HTMLInputElement).value, 1, 32767, true)" /></div>
                    </div>
                    <div class="flex items-center justify-between gap-3"><label class="text-xs text-muted-foreground">{{ $t('components.generationParams.nonStreamingMode') }}</label><AppSelect compact :model-value="triStateValue(defaultParams[selectedKind].non_streaming_mode)" :options="triStateOptions" @update:model-value="setTriState" /></div>
                  </section>
                  </div>
                </div>
              </section>
              <section class="space-y-3 min-w-0"><h3 class="text-sm font-medium flex items-center gap-2"><SlidersHorizontal class="w-4 h-4 text-muted-foreground" /> {{ $t("views.settings.other") }}</h3><div class="space-y-2"><div class="flex items-center gap-2"><Volume2 class="w-4 h-4 text-muted-foreground" /><span class="text-xs text-muted-foreground">{{ $t("views.settings.globalVolume") }}</span></div><div class="flex items-center gap-3"><AppSlider v-model="globalVolume" :min="0" :max="100" :step="1" :format="(v: number) => v + '%'" class="flex-1" /></div></div></section>
            </div>
          </div>
          <div v-if="activeSection === 'server'" class="hidden xl:block absolute w-px bg-border left-1/2 -translate-x-1/2 top-16 bottom-4 pointer-events-none"></div>
          <div v-if="activeSection === 'user'" class="hidden xl:block absolute w-px bg-border left-[calc(60%-8px)] -translate-x-1/2 top-16 bottom-4 pointer-events-none"></div>
        </section>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.param-input {
  @apply w-full px-2 py-1.5 text-xs border rounded-lg bg-background transition-colors duration-150 focus:border-primary focus:ring-1 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50;
}
</style>
