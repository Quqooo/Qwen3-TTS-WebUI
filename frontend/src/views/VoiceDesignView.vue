<script setup lang="ts">
import { ref } from "vue"
import AppSelect from "../components/common/AppSelect.vue"
import AutoTextarea from "../components/common/AutoTextarea.vue"
import GenerationParams from "../components/synthesis/GenerationParams.vue"
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
import { useModelStore } from "../stores/model"

const modelStore = useModelStore()

const { selectedModel, models, selectedLang, languageOptions } = useModelSelection({ kind: "voice_design" })
const voiceDescription = ref("")

const {
  bindAudioPlayer,
  text, outputFormat, sampleRate, gain, emitEvery, decodeWindow, overlapSamples, maxFrames, chunkSize,
  splitMode, streamingEnabled, splitChars, isGenerating, genElapsed,
  resultAudioUrl, resultDuration, genTime, rtf, statusMessage, genParams,
  synthesisText, generate, stop,
} = useSynthesisSession({
  kind: "voice_design",
  buildRequestExtras: () => ({ instruct: voiceDescription.value || undefined }),
})

const {
  showVoiceSaveDialog, voiceSaveName, voiceSaveText, voiceSaveModel,
  voiceSaveAudioUrl, voiceSaveTrimStart, voiceSaveTrimEnd,
  downloadAudio, onSaveVoice, doSaveVoice,
} = useVoiceResult(resultAudioUrl, synthesisText, resultDuration, streamingEnabled, outputFormat)
</script>

<template>
  <div class="h-full">
    <SynthesisWorkbench kind="voice_design">
    <template #left>
      <div class="card space-y-3">
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.voiceDesign.model') }}</label>
          <AppSelect v-model="selectedModel" :options="models" />
        </div>
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.voiceDesign.language') }}</label>
          <AppSelect v-model="selectedLang" :options="languageOptions" />
        </div>
      </div>

      <div class="card">
        <label class="label">{{ $t('views.voiceDesign.voiceDescription') }}</label>
        <AutoTextarea v-model="voiceDescription" :rows="5" :placeholder="$t('views.voiceDesign.voiceDescPlaceholder')" />
      </div>

      <GenerationParams v-model="genParams" />
    </template>

    <template #middle>
      <SynthesisTextInput i18n-prefix="views.voiceDesign" v-model="text" />
    </template>

    <template #right>
      <SynthesisOutputCard
        :ref="bindAudioPlayer"
        i18n-prefix="views.voiceDesign"
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
        v-model:overlap-samples="overlapSamples"
        v-model:max-frames="maxFrames"
        v-model:chunk-size="chunkSize"
        :faster-branch="modelStore.isFasterBranch"
      />

      <SynthesisOutputControls
        i18n-prefix="views.voiceDesign"
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
  </div>
</template>
