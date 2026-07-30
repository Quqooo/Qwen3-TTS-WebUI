import type { WsMessage } from "../types"

type MessageCallback = (msg: WsMessage) => void
type ConnectionCallback = (connected: boolean) => void

const VALID_TYPES = new Set(["cache", "worker", "tracker"])

function isWsMessage(value: unknown): value is WsMessage {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    "data" in value &&
    typeof (value as Record<string, unknown>).type === "string" &&
    VALID_TYPES.has((value as Record<string, unknown>).type as string) &&
    (value as Record<string, unknown>).data !== null
  )
}

/**
 * 创建 WebSocket 连接，接收缓存状态和 Worker 状态推送。
 * 返回清理函数。
 */
export function createCacheWebSocket(
  onMessage: MessageCallback,
  onConnectionChange?: ConnectionCallback,
): () => void {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:"
  const url = `${protocol}//${location.host}/api/ws/cache`
  let ws: WebSocket | null = null
  let reconnectDelay = 1000
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pingInterval: ReturnType<typeof setInterval> | null = null
  let destroyed = false

  function clearReconnectTimer() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function disconnect() {
    clearReconnectTimer()
    const current = ws
    ws = null
    if (!current) return
    current.onopen = null
    current.onmessage = null
    current.onerror = null
    current.onclose = null
    current.close()
  }

  function scheduleReconnect() {
    if (destroyed || document.hidden || reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, reconnectDelay)
    reconnectDelay = Math.min(reconnectDelay * 2, 30000)
  }

  function connect() {
    if (destroyed || document.hidden || ws) return
    const socket = new WebSocket(url)
    ws = socket

    socket.onopen = () => {
      if (ws !== socket) return
      reconnectDelay = 1000
      onConnectionChange?.(true)
    }

    socket.onmessage = (event) => {
      if (ws !== socket || event.data === "pong") return
      try {
        const msg = JSON.parse(event.data)
        if (msg && typeof msg.type === "string" && msg.data) {
          if (isWsMessage(msg)) onMessage(msg)
        }
      } catch {
        // ignore malformed messages
      }
    }

    socket.onclose = () => {
      if (ws !== socket) return
      ws = null
      onConnectionChange?.(false)
      scheduleReconnect()
    }

    socket.onerror = () => {
      if (ws === socket) socket.close()
    }
  }

  function onVisibilityChange() {
    if (document.hidden) {
      disconnect()
      onConnectionChange?.(false)
      return
    }
    reconnectDelay = 1000
    connect()
  }

  pingInterval = setInterval(() => {
    if (!document.hidden && ws?.readyState === WebSocket.OPEN) {
      ws.send("ping")
    }
  }, 20000)

  document.addEventListener("visibilitychange", onVisibilityChange)
  connect()

  return () => {
    destroyed = true
    document.removeEventListener("visibilitychange", onVisibilityChange)
    if (pingInterval) clearInterval(pingInterval)
    disconnect()
  }
}
