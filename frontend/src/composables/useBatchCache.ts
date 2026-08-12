import { type Ref, watch } from "vue"
import type { BatchRow } from "../types/batch"
import { audioCacheDB } from "../utils/audioCacheDB"
import { CACHE_VERSION, isSupportedCacheVersion, migrateCachedRow } from "../utils/batchVersionCompat"

const STORAGE_KEY = "batch_cache_persist"

export function useBatchCache(opts: {
  rows: Ref<BatchRow[]>
  selectedIndexes: Ref<Set<number>>
  editingIndex: Ref<number>
  persistent: Ref<boolean>
  format: Ref<string>
  sampleRate: Ref<number>
  gain: Ref<number>
  priorityMode: Ref<"model" | "serial">
  strictMode: Ref<boolean>
  concurrentTasks: Ref<number>
  minSilenceMs: Ref<number>
  generationTime: Ref<string>
  rtf: Ref<string>
  finalAudioUrl: Ref<string>
  zipUrl: Ref<string>
  subtitleSrt: Ref<string>
  refAudioCached: Set<string>
}) {
  const {
    rows, selectedIndexes, editingIndex, persistent,
    format, sampleRate, gain, priorityMode, strictMode,
    concurrentTasks, minSilenceMs, generationTime, rtf,
    finalAudioUrl, zipUrl, subtitleSrt, refAudioCached,
  } = opts

  function revokeBlobUrl(url?: string | null) {
    if (url?.startsWith("blob:")) URL.revokeObjectURL(url)
  }

  function replaceBlobUrl(target: Ref<string>, blob: Blob) {
    const previous = target.value
    target.value = URL.createObjectURL(blob)
    revokeBlobUrl(previous)
  }

  function revokeRowUrls(currentRows: BatchRow[]) {
    for (const row of currentRows) {
      revokeBlobUrl(row.audioUrl)
      revokeBlobUrl(row.refAudioUrl)
    }
  }

  async function saveCache(force = false) {
    if (!persistent.value && !force) return
    for (const row of rows.value) {
      if (
        row.cloneSource === "upload" &&
        row.refAudioUrl &&
        row.refAudioUrl.startsWith("blob:") &&
        !refAudioCached.has(row.id)
      ) {
        try {
          const resp = await fetch(row.refAudioUrl)
          const blob = await resp.blob()
          await audioCacheDB.putRefAudio(row.id, blob)
          refAudioCached.add(row.id)
        } catch { /* ignore fetch failures */ }
      }
    }
    const data = {
      version: CACHE_VERSION,
      persistent: true,
      rows: rows.value.map(({ audioUrl, isPlaying, errorMessage, ...rest }) => ({
        ...rest,
        audioState: rest.audioState === "generating" ? "none" : rest.audioState,
      })),
      selectedIndexes: [...selectedIndexes.value],
      editingIndex: editingIndex.value,
      format: format.value,
      sampleRate: sampleRate.value,
      gain: gain.value,
      priorityMode: priorityMode.value,
      strictMode: strictMode.value,
      concurrentTasks: concurrentTasks.value,
      minSilenceMs: minSilenceMs.value,
      generationTime: generationTime.value,
      rtf: rtf.value,
    }
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)) } catch {}

    if (finalAudioUrl.value) {
      try {
        const resp = await fetch(finalAudioUrl.value)
        const blob = await resp.blob()
        await audioCacheDB.putComposeAudio(blob)
      } catch {}
    }
    if (zipUrl.value) {
      try {
        const resp = await fetch(zipUrl.value)
        const blob = await resp.blob()
        await audioCacheDB.putComposeZip(blob)
      } catch {}
    }
    if (subtitleSrt.value) {
      try { await audioCacheDB.putComposeSrt(subtitleSrt.value) } catch {}
    }
  }

  async function restoreCache() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const data = JSON.parse(raw)
      if (!isSupportedCacheVersion(data.version)) return
      if (data.persistent !== true) return
      persistent.value = true
      const previousRows = rows.value
      rows.value = data.rows.map((r: any) => {
        const row: any = {
          ...migrateCachedRow(r),
          instruct: typeof r.instruct === "string" ? r.instruct : "",
          isPlaying: false,
          audioUrl: undefined,
          errorMessage: undefined,
        }
        if (typeof row.refAudioUrl === "string" && row.refAudioUrl.startsWith("blob:")) {
          row._restoreRefAudio = true
          row._refAudioName = row.refAudioName
          row.refAudioUrl = ""
        }
        return row
      })
      revokeRowUrls(previousRows)
      for (const row of rows.value) {
        if (row.audioState === "done") {
          const blob = await audioCacheDB.get(row.id)
          if (blob) row.audioUrl = URL.createObjectURL(blob)
        }
        if ((row as any)._restoreRefAudio) {
          delete (row as any)._restoreRefAudio
          const name = (row as any)._refAudioName
          delete (row as any)._refAudioName
          const ref = await audioCacheDB.getRefAudio(row.id)
          if (ref) {
            row.refAudioUrl = URL.createObjectURL(ref)
            if (name) row.refAudioName = name
          }
        }
      }
      if (data.persistent === true) {
        const [audioBlob, zipBlob, srt] = await Promise.all([
          audioCacheDB.getComposeAudio(),
          audioCacheDB.getComposeZip(),
          audioCacheDB.getComposeSrt(),
        ])
        if (audioBlob) replaceBlobUrl(finalAudioUrl, audioBlob)
        if (zipBlob) replaceBlobUrl(zipUrl, zipBlob)
        if (srt) subtitleSrt.value = srt
      }
      selectedIndexes.value = new Set(data.selectedIndexes || [])
      editingIndex.value = data.editingIndex ?? -1
      if (data.format !== undefined) format.value = data.format
      if (data.sampleRate !== undefined) sampleRate.value = data.sampleRate
      if (data.gain !== undefined) gain.value = data.gain
      if (data.priorityMode) priorityMode.value = data.priorityMode
      if (data.strictMode !== undefined) strictMode.value = data.strictMode
      if (data.concurrentTasks !== undefined) concurrentTasks.value = data.concurrentTasks
      if (data.minSilenceMs !== undefined) minSilenceMs.value = data.minSilenceMs
      if (data.generationTime) generationTime.value = data.generationTime
      if (data.rtf) rtf.value = data.rtf
    } catch {}
  }

  function clearCache() {
    try { localStorage.removeItem(STORAGE_KEY) } catch {}
    refAudioCached.clear()
    audioCacheDB.clear()
    audioCacheDB.clearRefAudio()
    audioCacheDB.removeCompose()
  }

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(saveCache, 500)
  }

  watch(rows, () => {
    scheduleSave()
  }, { deep: true })

  watch([concurrentTasks, minSilenceMs, priorityMode, strictMode, format, sampleRate, gain], () => {
    scheduleSave()
  })

  return { saveCache, restoreCache, clearCache, scheduleSave }
}
