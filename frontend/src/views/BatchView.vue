<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onActivated, onBeforeUnmount, onDeactivated } from "vue"
import type { ComponentPublicInstance } from "vue"
import { watch } from "vue"
import { useStorage } from "@vueuse/core"
import Skeleton from "../components/common/Skeleton.vue"
import { Trash2, Settings, Plus, FileText, Upload, X, WandSparkles, ListChecks, AlertTriangle, Check } from "@lucide/vue"
import ModelConfigPanel from "../components/batch/ModelConfigPanel.vue"
import type { ModelConfig } from "../components/batch/ModelConfigPanel.vue"
import BatchAudioOutput from "../components/batch/BatchAudioOutput.vue"
import BatchGenerationControls from "../components/batch/BatchGenerationControls.vue"
import BatchTaskTable from "../components/batch/BatchTaskTable.vue"
import BatchImportDialogs from "../components/batch/BatchImportDialogs.vue"
import BatchSettingsDialogs from "../components/batch/BatchSettingsDialogs.vue"
import { t } from "../lang"
import { useUserConfig } from "../composables/useUserConfig"
import { useBatchCache } from "../composables/useBatchCache"
import { useBatchAudio } from "../composables/useBatchAudio"
import { useBatchGeneration } from "../composables/useBatchGeneration"
import { useBatchBackup } from "../composables/useBatchBackup"
import { useBatchModelConfigs } from "../composables/useBatchModelConfigs"
import { useBatchRequestBuilder } from "../composables/useBatchRequestBuilder"
import { useBatchImport } from "../composables/useBatchImport"
import { useBatchRowInteractions } from "../composables/useBatchRowInteractions"
import { usePageKeepAlive } from "../composables/usePageKeepAlive"
import type { BatchRow } from "../composables/useBatchTypes"
import { audioCacheDB } from "../utils/audioCacheDB"
import { useModelStore } from "../stores/model"
import { useVoiceStore } from "../stores/voice"

const modelStore = useModelStore()
const voiceStore = useVoiceStore()
import { destructiveColor } from "../theme"
import { synthesisApi } from "../api/synthesis"
import { speakerLabel } from "../constants/options"

function createRow(text = ""): BatchRow {
  const firstBase = modelStore.baseModels[0]
  const firstVoice = voiceStore.voices[0]
  return {
    id: crypto.randomUUID(),
    text,
    modelKind: "base",
    model: firstBase?.id ?? "",
    speaker: "",
    instruct: "",
    voiceDescription: "",
    voiceFile: firstVoice?.name ?? "",
    refText: "",
    xvecOnly: false,
    cloneSource: "voice_file",
    refAudioUrl: "",
    refAudioName: "",
    timelineEnabled: false,
    timelineStart: 0,
    timelineEnd: 0,
    language: "Auto",
    generationParams: { ...defaultParams.value.base },
    finalized: false,
    isPlaying: false,
    audioState: "none",
  }
}

const pageLoading = ref(true)
const rows = ref<BatchRow[]>([])
const selectedIndexes = ref<Set<number>>(new Set())
const editingIndex = ref(-1)

type BatchTaskTableExposed = ComponentPublicInstance & {
  scrollToStart: () => void
  scrollToEnd: () => void
}
const taskTableRef = ref<BatchTaskTableExposed | null>(null)
const { globalVolume, defaultParams } = useUserConfig()
const { importConfig, batchConfig, batchCurrentKind, batchKindStore } = useBatchModelConfigs({
  modelStore,
  voiceStore,
  defaultParams,
})
const { buildRequest } = useBatchRequestBuilder()
const {
  rowProgress, tableVolume,
  togglePlayRow, onSeekWaveform,
  destroyRowAudio, destroyAllAudio, downloadRowAudio, onTableVolumeWheel,
} = useBatchAudio({ rows, initialVolume: globalVolume.value / 100 })

const activeRow = computed(() => editingIndex.value >= 0 ? rows.value[editingIndex.value] : null)

interface ErrorEntry {
  id: string
  index: number
  message: string
}

const errors = ref<ErrorEntry[]>([])

function addError(rowId: string, message: string) {
  const idx = rows.value.findIndex(r => r.id === rowId)
  errors.value.push({ id: crypto.randomUUID(), index: idx + 1, message })
}

function clearErrors() {
  errors.value = []
}

// Batch generation state
const format = ref("wav")
const sampleRate = ref(24000)
const gain = ref(0)
const generating = ref(false)
const {
  editingTextId,
  editingTextValue,
  dragRowIndex,
  onRowClick,
  toggleRowSelect,
  startEditText,
  confirmEditText,
  cancelEditText,
  onRowDragStart,
  onRowDragEnterItem,
  onRowDragEnd,
  adjustIndexesAfterRemove,
} = useBatchRowInteractions({ rows, selectedIndexes, editingIndex, generating })
const generationTime = ref("--:--")
const rtf = ref("--")
const persistent = ref(true)
const priorityMode = ref<"model" | "serial">("model")
const strictMode = ref(false)
const concurrentTasks = ref(1)
const minSilenceMs = ref(300)
const fillTimeline = ref(true)
const {
  showTextImport,
  showFileImport,
  importText,
  importSplitChars,
  importRetainSplit,
  importSplitMode,
  importFiles,
  fileImportError,
  isDragging,
  dragFileIndex,
  confirmTextImport,
  onFileDragOver,
  onFileDragEnter,
  onFileDragLeave,
  onFileDrop,
  onFileInput,
  onFileDragStart,
  onFileDragEnterItem,
  onFileDragEnd,
  removeImportFile,
  confirmFileImport,
} = useBatchImport({ rows, importConfig, fillTimeline, createRow })
const completedCount = ref(0)
const totalAudioDuration = ref(0)
const composing = ref(false)
const finalAudioUrl = ref("")
const zipUrl = ref("")
const subtitleSrt = ref("")
const composeError = ref("")
const refAudioCached = new Set<string>()

const { saveCache, restoreCache, clearCache } = useBatchCache({
  rows, selectedIndexes, editingIndex, persistent,
  format, sampleRate, gain, priorityMode, strictMode,
  concurrentTasks, minSilenceMs, generationTime, rtf,
  finalAudioUrl, zipUrl, subtitleSrt, refAudioCached,
})

const isPaused = ref(false)

const {
  toggleBatchGenerate,
  stopBatchGenerate,
  stopRowGenerate: stopBatchRowGenerate,
  retryFailed,
} = useBatchGeneration({
  rows, format, sampleRate, strictMode, minSilenceMs,
  priorityMode, concurrentTasks, generating, isPaused,
  generationTime, rtf, completedCount, totalAudioDuration,
  composing, composeError, finalAudioUrl, zipUrl, subtitleSrt,
  persistent, buildRequest, addError,
})

const keepAlive = useStorage("qwen-tts:keep-alive", true)
const { notifyActive } = usePageKeepAlive(keepAlive)
watch([generating, isPaused], () => notifyActive(generating.value || isPaused.value))

function removeSelected() {
  const sorted = [...selectedIndexes.value].sort((a, b) => b - a)
  for (const idx of sorted) removeRow(idx)
}

async function clearAllTasks() {
  rows.value = []
  selectedIndexes.value = new Set()
  editingIndex.value = -1
  refAudioCached.clear()
  await audioCacheDB.clear()
  for (const key of Object.keys(rowProgress)) delete rowProgress[key]
  generationTime.value = "--:--"
  rtf.value = "--"
  finalAudioUrl.value = ""
  zipUrl.value = ""
  subtitleSrt.value = ""
}

const { exportBackup, importBackup } = useBatchBackup({
  rows,
  saveCache,
  restoreCache,
  clearAllTasks,
})

const showBatchOps = ref(false)
const showConfirmClear = ref(false)
const showContextMenu = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const showBatchConfig = ref(false)
const showMoreConfig = ref(false)

const hasSelection = computed(() => selectedIndexes.value.size > 0)
const hasFailedRows = computed(() => rows.value.some(r => r.audioState === "error"))

function toggleBatchOps() {
  showBatchOps.value = !showBatchOps.value
}

function closeBatchOps() {
  showBatchOps.value = false
}

function openContextMenu(ev: MouseEvent) {
  const tag = (ev.target as HTMLElement)?.tagName
  if (tag === "INPUT" || tag === "TEXTAREA" || (ev.target as HTMLElement)?.isContentEditable) return
  if (document.getSelection()?.toString()) return
  ev.preventDefault()
  contextMenuX.value = ev.clientX
  contextMenuY.value = ev.clientY
  showContextMenu.value = true
}

function closeContextMenu() {
  showContextMenu.value = false
}

function generateSelected() {
  const sorted = [...selectedIndexes.value].sort((a, b) => a - b)
  for (const idx of sorted) {
    if (rows.value[idx] && !rows.value[idx].finalized) {
      generateRow(idx)
    }
  }
}

function finalizeSelected() {
  for (const idx of selectedIndexes.value) {
    if (rows.value[idx]) {
      rows.value[idx].finalized = true
    }
  }
  selectedIndexes.value = new Set()
}

function confirmClearAll() {
  showConfirmClear.value = false
  clearAllTasks()
}

function openBatchConfig() {
  const firstIdx = [...selectedIndexes.value][0]
  const src = firstIdx !== undefined ? rows.value[firstIdx] : null
  if (src) {
    batchCurrentKind.value = src.modelKind
    batchKindStore[src.modelKind].value = {
      modelKind: src.modelKind,
      model: src.model,
      speaker: src.speaker,
      instruct: src.instruct,
      voiceDescription: src.voiceDescription,
      voiceFile: src.voiceFile,
      refText: src.refText,
      xvecOnly: src.xvecOnly,
      cloneSource: src.cloneSource,
      refAudioUrl: src.refAudioUrl,
      refAudioName: src.refAudioName,
      timelineEnabled: src.timelineEnabled,
      timelineStart: src.timelineStart,
      timelineEnd: src.timelineEnd,
      language: src.language,
      generationParams: { ...src.generationParams },
      text: "",
    }
  } else {
    batchCurrentKind.value = "base"
  }
  showBatchConfig.value = true
}

function applyBatchConfig(config: ModelConfig) {
  for (const idx of selectedIndexes.value) {
    const row = rows.value[idx]
    if (row && !row.finalized && row.audioState !== "generating") {
      row.modelKind = config.modelKind
      row.model = config.model
      row.speaker = config.speaker
      row.instruct = config.instruct
      row.voiceDescription = config.voiceDescription
      row.voiceFile = config.voiceFile
      row.refText = config.refText
      row.xvecOnly = config.xvecOnly
      row.cloneSource = config.cloneSource
      row.refAudioUrl = config.refAudioUrl
      row.refAudioName = config.refAudioName
      row.language = config.language
      row.generationParams = { ...config.generationParams }
    }
  }
  showBatchConfig.value = false
}

function downloadZip() {
  if (!zipUrl.value) return
  const doneRows = rows.value.filter(r => r.audioState === "done").length
  const now = new Date()
  const ts = `${now.getFullYear()}_${String(now.getMonth() + 1).padStart(2, "0")}_${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}-${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`
  const name = `${ts} ${doneRows}`
  const a = document.createElement("a")
  a.href = zipUrl.value
  a.download = `${name}.zip`
  a.click()
}
function exportSubtitles() {
  if (!subtitleSrt.value) return
  const doneRows = rows.value.filter(r => r.audioState === "done").length
  const now = new Date()
  const ts = `${now.getFullYear()}_${String(now.getMonth() + 1).padStart(2, "0")}_${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}-${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`
  const name = `${ts} ${doneRows}`
  const srtBlob = new Blob([subtitleSrt.value], { type: "text/plain" })
  const url = URL.createObjectURL(srtBlob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${name}.srt`
  a.click()
  URL.revokeObjectURL(url)
}
function downloadFinal() {
  if (!finalAudioUrl.value) return
  const doneRows = rows.value.filter(r => r.audioState === "done").length
  const now = new Date()
  const ts = `${now.getFullYear()}_${String(now.getMonth() + 1).padStart(2, "0")}_${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}-${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`
  const name = `${ts} ${doneRows}`
  const a = document.createElement("a")
  a.href = finalAudioUrl.value
  a.download = `${name}.${format.value === "pcm" ? "wav" : format.value}`
  a.click()
}
function addRow(event?: MouseEvent) {
  const reverse = event?.shiftKey ?? false
  const row = createRow()
  if (editingIndex.value >= 0) {
    const src = rows.value[editingIndex.value]
    row.modelKind = src.modelKind
    row.model = src.model
    row.speaker = src.speaker
    row.instruct = src.instruct
    row.voiceDescription = src.voiceDescription
    row.voiceFile = src.voiceFile
    row.refText = src.refText
    row.xvecOnly = src.xvecOnly
    row.cloneSource = src.cloneSource
    row.refAudioUrl = src.refAudioUrl
    row.refAudioName = src.refAudioName
    row.timelineEnabled = src.timelineEnabled
    row.timelineStart = src.timelineStart
    row.timelineEnd = src.timelineEnd
    row.language = src.language
    row.generationParams = { ...src.generationParams }
  }
  if (reverse) {
    rows.value.unshift(row)
    editingIndex.value = 0
    nextTick(() => {
      taskTableRef.value?.scrollToStart()
    })
  } else {
    rows.value.push(row)
    editingIndex.value = rows.value.length - 1
    nextTick(() => {
      taskTableRef.value?.scrollToEnd()
    })
  }
}

function removeRow(idx: number) {
  if (rows.value[idx]?.finalized) return
  const rowId = rows.value[idx]?.id
  if (rowId) {
    audioCacheDB.remove(rowId); audioCacheDB.removeRefAudio(rowId); refAudioCached.delete(rowId); delete rowProgress[rowId]
    destroyRowAudio(rowId)
  }
  adjustIndexesAfterRemove(idx)
  rows.value.splice(idx, 1)
}

const rowGenerationControllers = new Map<string, AbortController>()

async function generateRow(idx: number) {
  const row = rows.value[idx]
  if (!row || row.finalized || row.audioState === "generating") return
  const controller = new AbortController()
  rowGenerationControllers.get(row.id)?.abort()
  rowGenerationControllers.set(row.id, controller)
  row.audioState = "generating"
  try {
    const req = await buildRequest(row)
    controller.signal.throwIfAborted()
    const blob = await synthesisApi.synthesize(req, controller.signal)
    controller.signal.throwIfAborted()
    if (rowGenerationControllers.get(row.id) !== controller) return
    row.audioUrl = URL.createObjectURL(blob)
    audioCacheDB.put(row.id, blob)
    row.audioState = "done"
  } catch (e: any) {
    if (controller.signal.aborted || e?.name === "AbortError") {
      if (
        rowGenerationControllers.get(row.id) === controller
        && row.audioState === "generating"
      ) {
        row.audioState = "none"
      }
      return
    }
    row.audioState = "error"
    row.errorMessage = e?.message || t('views.batch.row.generateFailed')
    addError(row.id, e?.message || t('views.batch.row.generateFailed'))
  } finally {
    if (rowGenerationControllers.get(row.id) === controller) {
      rowGenerationControllers.delete(row.id)
    }
  }
}

function stopRowGenerate(rowId: string) {
  const controller = rowGenerationControllers.get(rowId)
  if (controller) {
    controller.abort()
    rowGenerationControllers.delete(rowId)
  }
  stopBatchRowGenerate(rowId)
  const row = rows.value.find(item => item.id === rowId)
  if (row?.audioState === "generating") row.audioState = "none"
}

function toggleRowFinalized(index: number) {
  const row = rows.value[index]
  if (!row || row.audioState !== "done") return
  row.finalized = !row.finalized
  if (row.finalized) {
    const selection = new Set(selectedIndexes.value)
    selection.delete(index)
    selectedIndexes.value = selection
  }
}

function voiceLabel(row: BatchRow): string {
  if (row.modelKind === "base") return row.cloneSource === "upload" ? (row.refAudioName || t('views.batch.row.base')) : row.voiceFile || t('views.batch.row.notSelected')
  if (row.modelKind === "custom_voice") return speakerLabel(row.speaker) || row.speaker || t('views.batch.row.notSelected')
  return t('views.batch.row.voiceDesign')
}

function onConfigUpdate(val: ModelConfig) {
  if (editingIndex.value < 0) return
  const row = rows.value[editingIndex.value]
  if (val.refAudioUrl !== row.refAudioUrl) {
    refAudioCached.delete(row.id)
  }
  Object.assign(row, val)
}

onMounted(async () => {
  pageLoading.value = true
  await restoreCache()
  pageLoading.value = false
  document.addEventListener("click", onDocumentClick)
  document.addEventListener("keydown", onKeyDown)
})

onDeactivated(() => {
  editingTextId.value = null
  document.removeEventListener("click", onDocumentClick)
  document.removeEventListener("keydown", onKeyDown)
  destroyAllAudio()
  for (const row of rows.value) {
    if (row.isPlaying) row.isPlaying = false
  }
})

onActivated(() => {
  document.addEventListener("click", onDocumentClick)
  document.addEventListener("keydown", onKeyDown)
  // Batch generation stays alive while this KeepAlive page is inactive.
})

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick)
  document.removeEventListener("keydown", onKeyDown)
  stopBatchGenerate()
  for (const controller of rowGenerationControllers.values()) controller.abort()
  rowGenerationControllers.clear()
  destroyAllAudio()
})

function onDocumentClick(ev: MouseEvent) {
  const target = ev.target as HTMLElement
  if (!target.closest("[data-batch-ops]")) {
    showBatchOps.value = false
  }
  if (!target.closest("[data-context-menu]")) {
    showContextMenu.value = false
  }
}

function onKeyDown(ev: KeyboardEvent) {
  if ((ev.ctrlKey || ev.metaKey) && ev.key === "a") {
    const tag = (ev.target as HTMLElement)?.tagName
    if (tag === "INPUT" || tag === "TEXTAREA" || (ev.target as HTMLElement)?.isContentEditable) return
    if (document.getSelection()?.toString()) return
    ev.preventDefault()
    const selectAll = new Set<number>()
    rows.value.forEach((r, i) => { if (!r.finalized) selectAll.add(i) })
    selectedIndexes.value = selectAll
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && ev.key.toLowerCase() === "i") {
    const tag = (ev.target as HTMLElement)?.tagName
    if (tag === "INPUT" || tag === "TEXTAREA" || (ev.target as HTMLElement)?.isContentEditable) return
    ev.preventDefault()
    const inverted = new Set<number>()
    for (let i = 0; i < rows.value.length; i++) {
      if (!rows.value[i]?.finalized && !selectedIndexes.value.has(i)) inverted.add(i)
    }
    selectedIndexes.value = inverted
  }
}
</script>

<template>
  <div class="h-full flex flex-col gap-4">
    <Transition name="fade" mode="out-in">
      <!-- Skeleton loading -->
      <div v-if="pageLoading" key="skeleton" class="flex gap-4 flex-1 min-h-0">
        <div class="flex-[5] min-w-0 flex flex-col gap-3">
          <div class="flex-1 border rounded-xl bg-card overflow-hidden flex flex-col p-3 space-y-2">
            <div class="grid grid-cols-batch gap-2 border-b pb-2">
              <Skeleton v-for="i in 9" :key="i" class="h-4" />
            </div>
            <Skeleton v-for="i in 4" :key="'r'+i" class="h-9 w-full" />
            <div class="flex gap-2 mt-auto pt-2 border-t">
              <Skeleton v-for="i in 4" :key="'b'+i" class="h-9 flex-1" />
            </div>
          </div>
          <div class="flex gap-2">
            <Skeleton class="h-9 flex-[1.5]" />
            <Skeleton class="h-9 flex-[1]" />
          </div>
        </div>
        <div class="flex-[2] min-w-0 flex flex-col gap-4">
          <div class="flex-1 border rounded-xl bg-card p-3 space-y-3">
            <Skeleton class="h-4 w-32" />
            <Skeleton class="h-8 w-full" />
            <Skeleton class="h-8 w-full" />
            <Skeleton class="h-8 w-3/4" />
            <Skeleton class="h-8 w-full" />
            <Skeleton class="h-20 w-full" />
          </div>
          <div class="border rounded-xl bg-card p-3 space-y-2">
            <Skeleton class="h-4 w-16" />
            <Skeleton class="h-4 w-full" />
          </div>
        </div>
      </div>

      <!-- Content -->
      <div v-else key="content" class="flex gap-4 flex-1 min-h-0">
        <!-- Left: Table + Add buttons (4) | Controls (1) -->
        <div class="flex-[5] min-w-0 flex flex-col gap-3">
          <div class="flex-[2] min-h-0 flex flex-col gap-2">
            <BatchTaskTable
              ref="taskTableRef"
              :rows="rows"
              :selected-indexes="selectedIndexes"
              :editing-index="editingIndex"
              :editing-text-id="editingTextId"
              :editing-text-value="editingTextValue"
              :drag-row-index="dragRowIndex"
              :generating="generating"
              :table-volume="tableVolume"
              :row-progress="rowProgress"
              :voice-label="voiceLabel"
              @context-menu="openContextMenu"
              @table-volume-wheel="onTableVolumeWheel"
              @row-click="onRowClick"
              @row-drag-enter="onRowDragEnterItem"
              @toggle-row-select="toggleRowSelect"
              @row-drag-start="onRowDragStart"
              @row-drag-end="onRowDragEnd"
              @start-edit-text="startEditText"
              @update-editing-text="editingTextValue = $event"
              @confirm-edit-text="confirmEditText"
              @cancel-edit-text="cancelEditText"
              @toggle-play-row="togglePlayRow"
              @seek-waveform="onSeekWaveform"
              @download-row-audio="downloadRowAudio"
              @remove-row="removeRow"
              @generate-row="generateRow"
              @stop-row-generate="stopRowGenerate"
              @toggle-batch-generate="toggleBatchGenerate"
              @toggle-finalized="toggleRowFinalized"
              @toggle-details="editingIndex = editingIndex === $event ? -1 : $event"
            >
              <template #footer>
                <!-- Bottom action buttons -->
                <div class="flex shrink-0 border-t border-border" data-batch-ops>
                  <div class="flex-1 relative">
                    <button
                      class="w-full flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium hover:bg-accent transition-colors"
                      @click="toggleBatchOps"
                    >
                      <ListChecks class="w-3.5 h-3.5" /> {{ $t('views.batch.batchOp') }}
                    </button>
                    <Transition name="popover">
                      <div v-if="showBatchOps" class="absolute bottom-full left-0 right-0 mb-1 border rounded-xl bg-card shadow-lg overflow-hidden z-50">
                        <button
                          class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
                          :class="hasSelection
                            ? 'hover:bg-accent cursor-pointer'
                            : 'text-muted-foreground/30 cursor-not-allowed'"
                          :disabled="!hasSelection"
                          @click="hasSelection && (closeBatchOps(), openBatchConfig())"
                        >
                          <Settings class="w-3.5 h-3.5" /> {{ $t('views.batch.batchOps.configSelected') }}
                        </button>
                        <div class="h-px bg-border mx-3" />
                        <button
                          class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
                          :class="hasSelection
                            ? 'hover:bg-accent cursor-pointer'
                            : 'text-muted-foreground/30 cursor-not-allowed'"
                          :disabled="!hasSelection"
                          @click="hasSelection && (closeBatchOps(), generateSelected())"
                        >
                          <WandSparkles class="w-3.5 h-3.5" /> {{ $t('views.batch.batchOps.generateSelected') }}
                        </button>
                        <div class="h-px bg-border mx-3" />
                        <button
                          class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
                          :class="hasSelection
                            ? 'hover:bg-accent cursor-pointer'
                            : 'text-muted-foreground/30 cursor-not-allowed'"
                          :disabled="!hasSelection"
                          @click="hasSelection && (closeBatchOps(), finalizeSelected())"
                        >
                          <Check class="w-3.5 h-3.5" /> {{ $t('views.batch.batchOps.finalizeSelected') }}
                        </button>
                        <div class="h-px bg-border mx-3" />
                        <button
                          class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
                          :class="hasSelection
                            ? 'hover:bg-status-destructive/10 cursor-pointer'
                            : 'cursor-not-allowed'"
                          :style="{ color: hasSelection ? destructiveColor() : undefined, opacity: hasSelection ? 1 : 0.3 }"
                          :disabled="!hasSelection"
                          @click="hasSelection && (closeBatchOps(), removeSelected())"
                        >
                          <Trash2 class="w-3.5 h-3.5" /> {{ $t('views.batch.batchOps.deleteSelected') }}
                        </button>
                        <div class="h-px bg-border mx-3" />
                        <button class="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-status-destructive/10 transition-colors cursor-pointer" :style="{ color: destructiveColor() }" @click="closeBatchOps(); showConfirmClear = true">
                          <AlertTriangle class="w-3.5 h-3.5" /> {{ $t('views.batch.batchOps.clearAll') }}
                        </button>
                      </div>
                    </Transition>
                  </div>
                  <div class="w-px bg-border self-center h-6" />
                  <button class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium hover:bg-accent transition-colors" @click="showTextImport = true">
                    <FileText class="w-3.5 h-3.5" /> {{ $t('views.batch.addFromText') }}
                  </button>
                  <div class="w-px bg-border self-center h-6" />
                  <button class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium hover:bg-accent transition-colors" @click="showFileImport = true">
                    <Upload class="w-3.5 h-3.5" /> {{ $t('views.batch.addFromFile') }}
                  </button>
                  <div class="w-px bg-border self-center h-6" />
                  <button class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium hover:bg-accent transition-colors" @click="addRow($event)">
                    <Plus class="w-3.5 h-3.5" /> {{ $t('views.batch.addRow') }}
                  </button>
                </div>
              </template>
            </BatchTaskTable>
          </div>

        <!-- Controls (1) -->
        <div class="flex-[1] min-h-0 flex gap-2">
          <BatchAudioOutput
            class="flex-[1.5] min-w-0"
            :generation-time="generationTime"
            :rtf="rtf"
            :final-audio-url="finalAudioUrl"
            :subtitles="subtitleSrt"
            :has-zip="!!zipUrl"
            :has-subtitles="!!subtitleSrt"
            @download-zip="downloadZip"
            @export-subtitles="exportSubtitles"
            @download-final="downloadFinal"
          />
          <BatchGenerationControls
            class="flex-[1] min-w-0"
            :generating="generating"
            :paused="isPaused"
            :can-retry="hasFailedRows"
            @update:format="format = $event"
            @update:sample-rate="sampleRate = Number($event)"
            @update:gain="gain = $event"
            @toggle-generate="toggleBatchGenerate"
            @stop-generate="stopBatchGenerate"
            @retry-failed="retryFailed"
            @open-more-config="showMoreConfig = true"
          />
        </div>
      </div>

      <!-- Right: Config Panel + Status -->
      <div class="flex-[2] min-w-0 flex flex-col gap-4">
        <div v-if="activeRow" class="border rounded-xl bg-card flex flex-col overflow-hidden flex-1 min-h-0">
          <div class="overflow-y-auto p-3 flex-1">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-medium text-muted-foreground">
                {{ $t('views.batch.configPanel.title', { index: editingIndex + 1 }) }}
              </span>
              <button class="text-muted-foreground hover:text-foreground transition-colors" @click="editingIndex = -1">
                <X class="w-3.5 h-3.5" />
              </button>
            </div>
            <ModelConfigPanel
              :disabled="activeRow.finalized || activeRow.audioState === 'generating'"
              :model-value="{
                text: activeRow.text,
                modelKind: activeRow.modelKind,
                model: activeRow.model,
                speaker: activeRow.speaker,
                instruct: activeRow.instruct,
                voiceDescription: activeRow.voiceDescription,
                voiceFile: activeRow.voiceFile,
                refText: activeRow.refText,
                xvecOnly: activeRow.xvecOnly,
                cloneSource: activeRow.cloneSource,
                refAudioUrl: activeRow.refAudioUrl,
                refAudioName: activeRow.refAudioName,
                timelineEnabled: activeRow.timelineEnabled,
                timelineStart: activeRow.timelineStart,
                timelineEnd: activeRow.timelineEnd,
                language: activeRow.language,
                generationParams: activeRow.generationParams,
              }"
              @update:model-value="onConfigUpdate"
            />
          </div>
        </div>
        <div v-else class="border rounded-xl bg-card flex flex-col items-center justify-center text-xs text-muted-foreground gap-2 py-12 flex-1 min-h-0">
          <Settings class="w-8 h-8 text-muted-foreground/20" />
          <span>{{ $t('views.batch.configPanel.placeholder') }}</span>
        </div>

        <!-- Status -->
        <div class="border rounded-xl bg-card px-3 py-2.5 shrink-0">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-xs font-medium text-muted-foreground">{{ $t('views.batch.statusPanel.title') }}</span>
            <button
              class="text-xs text-muted-foreground/50 hover:text-foreground transition-colors px-1.5 py-0.5 rounded hover:bg-accent"
              @click="clearErrors"
            >{{ $t('views.batch.statusPanel.clear') }}</button>
          </div>
          <div class="text-xs leading-5 overflow-y-auto whitespace-pre-wrap"
            style="height: calc(5 * 1.25rem)"
          >
            <div v-if="composing" class="text-yellow-500 leading-5">
              <span class="animate-spin inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full mr-1 align-middle" />
              {{ $t('views.batch.row.composeOngoing') }}
            </div>
            <div v-if="composeError" class="text-red-500 leading-5">
              {{ $t('views.batch.row.composeFailed') }}{{ composeError }}
            </div>
            <div v-for="err in errors" :key="err.id" class="leading-5">
              [<span class="text-blue-500">#{{ err.index }}</span>] <span class="text-red-500">{{ err.message }}</span>
            </div>
            <div v-if="errors.length === 0 && !composing && !composeError" class="text-muted-foreground/30 italic">{{ $t('views.batch.statusPanel.noErrors') }}</div>
          </div>
        </div>
      </div>
    </div>
    </Transition>

  <BatchImportDialogs
    v-model:show-text-import="showTextImport"
    v-model:show-file-import="showFileImport"
    v-model:import-text="importText"
    v-model:import-split-chars="importSplitChars"
    v-model:import-retain-split="importRetainSplit"
    v-model:import-split-mode="importSplitMode"
    v-model:import-config="importConfig"
    v-model:fill-timeline="fillTimeline"
    :import-files="importFiles"
    :file-import-error="fileImportError"
    :is-dragging="isDragging"
    :drag-file-index="dragFileIndex"
    @confirm-text-import="confirmTextImport"
    @file-input="onFileInput"
    @file-drag-over="onFileDragOver"
    @file-drag-enter="onFileDragEnter"
    @file-drag-leave="onFileDragLeave"
    @file-drop="onFileDrop"
    @file-drag-start="onFileDragStart"
    @file-drag-enter-item="onFileDragEnterItem"
    @file-drag-end="onFileDragEnd"
    @remove-import-file="removeImportFile"
    @confirm-file-import="confirmFileImport"
  />

  <!-- Context Menu -->
  <Transition name="popover">
    <div
      v-if="showContextMenu"
      class="fixed z-[60] w-40 border rounded-xl bg-card shadow-lg overflow-hidden"
      :style="{ left: contextMenuX + 'px', top: contextMenuY + 'px' }"
      data-context-menu
      @click.stop
    >
      <button
        class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
        :class="hasSelection
          ? 'hover:bg-accent cursor-pointer'
          : 'text-muted-foreground/30 cursor-not-allowed'"
        :disabled="!hasSelection"
        @click="hasSelection && (closeContextMenu(), openBatchConfig())"
      >
        <Settings class="w-3.5 h-3.5" /> {{ $t('views.batch.contextMenu.configSelected') }}
      </button>
      <div class="h-px bg-border mx-3" />
      <button
        class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
        :class="hasSelection
          ? 'hover:bg-accent cursor-pointer'
          : 'text-muted-foreground/30 cursor-not-allowed'"
        :disabled="!hasSelection"
        @click="hasSelection && (closeContextMenu(), generateSelected())"
      >
        <WandSparkles class="w-3.5 h-3.5" /> {{ $t('views.batch.contextMenu.generateSelected') }}
      </button>
      <div class="h-px bg-border mx-3" />
      <button
        class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
        :class="hasSelection
          ? 'hover:bg-accent cursor-pointer'
          : 'text-muted-foreground/30 cursor-not-allowed'"
        :disabled="!hasSelection"
        @click="hasSelection && (closeContextMenu(), finalizeSelected())"
      >
        <Check class="w-3.5 h-3.5" /> {{ $t('views.batch.contextMenu.finalizeSelected') }}
      </button>
      <div class="h-px bg-border mx-3" />
      <button
        class="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors"
        :class="hasSelection
          ? 'hover:bg-status-destructive/10 cursor-pointer'
          : 'cursor-not-allowed'"
        :style="{ color: hasSelection ? destructiveColor() : undefined, opacity: hasSelection ? 1 : 0.3 }"
        :disabled="!hasSelection"
        @click="hasSelection && (closeContextMenu(), removeSelected())"
      >
        <Trash2 class="w-3.5 h-3.5" /> {{ $t('views.batch.contextMenu.deleteSelected') }}
      </button>
      <div class="h-px bg-border mx-3" />
      <button class="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-status-destructive/10 transition-colors cursor-pointer" :style="{ color: destructiveColor() }" @click="closeContextMenu(); showConfirmClear = true">
        <AlertTriangle class="w-3.5 h-3.5" /> {{ $t('views.batch.contextMenu.clearAll') }}
      </button>
    </div>
  </Transition>

  <BatchSettingsDialogs
    v-model:show-confirm-clear="showConfirmClear"
    v-model:show-batch-config="showBatchConfig"
    v-model:show-more-config="showMoreConfig"
    v-model:batch-config="batchConfig"
    v-model:persistent="persistent"
    v-model:keep-alive="keepAlive"
    v-model:priority-mode="priorityMode"
    v-model:strict-mode="strictMode"
    v-model:min-silence-ms="minSilenceMs"
    v-model:concurrent-tasks="concurrentTasks"
    @confirm-clear="confirmClearAll"
    @apply-batch-config="applyBatchConfig"
    @clear-cache="clearCache"
    @save-cache="saveCache"
    @export-backup="exportBackup"
    @import-backup="importBackup"
  />
  </div>
</template>

<style scoped>
.grid-cols-batch {
  grid-template-columns: 1fr 1fr 6fr 2fr 6fr 1fr 1fr 1fr 1fr;
}

.popover-enter-active,
.popover-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.popover-enter-from,
.popover-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

</style>
