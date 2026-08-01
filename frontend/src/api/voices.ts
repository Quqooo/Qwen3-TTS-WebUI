import { api } from "./client"

export interface VoiceMeta {
  customName: string
  model: string[]
  text: string
  x_vector_only?: boolean
}

export interface VoicePreview {
  ok: boolean
  audio?: string
  sr?: number
  duration?: number
}

export interface VoiceEditRequest {
  name: string
  new_name?: string
  text?: string
  audio?: string
  model?: string
  x_vector_only?: boolean
}

export const voicesApi = {
  list: () => api.get<{ voices: string[] }>("/voices"),
  get: (name: string) => api.get<VoiceMeta>(`/voices/${encodeURIComponent(name)}`),
  upload: (data: { audio: string; customName?: string; model: string; text?: string; x_vector_only?: boolean }) =>
    api.post<{ path: string }>("/voices/upload", data),
  edit: (data: VoiceEditRequest) =>
    api.post<{ status: string; path: string }>("/voices/edit", data),
  delete: (name: string) => api.post<{ status: string }>("/voices/delete", { name }),
  audio: (name: string, load: boolean) =>
    api.post<VoicePreview>(`/voices/audio/${encodeURIComponent(name)}`, { load }),
}
