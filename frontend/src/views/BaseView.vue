<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { Upload, Save } from "@lucide/vue"
import AppSelect from "../components/common/AppSelect.vue"
import AutoTextarea from "../components/common/AutoTextarea.vue"
import AppCheckbox from "../components/common/AppCheckbox.vue"
import AudioEditor from "../components/audio/AudioEditor.vue"
import GenerationParams from "../components/synthesis/GenerationParams.vue"
import SegmentPanel from "../components/synthesis/SegmentPanel.vue"
import SplitStreamPanel from "../components/synthesis/SplitStreamPanel.vue"
import SynthesisOutputCard from "../components/synthesis/SynthesisOutputCard.vue"
import SynthesisOutputControls from "../components/synthesis/SynthesisOutputControls.vue"
import SynthesisTextInput from "../components/synthesis/SynthesisTextInput.vue"
import SynthesisWorkbench from "../components/synthesis/SynthesisWorkbench.vue"
import StatusOutput from "../components/common/StatusOutput.vue"
import VoiceSaveDialog from "../components/common/VoiceSaveDialog.vue"
import { useModelSelection } from "../composables/synthesis/useModelSelection"
import { useSynthesisSession } from "../composables/synthesis/useSynthesisSession"
import { useVoiceResult } from "../composables/synthesis/useVoiceResult"
import { voicesApi } from "../api/voices"
import { t } from "../lang"

const { selectedModel, models, selectedLang, languageOptions } = useModelSelection({ kind: "base" })

const sourceMode = ref<"upload" | "voice">("upload")
const sourceSegments = computed(() => [
  { value: "upload" as const, label: t('views.base.segmentUpload'), icon: Upload },
  { value: "voice" as const, label: t('views.base.segmentVoice'), icon: Save },
])

const refAudioUrl = ref<string | null>(null)
const refAudioName = ref<string | null>(null)
const refTrimStart = ref(0)
const refTrimEnd = ref(0)
const refText = ref("")
const xvecOnly = ref(false)
const voiceFiles = ref<{ value: string; label: string }[]>([])
const selectedVoice = ref("")

function onRefAudio(file: File | null) {
  if (file) {
    refAudioUrl.value = URL.createObjectURL(file)
    refAudioName.value = file.name
  } else {
    if (refAudioUrl.value) URL.revokeObjectURL(refAudioUrl.value)
    refAudioUrl.value = null
    refAudioName.value = null
  }
}

const {
  text, outputFormat, sampleRate, gain, emitEvery, decodeWindow, maxFrames,
  splitMode, streamingEnabled, splitChars, isGenerating, genElapsed,
  resultAudioUrl, resultDuration, genTime, rtf, statusMessage, genParams,
  synthesisText, generate, stop,
} = useSynthesisSession({
  kind: "base",
  buildRequestExtras: async () => {
    let refAudioDataUrl: string | undefined
    let refTextValue: string | undefined
    let voiceFileValue: string | undefined

    if (sourceMode.value === "upload") {
      if (refAudioUrl.value) {
        const resp = await fetch(refAudioUrl.value)
        const blob = await resp.blob()
        refAudioDataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result as string)
          reader.onerror = reject
          reader.readAsDataURL(blob)
        })
      }
      refTextValue = xvecOnly.value ? undefined : (refText.value || undefined)
    } else {
      voiceFileValue = selectedVoice.value || undefined
    }

    return {
      ...(sourceMode.value === "upload"
        ? { ref_audio: refAudioDataUrl, ref_text: refTextValue }
        : { voice_file: voiceFileValue }),
      x_vector_only: sourceMode.value === "upload" ? (xvecOnly.value || undefined) : undefined,
    }
  },
})

const {
  showVoiceSaveDialog, voiceSaveName, voiceSaveText, voiceSaveModel,
  voiceSaveAudioUrl, voiceSaveTrimStart, voiceSaveTrimEnd,
  downloadAudio, onSaveVoice, doSaveVoice,
} = useVoiceResult(resultAudioUrl, synthesisText, resultDuration, streamingEnabled, outputFormat, voiceFiles)

onMounted(async () => {
  try {
    const res = await voicesApi.list()
    voiceFiles.value = res.voices.map((v: string) => ({ value: v, label: v }))
  } catch {
    // keep defaults
  }
})
</script>

<template>
  <SynthesisWorkbench kind="base">
    <template #left>
      <div class="card space-y-3">
        <div class="space-y-1.5">
          <label class="label">{{ $t('common.model') }}</label>
          <AppSelect v-model="selectedModel" :options="models" />
        </div>
        <div class="space-y-1.5">
          <label class="label">{{ $t('common.language') }}</label>
          <AppSelect v-model="selectedLang" :options="languageOptions" />
        </div>
      </div>

      <SegmentPanel
        v-model="sourceMode"
        :title="$t('views.base.cloneSource')"
        :segments="sourceSegments"
        :can-deselect="false"
      >
        <template #upload>
          <AudioEditor
            :audio-url="refAudioUrl"
            :audio-name="refAudioName ?? undefined"
            :trim-start="refTrimStart"
            :trim-end="refTrimEnd"
            @file="onRefAudio"
            @update:trim-start="refTrimStart = $event"
            @update:trim-end="refTrimEnd = $event"
          />
          <Transition
            enter-active-class="transition-all duration-200 ease-out"
            enter-from-class="opacity-0 -translate-y-2"
            enter-to-class="opacity-100 translate-y-0"
          >
            <div v-if="refAudioUrl || xvecOnly" class="space-y-2">
              <label class="label">{{ $t('views.base.referenceText') }}</label>
              <AutoTextarea v-model="refText" :rows="2" :placeholder="$t('common.refTextPlaceholder')" />
              <AppCheckbox v-model="xvecOnly" :label="$t('common.xVectorOnly')" />
            </div>
          </Transition>
        </template>
        <template #voice>
          <AppSelect
            v-model="selectedVoice"
            :options="voiceFiles"
            :placeholder="$t('views.base.voiceNamePlaceholder')"
            filterable
          />
        </template>
      </SegmentPanel>

      <GenerationParams v-model="genParams" />
    </template>

    <template #middle>
      <SynthesisTextInput i18n-prefix="views.base" v-model="text" />
    </template>

    <template #right>
      <SynthesisOutputCard
        i18n-prefix="views.base"
        :result-audio-url="resultAudioUrl"
        :result-duration="resultDuration"
        :streaming-enabled="streamingEnabled"
        :is-generating="isGenerating"
        :gen-elapsed="genElapsed"
        :gen-time="genTime"
        :rtf="rtf"
        @download="downloadAudio"
        @save-voice="onSaveVoice"
      />

      <SplitStreamPanel
        v-model="splitMode"
        v-model:split-chars="splitChars"
        v-model:emit-every="emitEvery"
        v-model:decode-window="decodeWindow"
        v-model:max-frames="maxFrames"
      />

      <SynthesisOutputControls
        i18n-prefix="views.base"
        :is-generating="isGenerating"
        :streaming-enabled="streamingEnabled"
        :output-format="outputFormat"
        :sample-rate="sampleRate"
        :gain="gain"
        @update:output-format="outputFormat = $event"
        @update:sample-rate="sampleRate = $event"
        @update:gain="gain = $event"
        @generate="generate(selectedModel, selectedLang)"
        @stop="stop()"
      />

      <StatusOutput :message="statusMessage" />
    </template>
  </SynthesisWorkbench>

  <VoiceSaveDialog
    :open="showVoiceSaveDialog"
    :name="voiceSaveName"
    :model="voiceSaveModel"
    :audio-url="resultAudioUrl"
    :text="voiceSaveText"
    @update:name="voiceSaveName = $event"
    @update:model="voiceSaveModel = $event"
    @update:text="voiceSaveText = $event"
    @update:audio-url="voiceSaveAudioUrl = $event"
    @update:trim-start="voiceSaveTrimStart = $event"
    @update:trim-end="voiceSaveTrimEnd = $event"
    @confirm="doSaveVoice(voiceSaveName, voiceSaveModel)"
    @cancel="showVoiceSaveDialog = false"
  />
</template>
