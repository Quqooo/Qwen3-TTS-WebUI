import { api } from "./client"
import type { ModelInfo, ModelCacheStatus, ModelMeta } from "../types"

export const modelsApi = {
  list: () => api.get<{ models: ModelInfo[] }>("/models"),
  load: (modelId: string) => api.post<{ message: string }>("/models/load", { model: modelId }),
  unload: (modelId: string) => api.post<{ message: string }>("/models/unload", { model: modelId }),
  cacheStatus: () => api.get<ModelCacheStatus>("/models/cache"),
  updateCache: (maxConcurrent: number) => api.put<ModelCacheStatus>("/models/cache", { max_concurrent: maxConcurrent }),
  getMeta: (modelId: string) => api.get<ModelMeta>(`/models/meta/${encodeURIComponent(modelId)}`),
}
