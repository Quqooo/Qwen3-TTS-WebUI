import { ref, computed, onBeforeUnmount } from "vue"
import AudioPlayer from "../../components/audio/AudioPlayer.vue"
import { synthesisApi, getBlobDuration, pcm16ToWav } from "../../api/synthesis"
import type { ModelKind, SynthesisRequest, GenerationParams as GenParams } from "../../types"
import { useUserConfig } from "../useUserConfig"
import { t } from "../../lang"

export interface SynthesisSessionOptions {
  kind: ModelKind
  buildRequestExtras: () => Partial<SynthesisRequest> | Promise<Partial<SynthesisRequest>>
}

export function useSynthesisSession({ kind, buildRequestExtras }: SynthesisSessionOptions) {
  const AudioPlayerRef = ref<InstanceType<typeof AudioPlayer> | null>(null)

  const text = ref("")
  const outputFormat = ref("wav")
  const sampleRate = ref("24000")
  const gain = ref(0)
  const emitEvery = ref(4)
  const decodeWindow = ref(80)
  const maxFrames = ref(10000)
  const splitMode = ref<"" | "split" | "stream">("")
  const streamingEnabled = computed(() => splitMode.value === "stream")
  const splitChars = ref(".。!！?？\\n")

  const isGenerating = ref(false)
  const genStartTime = ref(0)
  const genElapsed = ref(0)
  let genTimer: ReturnType<typeof setInterval> | 0 = 0
  const resultAudioUrl = ref<string | null>(null)
  const resultDuration = ref<number | undefined>(undefined)
  const genTime = ref<number | undefined>(undefined)
  const rtf = ref<number | undefined>(undefined)
  const statusMessage = ref("")

  const { defaultParams } = useUserConfig()
  const genParams = ref<GenParams>({ ...(defaultParams.value as any)[kind] })
  let generationController: AbortController | null = null
  let generationEpoch = 0
  const pcmBuffer = ref<Uint8Array[]>([])
  const synthesisText = ref("")

  const i18n = {
    generating: t(`views.${kindPath(kind)}.generating`),
    firstChunkArrived: t(`views.${kindPath(kind)}.firstChunkArrived`),
    generated: t(`views.${kindPath(kind)}.generated`),
    stopped: t(`views.${kindPath(kind)}.stopped`),
    failed: t(`views.${kindPath(kind)}.failed`),
  }

  async function generate(model: string, lang: string) {
    const epoch = ++generationEpoch
    const controller = new AbortController()
    generationController?.abort()
    generationController = controller
    isGenerating.value = true
    genStartTime.value = performance.now()
    genElapsed.value = 0
    genTime.value = undefined
    rtf.value = undefined
    AudioPlayerRef.value?.stopStream()
    resultAudioUrl.value = null
    resultDuration.value = undefined
    statusMessage.value = i18n.generating
    AudioPlayerRef.value?.resetVisual()
    genTimer = setInterval(() => {
      genElapsed.value = (performance.now() - genStartTime.value) / 1000
      if (streamingEnabled.value && pcmBuffer.value.length > 0) {
        const sr = parseInt(sampleRate.value)
        const totalBytes = pcmBuffer.value.reduce((s, c) => s + c.length, 0)
        const bufferedDur = totalBytes / 2 / sr
        if (bufferedDur > 0) {
          rtf.value = genElapsed.value / bufferedDur
        }
      }
    }, 50)
    pcmBuffer.value.length = 0
    try {
      const request: SynthesisRequest = {
        model: model,
        text: text.value,
        language: lang,
        kind,
        ...(await buildRequestExtras()),
        output_format: streamingEnabled.value ? "pcm" : outputFormat.value,
        output_sample_rate: parseInt(sampleRate.value),
        gain: gain.value,
        streaming: streamingEnabled.value,
        emit_every_frames: emitEvery.value,
        decode_window_frames: decodeWindow.value,
        overlap_samples: 0,
        max_frames: streamingEnabled.value ? maxFrames.value : undefined,
        split_enabled: splitMode.value === "split",
        split_characters: splitMode.value === "split" ? [splitChars.value] : undefined,
        generation_params: { ...genParams.value },
      }
      const blob = streamingEnabled.value
        ? await synthesisApi.synthesizePcmStream(
            request,
            (chunk) => {
              if (controller.signal.aborted || epoch !== generationEpoch) return
              pcmBuffer.value.push(chunk)
              if (pcmBuffer.value.length === 1) statusMessage.value = i18n.firstChunkArrived
              AudioPlayerRef.value?.appendChunk(chunk, parseInt(sampleRate.value))
            },
            controller.signal,
          )
        : await synthesisApi.synthesize(request, controller.signal)
      controller.signal.throwIfAborted()
      if (epoch !== generationEpoch) return
      clearInterval(genTimer)
      if (streamingEnabled.value) {
        AudioPlayerRef.value?.endStream()
        if (pcmBuffer.value.length > 0) {
          const sr = parseInt(sampleRate.value)
          const total = pcmBuffer.value.reduce((s, c) => s + c.length, 0)
          const merged = new Uint8Array(total)
          let off = 0
          for (const c of pcmBuffer.value) { merged.set(c, off); off += c.length }
          if (resultAudioUrl.value) URL.revokeObjectURL(resultAudioUrl.value)
          resultAudioUrl.value = URL.createObjectURL(pcm16ToWav(merged, sr))
          resultDuration.value = merged.length / 2 / sr
        }
      } else {
        const duration = await getBlobDuration(blob)
        controller.signal.throwIfAborted()
        if (epoch !== generationEpoch) return
        if (resultAudioUrl.value) URL.revokeObjectURL(resultAudioUrl.value)
        resultAudioUrl.value = URL.createObjectURL(blob)
        resultDuration.value = duration
      }
      genTime.value = (performance.now() - genStartTime.value) / 1000
      const finalDur = resultDuration.value ?? 0
      rtf.value = genTime.value / Math.max(finalDur, 0.01)
      isGenerating.value = false
      statusMessage.value = i18n.generated
      synthesisText.value = text.value
    } catch (e: any) {
      if (epoch !== generationEpoch) return
      clearInterval(genTimer)
      isGenerating.value = false
      statusMessage.value = e?.name === "AbortError" ? i18n.stopped : (e?.message ?? i18n.failed)
      if (e?.name === "AbortError") AudioPlayerRef.value?.stopStream()
    } finally {
      if (generationController === controller) generationController = null
    }
  }

  function stop() {
    generationEpoch++
    generationController?.abort()
    generationController = null
    clearInterval(genTimer)
    isGenerating.value = false
    statusMessage.value = i18n.stopped
    AudioPlayerRef.value?.stopStream()
  }

  onBeforeUnmount(() => { generationEpoch++; clearInterval(genTimer); generationController?.abort(); AudioPlayerRef.value?.stopStream() })

  return {
    AudioPlayerRef,
    text,
    outputFormat,
    sampleRate,
    gain,
    emitEvery,
    decodeWindow,
    maxFrames,
    splitMode,
    streamingEnabled,
    splitChars,
    isGenerating,
    genElapsed,
    resultAudioUrl,
    resultDuration,
    genTime,
    rtf,
    statusMessage,
    genParams,
    synthesisText,
    generate,
    stop,
  }
}

function kindPath(kind: ModelKind): string {
  if (kind === "custom_voice") return "customVoice"
  if (kind === "voice_design") return "voiceDesign"
  return "base"
}
