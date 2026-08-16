import { api } from "./client"

export interface BatchComposerSettings {
  max_segments: number
  max_output_samples: number
  max_decoded_samples: number
  max_total_decoded_samples: number
  max_time_stretch_rate: number
  max_audio_mib: number
  max_total_audio_mib: number
  min_sample_rate: number
  max_sample_rate: number
}

export interface PredictorGraphSettings {
  do_sample: boolean
  top_k: number
  top_p: number
  temperature: number
}

export interface FasterSettings {
  max_seq_len: number
  predictor_graph: PredictorGraphSettings
}

export interface QwenSettings {
  attn_implementation: string
}

export interface StreamingSettings {
  use_compile: boolean
  use_cuda_graphs: boolean
  compile_mode: string
  use_fast_codebook: boolean
  compile_codebook_predictor: boolean
  compile_talker: boolean
  attn_implementation: string
}

/** 服务端真实配置项（GET 响应的 settings 字段 / PUT 请求体）。 */
export interface ServerSettings {
  gpu_devices: string
  dtype: string
  max_concurrent_models: number
  idle_unload_seconds: number
  worker_idle_unload_seconds: number
  backend_branch: string
  project_dir: string
  env_dir: string
  model_dir: string
  voice_dir: string
  faster: FasterSettings
  qwenlm: QwenSettings
  streaming: StreamingSettings
  batch_composer: BatchComposerSettings
}

/** 下拉枚举选项（只读元数据，键名与设置字段同名）。 */
export interface SettingsOptions {
  backend_branch: string[]
  dtype: string[]
  attn_implementation: string[]
  compile_mode: string[]
}

/** 新格式响应：真实配置收进 settings，枚举选项收进 options。 */
export interface SettingsResponse {
  settings: ServerSettings
  options: SettingsOptions
}

/** 旧后端平铺格式（配置值与 *_options 混在同一层），仅过渡兼容。 */
export interface LegacySettingsResponse extends ServerSettings {
  backend_branch_options?: string[]
  dtype_options?: string[]
  attn_implementation_options?: string[]
  compile_mode_options?: string[]
}

export type SettingsGetResponse = SettingsResponse | LegacySettingsResponse

function unique(values: readonly (string | undefined)[]): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))]
}

function optionsFromLegacy(data: LegacySettingsResponse, values: ServerSettings): SettingsOptions {
  return {
    backend_branch: data.backend_branch_options ?? (values.backend_branch ? [values.backend_branch] : []),
    dtype: data.dtype_options ?? (values.dtype ? [values.dtype] : []),
    attn_implementation: data.attn_implementation_options
      ?? unique([values.streaming?.attn_implementation, values.qwenlm?.attn_implementation]),
    compile_mode: data.compile_mode_options
      ?? (values.streaming?.compile_mode ? [values.streaming.compile_mode] : []),
  }
}

function normalizeOptions(
  options: SettingsOptions | undefined,
  values: ServerSettings,
  legacy: LegacySettingsResponse,
): SettingsOptions {
  const fallback = optionsFromLegacy(legacy, values)
  return {
    backend_branch: options?.backend_branch ?? fallback.backend_branch,
    dtype: options?.dtype ?? fallback.dtype,
    attn_implementation: options?.attn_implementation ?? fallback.attn_implementation,
    compile_mode: options?.compile_mode ?? fallback.compile_mode,
  }
}

/**
 * 将 GET/PUT 响应解析为统一的 { settings, options }，
 * 兼容旧后端把配置与 *_options 平铺在同一层的格式。
 */
export function resolveSettings(data: SettingsGetResponse): { settings: ServerSettings; options: SettingsOptions } {
  if ("settings" in data && data.settings) {
    return {
      settings: data.settings,
      options: normalizeOptions(data.options, data.settings, data as unknown as LegacySettingsResponse),
    }
  }
  const values = data as unknown as ServerSettings
  return { settings: values, options: normalizeOptions(undefined, values, data as LegacySettingsResponse) }
}

export const settingsApi = {
  get: () => api.get<SettingsGetResponse>("/settings"),
  update: (data: Partial<ServerSettings>) =>
    api.put<SettingsGetResponse>("/settings", data),
}
