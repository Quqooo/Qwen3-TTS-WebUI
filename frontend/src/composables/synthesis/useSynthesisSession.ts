import { ref, computed, onBeforeUnmount } from "vue"
import { synthesisApi, getBlobDuration, pcm16ToWav } from "../../api/synthesis"
import type { ModelKind, SynthesisRequest, GenerationParamsConfig as GenParams } from "../../types"
import { useUserConfig } from "../useUserConfig"
import { useModelStore } from "../../stores/model"
import { t } from "../../lang"

export interface SynthesisSessionOptions {
  kind: ModelKind
  buildRequestExtras: () => Partial<SynthesisRequest> | Promise<Partial<SynthesisRequest>>
}

export function useSynthesisSession({ kind, buildRequestExtras }: SynthesisSessionOptions) {
  const audioPlayerRef = ref<{ appendChunk: (chunk: Uint8Array, sampleRate: number) => void; endStream: () => void; stopStream: () => void; resetVisual: () => void } | null>(null)
  const bindAudioPlayer = (instance: unknown) => {
    audioPlayerRef.value = instance as typeof audioPlayerRef.value
  }

  const text = ref("")
  const outputFormat = ref("wav")
  const sampleRate = ref("24000")
  const gain = ref(0)
  const emitEvery = ref<number | undefined>(8)
  const decodeWindow = ref<number | undefined>(80)
  const overlapSamples = ref<number | undefined>(0)
  const maxFrames = ref<number | undefined>(10000)
  const chunkSize = ref<number | undefined>(12)
  const parityMode = ref(false)
  const splitMode = ref<"" | "split" | "stream">("")
  const streamingEnabled = computed(() => splitMode.value === "stream")
  const splitChars = ref(".。!！?？\\n")

  const modelStore = useModelStore()

  const isGenerating = ref(false)
  const genStartTime = ref(0)
  const genElapsed = ref(0)
  let genTimer: ReturnType<typeof setInterval> | 0 = 0
  const resultAudioUrl = ref<string | null>(null)
  const resultDuration = ref<number | undefined>(undefined)

  function clearResultAudioUrl() {
    const previous = resultAudioUrl.value
    resultAudioUrl.value = null
    if (previous?.startsWith("blob:")) URL.revokeObjectURL(previous)
  }

  function replaceResultAudioUrl(blob: Blob) {
    const previous = resultAudioUrl.value
    resultAudioUrl.value = URL.createObjectURL(blob)
    if (previous?.startsWith("blob:")) URL.revokeObjectURL(previous)
  }
  const genTime = ref<number | undefined>(undefined)
  const rtf = ref<number | undefined>(undefined)
  const statusKind = ref<"generating" | "firstChunkArrived" | "generated" | "stopped" | "failed" | "">("")
  const statusError = ref("")
  // 状态文本按语言动态翻译；后端返回的原始错误信息原样显示
  const statusMessage = computed(() => {
    if (statusError.value) return statusError.value
    if (!statusKind.value) return ""
    return t(`views.${kindPath(kind)}.${statusKind.value}`)
  })

  const { defaultParams } = useUserConfig()
  const genParams = ref<GenParams>({ ...(defaultParams.value as any)[kind] })
  let generationController: AbortController | null = null
  let generationEpoch = 0
  const pcmBuffer = ref<Uint8Array[]>([])
  const synthesisText = ref("")

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
    audioPlayerRef.value?.stopStream()
    clearResultAudioUrl()
    resultDuration.value = undefined
    statusKind.value = "generating"
    statusError.value = ""
    audioPlayerRef.value?.resetVisual()
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
        output: {
          format: streamingEnabled.value ? "pcm" : outputFormat.value,
          sample_rate: parseInt(sampleRate.value),
          gain: gain.value,
        },
        streaming: streamingEnabled.value,
        ...(splitMode.value === "split" ? { split_string: [splitChars.value] } : {}),
        ...(genParams.value.enabled ? {
          generation_params: Object.fromEntries(
            Object.entries(genParams.value).filter(([key, value]) => key !== "enabled" && key !== "parity_mode" && value !== undefined),
          ),
        } : {}),
        ...(streamingEnabled.value && !modelStore.isFasterBranch ? {
          dffdeeq: Object.fromEntries(
            Object.entries({
              emit_every_frames: emitEvery.value,
              decode_window_frames: decodeWindow.value,
              overlap_samples: overlapSamples.value,
              max_frames: maxFrames.value,
            }).filter(([, value]) => value !== undefined),
          ),
        } : {}),
        ...(streamingEnabled.value && modelStore.isFasterBranch ? {
          andimarafioti: {
            ...(chunkSize.value !== undefined ? { chunk_size: chunkSize.value } : {}),
            ...(kind === "base" ? { parity_mode: parityMode.value } : {}),
          },
        } : {}),
      }
      const blob = streamingEnabled.value
        ? await synthesisApi.synthesizePcmStream(
            request,
            (chunk) => {
              if (controller.signal.aborted || epoch !== generationEpoch) return
              pcmBuffer.value.push(chunk)
              if (pcmBuffer.value.length === 1) statusKind.value = "firstChunkArrived"
              audioPlayerRef.value?.appendChunk(chunk, parseInt(sampleRate.value))
            },
            controller.signal,
          )
        : await synthesisApi.synthesize(request, controller.signal)
      controller.signal.throwIfAborted()
      if (epoch !== generationEpoch) return
      clearInterval(genTimer)
      if (streamingEnabled.value) {
        audioPlayerRef.value?.endStream()
        if (pcmBuffer.value.length > 0) {
          const sr = parseInt(sampleRate.value)
          const total = pcmBuffer.value.reduce((s, c) => s + c.length, 0)
          const merged = new Uint8Array(total)
          let off = 0
          for (const c of pcmBuffer.value) { merged.set(c, off); off += c.length }
          replaceResultAudioUrl(pcm16ToWav(merged, sr))
          resultDuration.value = merged.length / 2 / sr
        }
      } else {
        const duration = await getBlobDuration(blob)
        controller.signal.throwIfAborted()
        if (epoch !== generationEpoch) return
        replaceResultAudioUrl(blob)
        resultDuration.value = duration
      }
      genTime.value = (performance.now() - genStartTime.value) / 1000
      const finalDur = resultDuration.value ?? 0
      rtf.value = genTime.value / Math.max(finalDur, 0.01)
      isGenerating.value = false
      statusKind.value = "generated"
      statusError.value = ""
      synthesisText.value = text.value
    } catch (e: any) {
      if (epoch !== generationEpoch) return
      clearInterval(genTimer)
      isGenerating.value = false
      if (e?.name === "AbortError") {
        statusKind.value = "stopped"
        statusError.value = ""
      } else if (e?.message) {
        statusKind.value = ""
        statusError.value = e.message
      } else {
        statusKind.value = "failed"
        statusError.value = ""
      }
      if (e?.name === "AbortError") audioPlayerRef.value?.stopStream()
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
    statusKind.value = "stopped"
    statusError.value = ""
    audioPlayerRef.value?.stopStream()
  }

  onBeforeUnmount(() => {
    generationEpoch++
    clearInterval(genTimer)
    generationController?.abort()
    audioPlayerRef.value?.stopStream()
    clearResultAudioUrl()
  })

  return {
    bindAudioPlayer,
    text,
    outputFormat,
    sampleRate,
    gain,
    emitEvery,
    decodeWindow,
    overlapSamples,
    maxFrames,
    chunkSize,
    parityMode,
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
