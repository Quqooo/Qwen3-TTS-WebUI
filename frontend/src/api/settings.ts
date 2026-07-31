import { api } from "./client"

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
  max_seq_len: number
}

export const settingsApi = {
  get: () => api.get<ServerSettings>("/settings"),
  update: (data: Partial<ServerSettings>) =>
    api.put<ServerSettings>("/settings", data),
}
