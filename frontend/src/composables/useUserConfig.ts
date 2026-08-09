import { useStorage } from "@vueuse/core"
import type { ModelKind, GenerationParamsConfig } from "../types"

const DEFAULT_PARAMS: GenerationParamsConfig = {
  enabled: false,
  do_sample: true,
  temperature: 0.9,
  top_k: 50,
  top_p: 1.0,
  repetition_penalty: 1.05,
  subtalker_dosample: true,
  subtalker_top_k: 50,
  subtalker_top_p: 1.0,
  subtalker_temperature: 0.9,
  min_new_tokens: undefined,
  max_new_tokens: 2048,
  non_streaming_mode: undefined,
  seed: undefined,
}

const DEFAULT_PARAMS_BY_KIND: Record<ModelKind, GenerationParamsConfig> = {
  base: { ...DEFAULT_PARAMS },
  custom_voice: { ...DEFAULT_PARAMS },
  voice_design: { ...DEFAULT_PARAMS },
}

function sanitizeParams(v: unknown): Record<ModelKind, GenerationParamsConfig> {
  if (!v || typeof v !== "object") return { ...DEFAULT_PARAMS_BY_KIND }
  const raw = v as Record<string, Partial<GenerationParamsConfig>>
  const result = { ...DEFAULT_PARAMS_BY_KIND }
  for (const kind of ["base", "custom_voice", "voice_design"] as ModelKind[]) {
    if (raw[kind] && typeof raw[kind] === "object") {
      result[kind] = { ...DEFAULT_PARAMS, ...raw[kind] }
    }
  }
  return result
}

export function useUserConfig() {
  const defaultParams = useStorage<Record<ModelKind, GenerationParamsConfig>>(
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
