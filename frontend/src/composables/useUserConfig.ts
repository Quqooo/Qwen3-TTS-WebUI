import { useStorage } from "@vueuse/core"
import type { ModelKind, GenerationParams } from "../types"

const DEFAULT_PARAMS: GenerationParams = {
  temperature: 0.9,
  top_k: 50,
  top_p: 1.0,
  repetition_penalty: 1.05,
  max_new_tokens: 8192,
  subtalker_top_k: 50,
  subtalker_top_p: 1.0,
  subtalker_temperature: 0.9,
}

const DEFAULT_PARAMS_BY_KIND: Record<ModelKind, GenerationParams> = {
  base: { ...DEFAULT_PARAMS },
  custom_voice: { ...DEFAULT_PARAMS },
  voice_design: { ...DEFAULT_PARAMS },
}

function sanitizeParams(v: unknown): Record<ModelKind, GenerationParams> {
  if (!v || typeof v !== "object") return { ...DEFAULT_PARAMS_BY_KIND }
  const raw = v as Record<string, Record<string, number>>
  const result = { ...DEFAULT_PARAMS_BY_KIND }
  for (const kind of ["base", "custom_voice", "voice_design"] as ModelKind[]) {
    if (raw[kind] && typeof raw[kind] === "object") {
      result[kind] = { ...DEFAULT_PARAMS, ...raw[kind] }
    }
  }
  return result
}

export function useUserConfig() {
  const defaultParams = useStorage<Record<ModelKind, GenerationParams>>(
    "qwen-tts:user-config:default-params",
    { ...DEFAULT_PARAMS_BY_KIND },
    localStorage,
    { serializer: { read: sanitizeParams, write: (v) => JSON.stringify(v) } },
  )

  const globalVolume = useStorage<number>(
    "qwen-tts:user-config:global-volume",
    100,
    localStorage,
    { serializer: { read: (v) => { const n = Number(v); return Number.isNaN(n) ? 100 : Math.max(0, Math.min(100, n)) }, write: (v) => String(v) } },
  )

  return { defaultParams, globalVolume }
}
