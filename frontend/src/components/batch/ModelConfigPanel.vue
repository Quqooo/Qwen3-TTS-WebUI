<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue"
import { MicVocal, Speech, Palette, Upload, Clock, Save } from "@lucide/vue"
import AppSelect from "../common/AppSelect.vue"
import AutoTextarea from "../common/AutoTextarea.vue"
import SegmentPanel from "../synthesis/SegmentPanel.vue"
import GenerationParams from "../synthesis/GenerationParams.vue"
import AudioCard from "../audio/AudioCard.vue"
import TimeInput from "../common/TimeInput.vue"
import type { ModelKind, GenerationParamsConfig as GenParams } from "../../types"
import { useModelStore } from "../../stores/model"
import { useVoiceStore } from "../../stores/voice"
import { modelsApi } from "../../api/models"
import { t } from "../../lang"
import { buildSpeakerOptions, buildLanguageOptions, type OptionItem } from "../../constants/options"

export interface ModelConfig {
  text: string
  modelKind: ModelKind
  model: string
  speaker: string
  instruct: string
  voiceDescription: string
  voiceFile: string
  refText: string
  xVectorOnly: boolean
  cloneSource: "upload" | "voice_file"
  refAudioUrl: string
  refAudioName: string
  timelineEnabled: boolean
  timelineStart: number
  timelineEnd: number
  language: string
  generationParams: GenParams
}

const props = defineProps<{
  modelValue: ModelConfig
  disabled?: boolean
  hideText?: boolean
  hideTimeOffset?: boolean
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: ModelConfig): void
}>()

const modelStore = useModelStore()
const voiceStore = useVoiceStore()

let _mounted = false

onMounted(() => {
  _mounted = true
  modelStore.fetchModels()
  voiceStore.fetchVoices()
})

function patch(partial: Partial<ModelConfig>) {
  if (props.disabled) return
  emit("update:modelValue", { ...props.modelValue, ...partial })
}

const kindOptions = computed((): { value: ModelKind; label: string; icon: any }[] => [
  { value: "base", label: t('components.modelConfigPanel.base'), icon: MicVocal },
  { value: "custom_voice", label: t('components.modelConfigPanel.customVoice'), icon: Speech },
  { value: "voice_design", label: t('components.modelConfigPanel.voiceDesign'), icon: Palette },
])

const cloneSourceOptions = computed(() => [
  { value: "upload" as const, label: t('components.modelConfigPanel.uploadAudio'), icon: Upload },
  { value: "voice_file" as const, label: t('components.modelConfigPanel.existingVoice'), icon: Save },
])

const speakerOptions = ref<OptionItem[]>([])
const languageOptions = ref<OptionItem[]>([])

let metaRequestId = 0

interface MetaCacheEntry {
  speakers: OptionItem[]
  languages: OptionItem[]
  syncing: boolean
}

const _metaCache = new Map<string, MetaCacheEntry>()

async function fetchModelMeta(modelId: string) {
  const requestId = ++metaRequestId
  if (!modelId) {
    speakerOptions.value = []
    languageOptions.value = []
    return
  }

  const cached = _metaCache.get(modelId)
  if (cached) {
    speakerOptions.value = cached.speakers
    languageOptions.value = cached.languages
    applyMetaFallback(cached.speakers, cached.languages)
    if (cached.syncing) return
    cached.syncing = true
  }

  try {
    const meta = await modelsApi.getMeta(modelId)
    if (requestId !== metaRequestId) return
    const speakers = buildSpeakerOptions(meta.speakers)
    const languages = buildLanguageOptions(meta.languages)
    _metaCache.set(modelId, { speakers, languages, syncing: false })
    speakerOptions.value = speakers
    languageOptions.value = languages
    applyMetaFallback(speakers, languages)
  } catch {
    if (cached) cached.syncing = false
  }
}

function normalizeSpeaker(s: string) { return s.toLowerCase().replace(/[ _]/g, '_') }

function applyMetaFallback(speakers: OptionItem[], languages: OptionItem[]) {
  if (!_mounted) return
  const next: Partial<ModelConfig> = {}
  const currentSpeaker = props.modelValue.speaker
  if (speakers.length) {
    const match = speakers.find(o => normalizeSpeaker(o.value) === normalizeSpeaker(currentSpeaker))
    if (match) {
      if (match.value !== currentSpeaker) next.speaker = match.value
    } else {
      next.speaker = speakers[0].value
    }
  }
  if (languages.length && !languages.some(o => o.value === props.modelValue.language)) {
    const auto = languages.find(o => o.value.toLowerCase() === "auto")
    next.language = auto?.value ?? languages[0].value
  }
  if (Object.keys(next).length) patch(next)
}

watch(() => props.modelValue.model, fetchModelMeta, { immediate: true })

const audioInputRef = ref<HTMLInputElement | null>(null)
let uploadDragCounter = 0
const isDragOver = ref(false)

const modelOptionsByKind = computed(() => {
  const all = modelStore.availableModels
  return {
    base: all.filter((m) => m.kind === "base").map((m) => ({ value: m.id, label: m.id })),
    custom_voice: all.filter((m) => m.kind === "custom_voice").map((m) => ({ value: m.id, label: m.id })),
    voice_design: all.filter((m) => m.kind === "voice_design").map((m) => ({ value: m.id, label: m.id })),
  }
})

const currentModels = computed(() => modelOptionsByKind.value[props.modelValue.modelKind])

const voiceFileOptions = computed(() =>
  voiceStore.voices.map((v) => ({ value: v.name, label: v.name }))
)

watch(currentModels, (options) => {
  if (!_mounted) return
  if (!options.length) return
  const exists = options.some(o => o.value === props.modelValue.model)
  if (!exists) patch({ model: options[0].value })
})

watch(voiceFileOptions, (options) => {
  if (!_mounted) return
  if (!options.length) return
  const exists = options.some(o => o.value === props.modelValue.voiceFile)
  if (!exists) patch({ voiceFile: options[0].value })
})

const xvecAutoOn = computed(() =>
  !(props.modelValue.cloneSource === "upload" && !!props.modelValue.refAudioUrl && props.modelValue.refText.trim().length > 0)
)

function onKindChange(kind: ModelKind) {
  const models = modelOptionsByKind.value[kind]
  const model = models.length > 0 ? models[0].value : ""
  patch({ modelKind: kind, model })
}

watch(() => [props.modelValue.refAudioUrl, props.modelValue.refText], () => {
  const on = props.modelValue.cloneSource === "upload" && !!props.modelValue.refAudioUrl && props.modelValue.refText.trim().length > 0
  if (props.modelValue.xVectorOnly !== !on) patch({ xVectorOnly: !on })
})

function handleAudioFile(file: File) {
  if (!file.type.startsWith("audio/")) return
  const previousUrl = props.modelValue.refAudioUrl
  const url = URL.createObjectURL(file)
  patch({ refAudioUrl: url, refAudioName: file.name })
  if (previousUrl?.startsWith("blob:")) URL.revokeObjectURL(previousUrl)
}

function removeAudio() {
  if (props.modelValue.refAudioUrl) URL.revokeObjectURL(props.modelValue.refAudioUrl)
  patch({ refAudioUrl: "", refAudioName: "", xVectorOnly: false })
}

function onUploadDragOver(ev: DragEvent) { ev.preventDefault() }
function onUploadDragEnter() { uploadDragCounter++; isDragOver.value = true }
function onUploadDragLeave() { uploadDragCounter--; if (uploadDragCounter <= 0) { uploadDragCounter = 0; isDragOver.value = false } }
function onUploadDrop(ev: DragEvent) {
  ev.preventDefault()
  uploadDragCounter = 0
  isDragOver.value = false
  const file = ev.dataTransfer?.files[0]
  if (file) handleAudioFile(file)
}
function onUploadInput(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  if (file) handleAudioFile(file);
  (ev.target as HTMLInputElement).value = ""
}
</script>

<template>
  <div class="space-y-3" :class="disabled ? 'pointer-events-none opacity-60' : ''">
    <template v-if="!hideText">
      <div class="space-y-1.5">
        <label class="label">{{ $t('components.modelConfigPanel.synthesisText') }}</label>
        <textarea
          :value="modelValue.text"
          class="w-full px-3 py-2 text-sm resize-none"
          rows="3"
          :placeholder="$t('components.modelConfigPanel.textPlaceholder')"
          @input="patch({ text: ($event.target as HTMLTextAreaElement).value })"
        />
      </div>
    </template>

    <SegmentPanel
      :model-value="modelValue.modelKind"
      @update:model-value="onKindChange($event as ModelKind)"
      :segments="kindOptions"
      :animate-height="false"
    >
      <template #base>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.model') }}</label>
          <AppSelect
            :model-value="modelValue.model"
            :options="currentModels"
            @update:model-value="patch({ model: $event })"
          />
        </div>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.language') }}</label>
          <AppSelect
            :model-value="modelValue.language"
            :options="languageOptions"
            @update:model-value="patch({ language: $event })"
          />
        </div>

        <SegmentPanel
          nested
          :model-value="modelValue.cloneSource"
          @update:model-value="patch({ cloneSource: $event as 'upload' | 'voice_file' })"
          :segments="cloneSourceOptions"
          :can-deselect="false"
        >
          <template #upload>
            <div
              v-if="!modelValue.refAudioUrl"
              class="border-2 border-dashed rounded-lg py-4 text-center cursor-pointer transition-colors hover:border-primary/50"
              :class="isDragOver ? 'border-primary bg-primary/5' : 'border-border'"
              @drop.prevent="onUploadDrop"
              @dragover.prevent="onUploadDragOver"
              @dragenter="onUploadDragEnter"
              @dragleave="onUploadDragLeave"
              @click="audioInputRef?.click()"
            >
              <input ref="audioInputRef" type="file" accept="audio/*" class="hidden" @input="onUploadInput" />
              <Upload class="w-5 h-5 text-muted-foreground mx-auto mb-1" />
              <p class="text-xs text-muted-foreground">{{ $t('components.modelConfigPanel.dropHint') }}</p>
            </div>
            <template v-else>
              <AudioCard
                :audio-url="modelValue.refAudioUrl"
                :audio-name="modelValue.refAudioName"
                @file="(f) => f ? handleAudioFile(f) : removeAudio()"
              />
              <div class="space-y-1.5">
                <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.refText') }}</label>
                <AutoTextarea
                  :model-value="modelValue.refText"
                  :rows="2"
                  :placeholder="$t('components.modelConfigPanel.refTextPlaceholder')"
                  @update:model-value="patch({ refText: $event })"
                />
              </div>
              <label class="inline-flex items-center gap-2 cursor-default select-none text-xs">
                <span class="w-4 h-4 rounded border-2 flex items-center justify-center transition-all duration-150"
                  :class="xvecAutoOn ? 'bg-primary border-primary' : 'border-muted-foreground/30'">
                  <svg class="w-3 h-3 text-primary-foreground transition-opacity duration-150" :class="xvecAutoOn ? 'opacity-100' : 'opacity-0'" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
                <span class="text-muted-foreground">{{ $t('components.modelConfigPanel.xVectorOnly') }}</span>
              </label>
            </template>
            <div v-if="modelStore.isFasterBranch" class="space-y-1.5">
              <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.instruct') }}</label>
              <AutoTextarea
                :model-value="modelValue.instruct"
                :rows="2"
                :placeholder="$t('components.modelConfigPanel.instructPlaceholder')"
                @update:model-value="patch({ instruct: $event })"
              />
            </div>
          </template>
          <template #voice_file>
            <div class="space-y-1.5">
              <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.existingVoiceLabel') }}</label>
              <AppSelect
                :model-value="modelValue.voiceFile"
                :options="voiceFileOptions"
                :placeholder="$t('components.modelConfigPanel.existingVoicePlaceholder')"
                filterable
                @update:model-value="patch({ voiceFile: $event })"
              />
            </div>
            <div v-if="modelStore.isFasterBranch" class="space-y-1.5">
              <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.instruct') }}</label>
              <AutoTextarea
                :model-value="modelValue.instruct"
                :rows="2"
                :placeholder="$t('components.modelConfigPanel.instructPlaceholder')"
                @update:model-value="patch({ instruct: $event })"
              />
            </div>
          </template>
        </SegmentPanel>
      </template>

      <template #custom_voice>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.model') }}</label>
          <AppSelect
            :model-value="modelValue.model"
            :options="currentModels"
            @update:model-value="patch({ model: $event })"
          />
        </div>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.language') }}</label>
          <AppSelect
            :model-value="modelValue.language"
            :options="languageOptions"
            @update:model-value="patch({ language: $event })"
          />
        </div>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.speaker') }}</label>
          <AppSelect
            :model-value="modelValue.speaker"
            :options="speakerOptions"
            @update:model-value="patch({ speaker: $event })"
          />
        </div>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.instruct') }}</label>
          <AutoTextarea
            :model-value="modelValue.instruct"
            :rows="2"
            :placeholder="$t('components.modelConfigPanel.instructPlaceholder')"
            @update:model-value="patch({ instruct: $event })"
          />
        </div>
      </template>

      <template #voice_design>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.model') }}</label>
          <AppSelect
            :model-value="modelValue.model"
            :options="currentModels"
            @update:model-value="patch({ model: $event })"
          />
        </div>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.language') }}</label>
          <AppSelect
            :model-value="modelValue.language"
            :options="languageOptions"
            @update:model-value="patch({ language: $event })"
          />
        </div>
        <div class="space-y-1.5">
          <label class="text-[10px] text-muted-foreground">{{ $t('components.modelConfigPanel.voiceDescription') }}</label>
          <AutoTextarea
            :model-value="modelValue.voiceDescription"
            :rows="3"
            :placeholder="$t('components.modelConfigPanel.voiceDescPlaceholder')"
            @update:model-value="patch({ voiceDescription: $event })"
          />
        </div>
      </template>
    </SegmentPanel>

    <template v-if="!hideTimeOffset">
      <SegmentPanel
        :model-value="modelValue.timelineEnabled ? 'on' : ''"
        @update:model-value="patch({ timelineEnabled: $event === 'on' })"
        :segments="[{ value: 'on', label: t('components.modelConfigPanel.timeline'), icon: Clock }]"
        :animate-height="false"
        can-deselect
      >
        <template #on>
          <div class="grid items-center" style="grid-template-columns: 2fr 1fr 2fr;">
            <div class="flex justify-center">
              <TimeInput
                :model-value="modelValue.timelineStart"
                @update:model-value="patch({ timelineStart: $event })"
              />
            </div>
            <span class="text-center text-muted-foreground select-none">→</span>
            <div class="flex justify-center">
              <TimeInput
                :model-value="modelValue.timelineEnd"
                @update:model-value="patch({ timelineEnd: $event })"
              />
            </div>
          </div>
          <p class="text-center text-[10px] text-muted-foreground/60 leading-tight">{{ $t('components.modelConfigPanel.timelineNote') }}</p>
        </template>
      </SegmentPanel>
    </template>

    <GenerationParams
      :model-value="modelValue.generationParams"
      :disabled="disabled"
      @update:model-value="patch({ generationParams: $event })"
    />
  </div>
</template>
