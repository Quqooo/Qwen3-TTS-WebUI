import { reactive, ref, type Ref, watch } from "vue"
import type { BatchRow } from "../types/batch"

export function useBatchAudio(opts: {
  rows: Ref<BatchRow[]>
  initialVolume: number
}) {
  const { rows, initialVolume } = opts
  const rowProgress = reactive<Record<string, number>>({})
  const tableVolume = ref(initialVolume)
  const rowAudios = new Map<string, HTMLAudioElement>()
  const progressRafs = new Map<string, number>()

  function getRowAudio(rowId: string, url: string): HTMLAudioElement {
    let audio = rowAudios.get(rowId)
    if (!audio) {
      audio = new Audio(url)
      audio.volume = tableVolume.value
      audio.addEventListener("ended", () => onRowAudioEnded(rowId))
      audio.addEventListener("play", () => startRowPolling(rowId))
      audio.addEventListener("pause", () => stopRowPolling(rowId))
      rowAudios.set(rowId, audio)
    }
    return audio
  }

  function togglePlayRow(idx: number) {
    const row = rows.value[idx]
    if (row.audioState !== "done" || !row.audioUrl) return
    const audio = getRowAudio(row.id, row.audioUrl)
    if (row.isPlaying) {
      audio.pause()
      row.isPlaying = false
    } else {
      if (audio.src !== row.audioUrl) {
        audio.src = row.audioUrl
        rowProgress[row.id] = 0
      }
      const saved = rowProgress[row.id] ?? 0
      if (saved > 0 && audio.currentTime === 0) {
        if (audio.duration > 0) {
          audio.currentTime = saved * audio.duration
        } else {
          audio.addEventListener("loadedmetadata", () => {
            audio.currentTime = saved * audio.duration
          }, { once: true })
        }
      }
      ;(async () => {
        try { await audio.play() } catch (e) { console.warn("play failed", e) }
      })()
      row.isPlaying = true
    }
  }

  function onRowAudioEnded(rowId: string) {
    rowProgress[rowId] = 0
    const row = rows.value.find(r => r.id === rowId)
    if (row) row.isPlaying = false
  }

  function onSeekWaveform(rowId: string, val: number) {
    const row = rows.value.find(r => r.id === rowId)
    if (!row || !row.audioUrl) return
    rowProgress[rowId] = val
    const audio = rowAudios.get(rowId)
    if (audio && audio.src === row.audioUrl && audio.duration > 0) {
      audio.currentTime = val * audio.duration
    }
  }

  function startRowPolling(rowId: string) {
    stopRowPolling(rowId)
    function poll() {
      const audio = rowAudios.get(rowId)
      if (!audio || audio.paused || audio.ended) return
      const dur = audio.duration
      if (dur && dur > 0) {
        rowProgress[rowId] = audio.currentTime / dur
      }
      const raf = requestAnimationFrame(poll)
      progressRafs.set(rowId, raf)
    }
    const raf = requestAnimationFrame(poll)
    progressRafs.set(rowId, raf)
  }

  function stopRowPolling(rowId: string) {
    const raf = progressRafs.get(rowId)
    if (raf) { cancelAnimationFrame(raf); progressRafs.delete(rowId) }
  }

  function destroyRowAudio(rowId: string) {
    stopRowPolling(rowId)
    const audio = rowAudios.get(rowId)
    if (audio) { audio.pause(); audio.removeAttribute("src"); audio.load() }
    rowAudios.delete(rowId)
  }

  function destroyAllAudio() {
    for (const id of rowAudios.keys()) destroyRowAudio(id)
  }

  function downloadRowAudio(idx: number) {
    const row = rows.value[idx]
    if (row.audioState !== "done" || !row.audioUrl) return
    const a = document.createElement("a")
    a.href = row.audioUrl
    a.download = `#${idx + 1}.wav`
    a.click()
  }

  function onTableVolumeWheel(ev: WheelEvent) {
    ev.preventDefault()
    const delta = ev.deltaY > 0 ? -0.05 : 0.05
    tableVolume.value = Math.max(0, Math.min(1, tableVolume.value + delta))
  }

  watch(tableVolume, (v) => {
    for (const audio of rowAudios.values()) audio.volume = v
  }, { immediate: true })

  return {
    rowProgress,
    tableVolume,
    rowAudios,
    progressRafs,
    getRowAudio,
    togglePlayRow,
    onRowAudioEnded,
    onSeekWaveform,
    startRowPolling,
    stopRowPolling,
    destroyRowAudio,
    destroyAllAudio,
    downloadRowAudio,
    onTableVolumeWheel,
  }
}
