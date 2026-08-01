<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue"
import {
  Search, Trash2, Save, RefreshCw, MicVocal, ChevronRight, Folder,
} from "@lucide/vue"
import AudioEditor from "../components/audio/AudioEditor.vue"
import AutoTextarea from "../components/common/AutoTextarea.vue"
import AppCheckbox from "../components/common/AppCheckbox.vue"
import AppSelect from "../components/common/AppSelect.vue"
import ConfirmDialog from "../components/common/ConfirmDialog.vue"
import { voicesApi, type VoiceMeta } from "../api/voices"
import { modelsApi } from "../api/models"
import { useModelStore } from "../stores/model"
import { useToast } from "../composables/useToast"
import Skeleton from "../components/common/Skeleton.vue"
import { t } from "../lang"

const modelStore = useModelStore()

// ── Voice list (Level 1) ────────────────────────────────────────

const voiceNames = ref<string[]>([])
const loading = ref(false)
const error = ref("")

async function fetchVoices() {
  loading.value = true
  error.value = ""
  try {
    const res = await voicesApi.list()
    voiceNames.value = res.voices
  } catch (e: any) {
    error.value = e?.message ?? t('views.voices.fetchFailed')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    fetchVoices(),
    modelsApi.list().then((res) => modelStore.setModels(res.models)).catch(() => undefined),
    modelStore.refreshCacheStatus(),
  ])
})

// ── Search & tree ───────────────────────────────────────────────

const searchQuery = ref("")
const expandedFolders = ref<Set<string>>(new Set())
const _preSearchExpanded = ref<Set<string>>(new Set())

interface TreeNode {
  type: "folder" | "voice"
  name: string
  path: string
  children?: TreeNode[]
}

const voiceTree = computed<TreeNode[]>(() => {
  const q = searchQuery.value.toLowerCase()
  const filtered = q
    ? voiceNames.value.filter((v) => v.toLowerCase().includes(q))
    : voiceNames.value

  function sortTree(nodes: TreeNode[]) {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "folder" ? -1 : 1
      return a.name.localeCompare(b.name, "zh-CN")
    })
    for (const n of nodes) {
      if (n.children) sortTree(n.children)
    }
  }

  const root: TreeNode[] = []
  const map = new Map<string, TreeNode>()

  for (const name of filtered) {
    const parts = name.split("/")
    if (parts.length === 1) {
      root.push({ type: "voice", name, path: name })
    } else {
      let parent = root
      let currentPath = ""
      for (let i = 0; i < parts.length - 1; i++) {
        currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i]
        let node = map.get(currentPath)
        if (!node) {
          node = { type: "folder", name: parts[i], path: currentPath, children: [] }
          map.set(currentPath, node)
          parent.push(node)
        }
        parent = node.children!
      }
      parent.push({ type: "voice", name: parts[parts.length - 1], path: name })
    }
  }
  sortTree(root)
  return root
})

function toggleFolder(path: string) {
  const next = new Set(expandedFolders.value)
  if (next.has(path)) next.delete(path); else next.add(path)
  expandedFolders.value = next
}

watch(searchQuery, (q, oldQ) => {
  if (!oldQ && q) {
    _preSearchExpanded.value = new Set(expandedFolders.value)
  }
  if (!q) {
    expandedFolders.value = new Set(_preSearchExpanded.value)
    return
  }
  const expanded = new Set(expandedFolders.value)
  function collect(nodes: TreeNode[]) {
    for (const node of nodes) {
      if (node.type === "folder" && node.children && node.children.length > 0) {
        expanded.add(node.path)
        collect(node.children)
      }
    }
  }
  collect(voiceTree.value)
  expandedFolders.value = expanded
})

const ESC_MAP: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }
function escHtml(s: string) { return s.replace(/[&<>"']/g, c => ESC_MAP[c]) }

function highlightMatch(text: string) {
  const q = searchQuery.value.trim()
  const escapedText = escHtml(text)
  if (!q) return escapedText
  const escapedQ = escHtml(q)
  const reEscaped = escapedQ.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const re = new RegExp(`(${reEscaped})`, "gi")
  return escapedText.replace(re, '<mark class="bg-transparent text-primary font-medium">$1</mark>')
}

// ── Selected voice detail (Level 2) ─────────────────────────────

const selectedName = ref("")
const selectedMeta = ref<VoiceMeta | null>(null)
const metaLoading = ref(false)
const metaError = ref("")

const editName = ref("")
const editText = ref("")
const editAudioUrl = ref<string | null>(null)
const editAudioName = ref<string | null>(null)
const editXvec = ref(false)
const editAudioDirty = ref(false)
const editing = ref(false)
const editError = ref("")
const editSuccess = ref("")

function onEditAudio(file: File | null) {
  if (file) {
    if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
    editAudioUrl.value = URL.createObjectURL(file)
    editAudioName.value = file.name
    editAudioDirty.value = true
  } else {
    if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
    editAudioUrl.value = null
    editAudioName.value = null
    editAudioDirty.value = false
  }
}

async function selectVoice(name: string) {
  selectedName.value = name
  selectedMeta.value = null
  previewLoading.value = false
  metaLoading.value = true
  metaError.value = ""
  previewError.value = ""
  editAudioDirty.value = false
  if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
  editAudioUrl.value = null
  editAudioName.value = null
  editError.value = ""
  editSuccess.value = ""
  try {
    const [meta] = await Promise.all([
      voicesApi.get(name),
      modelStore.refreshCacheStatus(),
    ])
    selectedMeta.value = meta
    editName.value = name
    editText.value = meta.text
    editXvec.value = meta.x_vector_only ?? false
  } catch (e: any) {
    metaError.value = e?.message ?? t('views.voices.fetchDetailFailed')
    metaLoading.value = false
    return
  }
  try {
    previewLoading.value = true
    const result = await voicesApi.audio(name, false)
    if (result.ok && result.audio) {
      if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
      editAudioUrl.value = URL.createObjectURL(decodePreviewAudio(result.audio, result.sr ?? 24000))
      editAudioName.value = `${name.split("/").pop() ?? t('views.voices.referenceAudio')}.wav`
    }
  } catch {
    // no-op: audio decode failure is not critical for first load
  } finally {
    metaLoading.value = false
    previewLoading.value = false
  }
}

// ── Refresh info ────────────────────────────────────────────────

async function refreshInfo() {
  if (!selectedName.value) return
  metaLoading.value = true
  metaError.value = ""
  previewError.value = ""
  try {
    const [meta] = await Promise.all([
      voicesApi.get(selectedName.value),
      modelStore.refreshCacheStatus(),
    ])
    selectedMeta.value = meta
    editName.value = selectedName.value
    editText.value = meta.text
    editXvec.value = meta.x_vector_only ?? false
  } catch (e: any) {
    metaError.value = e?.message ?? t('views.voices.refreshMetaFailed')
    metaLoading.value = false
    return
  }
  try {
    previewLoading.value = true
    const result = await voicesApi.audio(selectedName.value, false)
    if (result.ok && result.audio) {
      if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
      editAudioUrl.value = URL.createObjectURL(decodePreviewAudio(result.audio, result.sr ?? 24000))
      editAudioName.value = `${selectedName.value.split("/").pop() ?? t('views.voices.referenceAudio')}.wav`
    }
  } catch {
    // no-op
  } finally {
    metaLoading.value = false
    previewLoading.value = false
  }
}

// ── Edit save ───────────────────────────────────────────────────

async function saveEdit() {
  if (!selectedName.value || !selectedMeta.value) return
  editError.value = ""
  editSuccess.value = ""
  editing.value = true
  try {
    const changed: { name: string; new_name?: string; text?: string; audio?: string; model?: string; x_vector_only?: boolean } = {
      name: selectedName.value,
    }

    if (editName.value !== selectedName.value) {
      changed.new_name = editName.value
    }
    if (editXvec.value) {
      if (!selectedMeta.value.x_vector_only) {
        changed.x_vector_only = true
      }
    } else {
      if (editText.value !== selectedMeta.value.text) {
        changed.text = editText.value
      }
      if (selectedMeta.value.x_vector_only) {
        changed.x_vector_only = false
      }
    }

    if (editAudioDirty.value && editAudioUrl.value) {
      const resp = await fetch(editAudioUrl.value)
      const blob = await resp.blob()
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result as string)
        reader.onerror = reject
        reader.readAsDataURL(blob)
      })
      changed.audio = base64
      changed.model = selectedMeta.value.model[0] || modelStore.baseModels[0]?.id || undefined
    }

    await voicesApi.edit(changed)
    editSuccess.value = t('views.voices.editSaved')
    await fetchVoices()
    await selectVoice(selectedName.value)
  } catch (e: any) {
    editError.value = e?.message ?? t('views.voices.saveEditFailed')
  } finally {
    editing.value = false
  }
}

// ── Preview audio (Level 3) ─────────────────────────────────────

const previewLoading = ref(false)
const previewError = ref("")

function decodePreviewAudio(base64Audio: string, sampleRate: number): Blob {
  const raw = atob(base64Audio)
  const pcmBytes = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) pcmBytes[i] = raw.charCodeAt(i)

  const samples = new Float32Array(
    pcmBytes.buffer,
    pcmBytes.byteOffset,
    Math.floor(pcmBytes.byteLength / Float32Array.BYTES_PER_ELEMENT),
  )
  const wav = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(wav)
  const writeAscii = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }

  writeAscii(0, "RIFF")
  view.setUint32(4, 36 + samples.length * 2, true)
  writeAscii(8, "WAVE")
  writeAscii(12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeAscii(36, "data")
  view.setUint32(40, samples.length * 2, true)

  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
  return new Blob([wav], { type: "audio/wav" })
}

const baseModelLoaded = computed(() =>
  modelStore.cacheStatus.loaded.some((m) => m.kind === "base"),
)

async function loadModelAndPreview() {
  if (!selectedName.value) return
  previewError.value = ""
  previewLoading.value = true
  try {
    const result = await voicesApi.audio(selectedName.value, true)
    if (result.ok && result.audio) {
      if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
      editAudioUrl.value = URL.createObjectURL(decodePreviewAudio(result.audio, result.sr ?? 24000))
      editAudioName.value = `${selectedName.value.split("/").pop() ?? t('views.voices.referenceAudio')}.wav`
    } else if (result.ok && !result.audio) {
      previewError.value = t('views.voices.noBaseModel')
    } else {
      previewError.value = t('views.voices.decodeFailed')
    }
    await modelStore.refreshCacheStatus()
  } catch (e: any) {
    previewError.value = e?.message ?? t('views.voices.loadModelFailed')
  } finally {
    previewLoading.value = false
  }
}

// ── Delete ──────────────────────────────────────────────────────

const showDeleteConfirm = ref(false)
const deleteTarget = ref("")

function confirmDelete(name: string) {
  deleteTarget.value = name
  showDeleteConfirm.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await voicesApi.delete(deleteTarget.value)
    voiceNames.value = voiceNames.value.filter((v) => v !== deleteTarget.value)
    if (selectedName.value === deleteTarget.value) {
      selectedName.value = ""
      selectedMeta.value = null
      if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
      editAudioUrl.value = null
    }
  } catch {
    // ignore
  }
  showDeleteConfirm.value = false
  deleteTarget.value = ""
}

// ── New voice creation ──────────────────────────────────────────

const newName = ref("")
const newModel = ref("")

watch(() => modelStore.baseModels, (models) => {
  if (models.length > 0 && !models.find(m => m.id === newModel.value)) {
    newModel.value = models[0].id
  }
})
const newAudioUrl = ref<string | null>(null)
const newAudioName = ref<string | null>(null)
const newText = ref("")
const newXvec = ref(false)
const { success: toastSuccess, error: toastError } = useToast()
const saving = ref(false)

function onNewAudio(file: File | null) {
  if (file) {
    newAudioUrl.value = URL.createObjectURL(file)
    newAudioName.value = file.name
  } else {
    if (newAudioUrl.value) URL.revokeObjectURL(newAudioUrl.value)
    newAudioUrl.value = null
    newAudioName.value = null
  }
}

async function saveNewVoice() {
  if (!newName.value.trim()) { toastError(t('views.voices.nameRequired')); return }
  if (!newAudioUrl.value) { toastError(t('views.voices.audioRequired')); return }
  saving.value = true
  try {
    const resp = await fetch(newAudioUrl.value)
    const blob = await resp.blob()
    const base64 = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })

    await voicesApi.upload({
      audio: base64,
      customName: newName.value.trim() || undefined,
      model: newModel.value,
      text: newXvec.value ? undefined : (newText.value || undefined),
      x_vector_only: newXvec.value || undefined,
    })
    toastSuccess(t('views.voices.voiceSaved'))
    await fetchVoices()
  } catch {
    // error already shown via toast
  } finally {
    saving.value = false
  }
}

// Cleanup
import { onBeforeUnmount } from "vue"
onBeforeUnmount(() => {
  if (editAudioUrl.value) URL.revokeObjectURL(editAudioUrl.value)
})
</script>

<template>
  <div class="max-w-full mx-20">
    <div class="flex gap-4 h-[calc(100vh-8rem)]">
      <!-- Left: New Voice Creator -->
      <div class="flex-[2] border rounded-lg p-4 space-y-3 overflow-auto">
        <h3 class="text-sm font-medium">{{ $t('views.voices.addVoice') }}</h3>
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.voices.model') }}</label>
          <AppSelect v-model="newModel" :options="modelStore.baseModels.map(m => ({ value: m.id, label: m.id }))" />
        </div>
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.voices.voiceName') }}</label>
          <input v-model="newName" type="text" class="w-full px-3 py-2 text-sm" :placeholder="$t('views.voices.voiceNamePlaceholder')" />
        </div>
        <div class="space-y-1.5">
<label class="label">{{ $t('views.voices.referenceAudio') }}</label>
                <AudioEditor
            :audio-url="newAudioUrl"
            :audio-name="newAudioName ?? undefined"
            :trim-start="0"
            :trim-end="0"
            @file="onNewAudio"
          />
        </div>
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.voices.referenceText') }}</label>
          <AutoTextarea v-model="newText" :rows="2" :placeholder="$t('views.voices.refTextPlaceholder')" />
        </div>
        <AppCheckbox v-model="newXvec" :label="$t('views.voices.xVectorOnly')" />
        <button
          class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border transition-all duration-150 hover:bg-accent hover:border-primary/30"
          :disabled="saving"
          @click="saveNewVoice"
        >
          <Save class="w-3.5 h-3.5" /> {{ saving ? $t('views.voices.saving') : $t('views.voices.save') }}
        </button>
        
      </div>

      <!-- Manage: Voice List + Editor -->
      <div class="flex-[6] flex gap-4 min-w-0">
        <!-- Voice list -->
        <div class="w-80 border rounded-lg flex flex-col shrink-0">
          <div class="p-3 border-b">
            <div class="relative">
              <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <input
                v-model="searchQuery"
                type="text"
                class="w-full pl-8 pr-3 py-1.5 text-sm"
                :placeholder="$t('views.voices.searchPlaceholder')"
              />
            </div>
          </div>
          <div class="flex-1 overflow-auto">
            <Transition name="fade" mode="out-in">
              <div v-if="loading" key="skeleton" class="px-3 py-4 space-y-3">
                <Skeleton class="h-9 w-full" />
                <Skeleton class="h-9 w-3/4" />
                <Skeleton class="h-9 w-5/6" />
                <Skeleton class="h-9 w-2/3" />
                <Skeleton class="h-9 w-4/5" />
              </div>
              <div v-else-if="error" key="error" class="px-3 py-8 text-xs text-red-500 text-center">{{ error }}</div>
              <div v-else key="list">
                <template v-for="node in voiceTree" :key="node.path">
                <div v-if="node.type === 'folder'">
                  <div
                    class="flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-muted-foreground cursor-pointer hover-overlay select-none"
                    @click="toggleFolder(node.path)"
                  >
                    <ChevronRight class="w-3 h-3 transition-transform duration-150" :class="expandedFolders.has(node.path) ? 'rotate-90' : ''" />
                    <Folder class="w-3.5 h-3.5" />
                    <span v-html="highlightMatch(node.name)"></span>
                  </div>
                  <div v-if="expandedFolders.has(node.path)">
                    <div
                      v-for="child in node.children ?? []"
                      :key="child.path"
                      class="flex items-center gap-2 pl-7 pr-3 py-2 cursor-pointer text-sm hover-overlay"
                      :class="selectedName === child.path ? 'bg-accent' : ''"
                      @click="selectVoice(child.path)"
                    >
                      <MicVocal class="w-4 h-4 shrink-0 text-muted-foreground" />
                      <div class="flex-1 min-w-0">
                        <p class="truncate font-medium" v-html="highlightMatch(child.name)"></p>
                      </div>
                    </div>
                  </div>
                </div>
                <div
                  v-else
                  class="flex items-center gap-2 px-3 py-2.5 cursor-pointer text-sm hover-overlay"
                  :class="selectedName === node.path ? 'bg-accent' : ''"
                  @click="selectVoice(node.path)"
                >
                  <MicVocal class="w-4 h-4 shrink-0 text-muted-foreground" />
                  <div class="flex-1 min-w-0">
                    <p class="truncate font-medium" v-html="highlightMatch(node.name)"></p>
                  </div>
                </div>
              </template>
              <div v-if="voiceTree.length === 0" class="px-3 py-8 text-xs text-muted-foreground text-center">{{ $t('views.voices.noMatch') }}</div>
            </div>
            </Transition>
          </div>
          <button
            class="w-full flex items-center justify-center gap-1 px-2 py-2 text-xs border-t hover:bg-accent transition-colors shrink-0"
            @click="fetchVoices"
          >
            <RefreshCw class="w-3 h-3" :class="loading ? 'animate-spin' : ''" /> {{ $t('views.voices.refresh') }}
          </button>
        </div>

        <!-- Right: Voice Editor -->
        <div class="flex-1 border rounded-lg p-4 space-y-4 overflow-auto">
          <div v-if="!selectedName" class="flex items-center justify-center h-full text-sm text-muted-foreground">
            {{ $t('views.voices.selectToEdit') }}
          </div>

          <template v-else>
            <Transition name="fade" mode="out-in">
              <div v-if="metaLoading" key="meta-skeleton" class="p-4 space-y-4">
              <div class="flex items-center justify-between">
                <Skeleton class="h-5 w-24" />
                <Skeleton class="h-7 w-14" />
              </div>
              <div class="space-y-2">
                <Skeleton class="h-4 w-16" />
                <Skeleton class="h-9 w-full" />
              </div>
              <div class="space-y-2">
                <Skeleton class="h-4 w-16" />
                <Skeleton class="h-48 w-full rounded-lg" />
              </div>
              <div class="space-y-2">
                <Skeleton class="h-4 w-16" />
                <Skeleton class="h-14 w-full" />
              </div>
              <div class="flex gap-2">
                <Skeleton class="h-9 w-24 rounded-lg" />
                <Skeleton class="h-9 w-24 rounded-lg" />
              </div>
            </div>
            <div v-else-if="selectedMeta" key="editor" class="space-y-4">
              <div class="flex items-center justify-between">
                <h3 class="text-sm font-medium">{{ $t('views.voices.editVoice') }}</h3>
                <button
                  class="flex items-center gap-1 px-2 py-1 text-xs border rounded-lg text-destructive hover:bg-destructive/10 transition-colors"
                  @click="confirmDelete(selectedName)"
                >
                  <Trash2 class="w-3 h-3" /> {{ $t('views.voices.delete') }}
                </button>
              </div>

              <div class="space-y-2">
                <label class="label">{{ $t('views.voices.voiceName') }}</label>
                <input v-model="editName" type="text" class="w-full px-3 py-2 text-sm" />
              </div>

              <div class="space-y-2">
                <label class="label">{{ $t('views.voices.referenceAudio') }}</label>
                <AudioEditor
                  :audio-url="editAudioUrl"
                  :audio-name="editAudioName ?? undefined"
                  :loading="previewLoading"
                  :trim-start="0"
                  :trim-end="0"
                  @file="onEditAudio"
                />
                <p v-if="previewError" class="text-xs text-destructive">{{ previewError }}</p>
              </div>

              <div class="space-y-2">
                <label class="label">{{ $t('views.voices.referenceText') }}</label>
                <AutoTextarea v-model="editText" :rows="2" />
              </div>

              <AppCheckbox v-model="editXvec" :label="$t('views.voices.xVectorOnly')" />

              <div v-if="selectedMeta.model.length" class="text-xs text-muted-foreground">
                {{ $t('views.voices.applicableModels') }}{{ selectedMeta.model.join(', ') }}
              </div>

              <div class="flex gap-2 pt-2 flex-wrap items-center">
                <button
                  class="flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
                  :disabled="editing"
                  @click="saveEdit"
                >
                  <Save class="w-4 h-4" /> {{ editing ? $t('views.voices.saving') : $t('views.voices.saveEdit') }}
                </button>

                <button
                  class="flex items-center gap-1 px-3 py-2 rounded-lg text-sm border hover:bg-accent transition-colors"
                  @click="refreshInfo"
                >
                  <RefreshCw class="w-3.5 h-3.5" /> {{ $t('views.voices.refreshInfo') }}
                </button>

                <button
                  v-if="!baseModelLoaded"
                  class="flex items-center gap-1 px-3 py-2 rounded-lg text-sm border hover:bg-accent transition-colors"
                  @click="loadModelAndPreview"
                >
                  <Folder class="w-3.5 h-3.5" /> {{ $t('views.voices.loadModel') }}
                </button>
              </div>

              <p v-if="editError" class="text-xs text-destructive">{{ editError }}</p>
              <p v-if="editSuccess" class="text-xs text-green-600">{{ editSuccess }}</p>

              <!-- Error / hint area -->
              <p v-if="!baseModelLoaded" class="text-xs text-muted-foreground mt-1">
                {{ $t('views.voices.loadModelHint') }}
              </p>
            </div>

            <div v-else-if="metaError" key="meta-error" class="text-sm text-red-500">{{ metaError }}</div>
            </Transition>
          </template>
        </div>
      </div>
    </div>

    <ConfirmDialog
      :open="showDeleteConfirm"
      :title="$t('views.voices.deleteDialog.title')"
      :message="$t('views.voices.deleteDialog.message', { name: deleteTarget })"
      @confirm="doDelete"
      @cancel="showDeleteConfirm = false"
    />
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
