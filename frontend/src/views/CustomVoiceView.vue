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

const { selectedModel, models, selectedLang, speakerOptions, languageOptions, selectedSpeaker } = useModelSelection({ kind: "custom_voice" })
const instruct = ref("")

const {
  text, outputFormat, sampleRate, gain, emitEvery, decodeWindow, maxFrames,
  splitMode, streamingEnabled, splitChars, isGenerating, genElapsed,
  resultAudioUrl, resultDuration, genTime, rtf, statusMessage, genParams,
  synthesisText, generate, stop,
} = useSynthesisSession({
  kind: "custom_voice",
  buildRequestExtras: () => ({ speaker: selectedSpeaker.value, instruct: instruct.value || undefined }),
})

const {
  showVoiceSaveDialog, voiceSaveName, voiceSaveText, voiceSaveModel,
  voiceSaveAudioUrl, voiceSaveTrimStart, voiceSaveTrimEnd,
  downloadAudio, onSaveVoice, doSaveVoice,
} = useVoiceResult(resultAudioUrl, synthesisText, resultDuration, streamingEnabled, outputFormat)
</script>

<template>
  <SynthesisWorkbench kind="custom_voice">
    <template #left>
      <div class="card space-y-3">
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.customVoice.model') }}</label>
          <AppSelect v-model="selectedModel" :options="models" />
        </div>
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.customVoice.language') }}</label>
          <AppSelect v-model="selectedLang" :options="languageOptions" />
        </div>
      </div>

      <div class="card space-y-3">
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.customVoice.speaker') }}</label>
          <AppSelect v-model="selectedSpeaker" :options="speakerOptions" />
        </div>
        <div class="space-y-1.5">
          <label class="label">{{ $t('views.customVoice.instruct') }}</label>
          <AutoTextarea v-model="instruct" :rows="3" :placeholder="$t('views.customVoice.instructPlaceholder')" />
        </div>
      </div>

      <GenerationParams v-model="genParams" />
    </template>

    <template #middle>
      <SynthesisTextInput i18n-prefix="views.customVoice" v-model="text" />
    </template>

    <template #right>
      <SynthesisOutputCard
        i18n-prefix="views.customVoice"
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
        i18n-prefix="views.customVoice"
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
