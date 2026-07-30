import { type Ref } from "vue"

let ctx: AudioContext | null = null
let source: AudioBufferSourceNode | null = null
let active = false

function ensureRunning() {
  if (active) return
  try {
    ctx = new AudioContext()
    const buffer = ctx.createBuffer(1, 1, ctx.sampleRate)
    source = ctx.createBufferSource()
    source.buffer = buffer
    source.loop = true
    source.connect(ctx.destination)
    source.start()
    active = true
  } catch {}
}

function stop() {
  if (!active) return
  try {
    source?.stop()
    source?.disconnect()
    ctx?.close()
  } catch {}
  source = null
  ctx = null
  active = false
}

export function usePageKeepAlive(enabled: Ref<boolean>) {
  function notifyActive(isActive: boolean) {
    if (enabled.value && isActive) {
      ensureRunning()
    } else {
      stop()
    }
  }

  return { notifyActive }
}
