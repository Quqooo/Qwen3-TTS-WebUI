export type ModelKind = "base" | "custom_voice" | "voice_design"

export interface ModelMetaOption {
  value: string
  label: string
}

export interface ModelMeta {
  languages: ModelMetaOption[]
  speakers: ModelMetaOption[]
}

export interface ModelInfo {
  id: string
  kind: ModelKind
}

export interface ModelCacheStatus {
  loaded: { id: string; kind: ModelKind; last_used: number; meta: ModelMeta }[]
  max_concurrent: number
  usage_order: string[]
}

export interface WorkerStatus {
  alive: boolean
  error: string | null
}

export interface TrackerStatus {
  inference_counts: Record<string, number>
  inference_total: number
}

export type WsMessage =
  | { type: "cache"; data: ModelCacheStatus }
  | { type: "worker"; data: WorkerStatus }
  | { type: "tracker"; data: TrackerStatus }

export interface GenerationParams {
  do_sample?: boolean
  top_k?: number
  top_p?: number
  temperature?: number
  repetition_penalty?: number
  subtalker_top_k?: number
  subtalker_top_p?: number
  subtalker_temperature?: number
  max_new_tokens?: number
}

export interface SynthesisRequest {
  model: string
  text: string
  language?: string
  kind: ModelKind
  speaker?: string
  instruct?: string
  voice_description?: string
  ref_audio?: string
  ref_text?: string
  voice_file?: string
  x_vector_only?: boolean
  streaming?: boolean
  emit_every_frames?: number
  decode_window_frames?: number
  overlap_samples?: number
  max_frames?: number
  output_format?: string
  output_sample_rate?: number
  gain?: number
  split_characters?: string[]
  split_enabled?: boolean
  generation_params?: GenerationParams
}

export interface VoiceFile {
  name: string
  path: string
  ref_text?: string
  x_vector_only?: boolean
  model?: string
  has_preview_audio?: boolean
}

export interface ComposeSegment {
  sort: number
  audio: string
  start?: number
  end?: number
  text: string
}

export interface ComposeResponse {
  audio_base64: string
  subtitle_srt: string
  format: string
  duration: number
  sample_rate: number
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $t(path: string, params?: Record<string, string | number>): string
  }
}
