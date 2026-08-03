import type { BatchRow } from "./useBatchTypes"
import type { SynthesisRequest } from "../types"
import { useModelStore } from "../stores/model"

async function blobUrlToDataUrl(url: string): Promise<string> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to read reference audio: HTTP ${response.status}`)
  }
  const blob = await response.blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read reference audio"))
    reader.readAsDataURL(blob)
  })
}

export function useBatchRequestBuilder() {
  const modelStore = useModelStore()

  async function buildRequest(row: BatchRow): Promise<SynthesisRequest> {
    const request: SynthesisRequest = {
      model: row.model,
      text: row.text,
      language: row.language,
      kind: row.modelKind,
      output: {
        format: "wav",
        sample_rate: 24000,
        gain: 0,
      },
      streaming: false,
      ...(row.generationParams.enabled ? {
        generation_params: Object.fromEntries(
          Object.entries(row.generationParams).filter(([key, value]) => key !== "enabled" && value !== undefined),
        ),
      } : {}),
    }

    if (row.modelKind === "base") {
      request.instruct = modelStore.isFasterBranch ? (row.instruct?.trim() || undefined) : undefined
      if (row.cloneSource === "voice_file") {
        request.voice_file = row.voiceFile
      } else if (row.cloneSource === "upload" && row.refAudioUrl) {
        request.ref_audio = await blobUrlToDataUrl(row.refAudioUrl)
        request.ref_text = row.refText || undefined
        request.x_vector_only = row.xvecOnly || undefined
      }
    } else if (row.modelKind === "custom_voice") {
      request.speaker = row.speaker
      request.instruct = row.instruct || undefined
    } else {
      request.voice_description = row.voiceDescription || undefined
    }

    return request
  }

  return { buildRequest }
}
