import { useToast } from "../composables/useToast"
import { t } from "../lang"

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api"

export class ApiError extends Error {
  status: number
  debug?: string
  constructor(status: number, message: string, debug?: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.debug = debug
  }
}

export function extractErrorText(raw: string): string {
  try {
    const obj = JSON.parse(raw)
    if (obj.detail && typeof obj.detail === "string") {
      return obj.detail
    }
  } catch {
    /* not JSON, use raw */
  }
  return raw
}

export function extractErrorInfo(raw: string): { detail: string; debug?: string } {
  try {
    const obj = JSON.parse(raw)
    const detail = obj.detail && typeof obj.detail === "string" ? obj.detail : raw
    const debug = obj.debug && typeof obj.debug === "string" ? obj.debug : undefined
    return { detail, debug }
  } catch {
    return { detail: raw }
  }
}

function showErrorToast(status: number, detail: string, debug?: string) {
  const { error } = useToast()
  if (status === 503) {
    error(t("api.client.backendUnavailable"), undefined, debug)
  } else if (!detail || !detail.trim()) {
    error(t("api.client.connectionFailed"), undefined, debug)
  } else {
    error(detail, undefined, debug)
  }
}

function showConnectionError() {
  const { error } = useToast()
  error(t("api.client.connectionFailed"))
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`
  let res: Response
  try {
    res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...options.headers },
      ...options,
    })
  } catch {
    showConnectionError()
    throw new ApiError(0, t("api.client.backendUnavailable"))
  }
  if (!res.ok) {
    const raw = await res.text().catch(() => "Unknown error")
    const { detail, debug } = extractErrorInfo(raw)
    const err = new ApiError(res.status, detail, debug)
    showErrorToast(res.status, detail, debug)
    throw err
  }
  return res.json()
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  getBlob: async (path: string): Promise<Blob> => {
    let res: Response
    try {
      res = await fetch(`${API_BASE}${path}`)
    } catch {
      showConnectionError()
      throw new ApiError(0, t("api.client.backendUnavailable"))
    }
    if (!res.ok) {
      const raw = await res.text().catch(() => "Unknown error")
      const { detail, debug } = extractErrorInfo(raw)
      showErrorToast(res.status, detail, debug)
      throw new ApiError(res.status, detail, debug)
    }
    return res.blob()
  },
}
