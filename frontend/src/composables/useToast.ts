import { ref } from "vue"

export interface Toast {
  id: number
  message: string
  type: "success" | "error" | "warning" | "info"
  duration: number
  debug?: string
}

const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  function show(message: string, type: Toast["type"] = "info", duration = 3000, debug?: string) {
    const duplicate = toasts.value.find((t) => t.type === type && t.message === message)
    if (duplicate) return duplicate.id
    const id = nextId++
    toasts.value.push({ id, message, type, duration, debug })
    return id
  }

  function dismiss(id: number) {
    const idx = toasts.value.findIndex((t) => t.id === id)
    if (idx >= 0) toasts.value.splice(idx, 1)
  }

  function success(message: string, duration?: number, debug?: string) {
    return show(message, "success", duration, debug)
  }

  function error(message: string, duration?: number, debug?: string) {
    return show(message, "error", duration ?? 3000, debug)
  }

  function warning(message: string, duration?: number, debug?: string) {
    return show(message, "warning", duration, debug)
  }

  function info(message: string, duration?: number, debug?: string) {
    return show(message, "info", duration, debug)
  }

  return { toasts, show, dismiss, success, error, warning, info }
}
