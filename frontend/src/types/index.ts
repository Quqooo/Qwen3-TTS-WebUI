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

export interface ModelCacheEntry {
  id: string
  gpu: string
  kind: ModelKind
  last_used: number
  meta: ModelMeta
}

export interface ModelCacheStatus {
  loaded: ModelCacheEntry[]
  max_concurrent: number
  usage_order: { id: string; gpu: string }[]
}

export interface WorkerGpuStatus {
  gpu: string
  alive: boolean
  error: string | null
  pid: number | null
  models: string[]
  inflight: number
  last_activity: number | null
}

export interface WorkerStatus {
  alive: boolean
  error: string | null
  gpus?: string[]
  workers?: WorkerGpuStatus[]
}

export interface TrackerStatus {
  inference_counts: Record<string, number>
  inference_gpus: Record<string, Record<string, number>>
  inference_total: number
}

export interface BackendInfo {
  backend_branch: string
  backend_branch_options: string[]
}

export type WsMessage =
  | { type: "cache"; data: ModelCacheStatus }
  | { type: "worker"; data: WorkerStatus }
  | { type: "tracker"; data: TrackerStatus }
  | { type: "backend"; data: BackendInfo }

export interface GenerationParams {
  do_sample?: boolean
  top_k?: number
  top_p?: number
  temperature?: number
  repetition_penalty?: number
  subtalker_dosample?: boolean
  subtalker_top_k?: number
  subtalker_top_p?: number
  subtalker_temperature?: number
  min_new_tokens?: number
  max_new_tokens?: number
  non_streaming_mode?: boolean
  seed?: number
}

export interface GenerationParamsConfig extends GenerationParams {
  enabled: boolean
}

export interface SynthesisOutputParams {
  format: string
  sample_rate: number
  gain: number
}

export interface DffdeeqParams {
  emit_every_frames?: number
  decode_window_frames?: number
  overlap_samples?: number
  max_frames?: number
}

export interface AndimarafiotiParams {
  chunk_size?: number
  parity_mode?: boolean
}

export interface SynthesisRequest {
  model: string
  text: string
  language?: string
  kind: ModelKind
  speaker?: string
  instruct?: string
  ref_audio?: string
  ref_text?: string
  voice_file?: string
  x_vector_only?: boolean
  streaming?: boolean
  split_string?: string[]
  output: SynthesisOutputParams
  generation_params?: GenerationParams
  dffdeeq?: DffdeeqParams
  andimarafioti?: AndimarafiotiParams
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
