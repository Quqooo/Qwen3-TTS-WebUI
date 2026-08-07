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

export interface AndimarafiotiSettings {
  max_seq_len: number
  predictor_graph: PredictorGraphSettings
}

export interface ServerSettings {
  gpu_devices: string
  max_concurrent_models: number
  idle_unload_seconds: number
  worker_idle_unload_seconds: number
  backend_branch: string
  backend_branch_options: string[]
  project_dir: string
  env_dir: string
  model_dir: string
  voice_dir: string
  andimarafioti: AndimarafiotiSettings
  batch_composer: BatchComposerSettings
}

export const settingsApi = {
  get: () => api.get<ServerSettings>("/settings"),
  update: (data: Partial<ServerSettings>) =>
    api.put<ServerSettings>("/settings", data),
}
