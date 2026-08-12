import { type Ref } from "vue"
import type { BatchRow } from "../types/batch"
import type { SynthesisRequest, ComposeSegment } from "../types"
import { synthesisApi, composeApi, getBlobDuration } from "../api/synthesis"
import { audioCacheDB } from "../utils/audioCacheDB"
import { deleteBatchWaveform } from "../utils/batchWaveformCache"
import JSZip from "jszip"
import { t } from "../lang"

export interface GenEngineOpts {
  rows: Ref<BatchRow[]>
  format: Ref<string>
  sampleRate: Ref<number>
  strictMode: Ref<boolean>
  minSilenceMs: Ref<number>
  priorityMode: Ref<"model" | "serial">
  concurrentTasks: Ref<number>
  generating: Ref<boolean>
  isPaused: Ref<boolean>
  generationTime: Ref<string>
  rtf: Ref<string>
  completedCount: Ref<number>
  totalAudioDuration: Ref<number>
  composing: Ref<boolean>
  composeError: Ref<string>
  finalAudioUrl: Ref<string>
  zipUrl: Ref<string>
  subtitleSrt: Ref<string>
  persistent: Ref<boolean>
  /** Callback: build a synthesis request for a given row */
  buildRequest: (row: BatchRow) => Promise<SynthesisRequest>
  /** Callback: add an error message for display */
  addError: (rowId: string, message: string) => void
}

export function useBatchGeneration(opts: GenEngineOpts) {
  const {
    rows, format, sampleRate, strictMode, minSilenceMs,
    priorityMode, concurrentTasks, generating, isPaused,
    generationTime, rtf, completedCount, totalAudioDuration,
    composing, composeError, finalAudioUrl, zipUrl, subtitleSrt,
    persistent, buildRequest, addError,
  } = opts

  let batchQueue: string[] = []
  let batchCursor = 0
  const pendingTasks = new Map<string, Promise<void>>()
  const runningControllers = new Map<string, AbortController>()
  let generationEpoch = 0
  let genTimer = 0
  let genStartTime = 0
  let genElapsed = 0

  // ── Index helpers ────────────────────────────────────────────────────

  function rowById(id: string): BatchRow | undefined {
    return rows.value.find(r => r.id === id)
  }

  function revokeBlobUrl(url?: string | null) {
    if (url?.startsWith("blob:")) URL.revokeObjectURL(url)
  }

  function replaceBlobUrl(target: Ref<string>, blob: Blob) {
    const previous = target.value
    target.value = URL.createObjectURL(blob)
    revokeBlobUrl(previous)
  }

  function clearBlobUrl(target: Ref<string>) {
    const previous = target.value
    target.value = ""
    revokeBlobUrl(previous)
  }

  // ── Timer ────────────────────────────────────────────────────────────

  function startGenTimer() {
    stopGenTimer()
    const tick = () => {
      if (!generating.value && !isPaused.value) { stopGenTimer(); return }
      const elapsed = (genElapsed + (performance.now() - genStartTime)) / 1000
      generationTime.value = `${elapsed.toFixed(2)}s`
      genTimer = requestAnimationFrame(tick)
    }
    genTimer = requestAnimationFrame(tick)
  }

  function stopGenTimer() {
    if (genTimer) { cancelAnimationFrame(genTimer); genTimer = 0 }
  }

  // ── Queue ────────────────────────────────────────────────────────────

  function buildBatchQueue() {
    const items = rows.value
      .map((r, i) => ({ id: r.id, idx: i, model: r.model, text: r.text, finalized: r.finalized }))
      .filter(r => !r.finalized && r.text.trim())
    if (priorityMode.value === "model") {
      items.sort((a, b) => {
        const ma = a.model
        const mb = b.model
        return ma.localeCompare(mb) || a.idx - b.idx
      })
    }
    batchQueue = items.map(r => r.id)
  }

  // ── Progress ─────────────────────────────────────────────────────────

  function updateProgress() {
    const elapsed = (genElapsed + (performance.now() - genStartTime)) / 1000
    generationTime.value = `${elapsed.toFixed(2)}s`
    rtf.value = (elapsed / Math.max(0.001, totalAudioDuration.value)).toFixed(3)
  }

  // ── Task Runner ──────────────────────────────────────────────────────

  async function _runOneTask(rowId: string, epoch: number): Promise<void> {
    const row = rowById(rowId)
    if (!row || row.finalized || !row.text.trim()) { pendingTasks.delete(rowId); return }
    row.audioState = "generating"
    const controller = new AbortController()
    runningControllers.get(rowId)?.abort()
    runningControllers.set(rowId, controller)
    try {
      const req = await buildRequest(row)
      controller.signal.throwIfAborted()
      if (epoch !== generationEpoch) return
      const blob = await synthesisApi.synthesize(req, controller.signal)
      controller.signal.throwIfAborted()
      if (epoch !== generationEpoch || runningControllers.get(rowId) !== controller) return
      const previousAudioUrl = row.audioUrl
      deleteBatchWaveform(row.id)
      row.audioUrl = URL.createObjectURL(blob)
      revokeBlobUrl(previousAudioUrl)
      audioCacheDB.put(row.id, blob)
      row.audioState = "done"
      try {
        const duration = await getBlobDuration(blob)
        if (!controller.signal.aborted && epoch === generationEpoch) totalAudioDuration.value += duration
      } catch { /* ignore */ }
    } catch (e: any) {
      if (controller.signal.aborted || epoch !== generationEpoch || e?.name === "AbortError") {
        if (
          epoch === generationEpoch
          && runningControllers.get(rowId) === controller
          && row.audioState === "generating"
        ) {
          row.audioState = "none"
        }
        return
      }
      row.audioState = "error"
      row.errorMessage = e?.message || t('composables.batchGeneration.generateFailed')
      addError(rowId, e?.message || t('composables.batchGeneration.generateFailed'))
    } finally {
      if (runningControllers.get(rowId) === controller) {
        runningControllers.delete(rowId)
        pendingTasks.delete(rowId)
      }
    }
    if (controller.signal.aborted || epoch !== generationEpoch) return
    completedCount.value++
    updateProgress()
  }

  // ── Pool Scheduler ───────────────────────────────────────────────────

  async function processNextBatchRow(epoch: number) {
    while (epoch === generationEpoch && generating.value && !isPaused.value) {
      while (batchCursor < batchQueue.length && pendingTasks.size < concurrentTasks.value) {
        const rowId = batchQueue[batchCursor++]
        const row = rowById(rowId)
        if (!row || row.finalized || !row.text.trim()) continue
        pendingTasks.set(rowId, _runOneTask(rowId, generationEpoch))
      }

      if (pendingTasks.size === 0) break

      await Promise.race(pendingTasks.values())
    }

    if (epoch !== generationEpoch) return

    if (!generating.value) {
      if (isPaused.value) return
      for (const rowId of batchQueue) {
        const r = rowById(rowId)
        if (r && r.audioState === "generating") r.audioState = "none"
      }
      return
    }

    stopGenTimer()
    updateProgress()
    generating.value = false
    isPaused.value = false
    if (rows.value.some(r => r.audioState === "done")) {
      await doFinalComposition()
    }
  }

  // ── Composition ──────────────────────────────────────────────────────

  async function doFinalComposition() {
    composing.value = true
    composeError.value = ""
    try {
      const doneRows = rows.value
        .map((r, i) => ({ row: r, idx: i }))
        .filter(({ row }) => row.audioState === "done" && row.audioUrl)

      const segments: ComposeSegment[] = []
      for (const { row, idx } of doneRows) {
        const resp = await fetch(row.audioUrl!)
        const blob = await resp.blob()
        const reader = new FileReader()
        const b64 = await new Promise<string>((resolve, reject) => {
          reader.onload = () => {
            const result = reader.result as string
            resolve(result.split(",")[1])
          }
          reader.onerror = reject
          reader.readAsDataURL(blob)
        })
        segments.push({
          sort: idx,
          audio: b64,
          text: row.text,
          ...(row.timelineEnabled ? { start: row.timelineStart, end: row.timelineEnd || undefined } : {}),
        })
      }

      if (segments.length === 0) return

      const result = await composeApi.compose(
        segments,
        strictMode.value ? "strict" : "lenient",
        format.value,
        sampleRate.value,
        0,
        minSilenceMs.value,
      )
      const audioBytes = Uint8Array.from(atob(result.audio_base64), c => c.charCodeAt(0))
      const audioBlob = new Blob([audioBytes], { type: `audio/${result.format}` })
      replaceBlobUrl(finalAudioUrl, audioBlob)
      subtitleSrt.value = result.subtitle_srt

      const ext = result.format === "wav" ? "wav" : result.format

      const zip = new JSZip()
      for (const { row, idx } of doneRows) {
        if (!row.audioUrl) continue
        const resp = await fetch(row.audioUrl)
        const blob = await resp.blob()
        const modelTag = row.modelKind === "custom_voice" ? "CustomVoice"
          : row.modelKind === "voice_design" ? "VoiceDesign" : "Base"
        const prefix = row.text.replace(/\s+/g, "").slice(0, 4)
        zip.file(`#${String(idx + 1).padStart(3, "0")}_${prefix}_${modelTag}.${ext}`, blob)
      }
      const zipBlob = await zip.generateAsync({ type: "blob" })
      replaceBlobUrl(zipUrl, zipBlob)

      if (persistent.value) {
        audioCacheDB.putComposeAudio(audioBlob)
        audioCacheDB.putComposeZip(zipBlob)
        audioCacheDB.putComposeSrt(result.subtitle_srt)
      }
    } catch (e: any) {
      composeError.value = e?.message || t('composables.batchGeneration.composeFailed')
      addError("", t('composables.batchGeneration.finalComposeFailed', { error: composeError.value }))
    } finally {
      composing.value = false
    }
  }

  // ── Abort ─────────────────────────────────────────────────────────

  function abortAllRunning() {
    generationEpoch++
    for (const [rowId, controller] of runningControllers) {
      controller.abort()
      const row = rowById(rowId)
      if (row && row.audioState === "generating") row.audioState = "none"
    }
    runningControllers.clear()
    pendingTasks.clear()
  }

  // ── Retry ────────────────────────────────────────────────────────────

  function retryFailed() {
    if (generating.value || isPaused.value) return
    batchQueue = []
    for (const row of rows.value) {
      if (row.audioState === "error") {
        row.audioState = "none"
        row.errorMessage = undefined
        audioCacheDB.remove(row.id)
        if (!row.finalized && row.text.trim()) batchQueue.push(row.id)
      }
    }
    if (batchQueue.length === 0) return
    isPaused.value = false
    generating.value = true
    genStartTime = performance.now()
    batchCursor = 0
    generationEpoch++
    runningControllers.clear()
    pendingTasks.clear()
    startGenTimer()
    processNextBatchRow(generationEpoch)
  }

  // ── Lifecycle ────────────────────────────────────────────────────────

  function toggleBatchGenerate() {
    if (generating.value) {
      genElapsed += performance.now() - genStartTime
      stopGenTimer()
      updateProgress()
      abortAllRunning()
      isPaused.value = true
      generating.value = false
    } else if (isPaused.value) {
      isPaused.value = false
      generating.value = true
      genStartTime = performance.now()
      while (batchCursor > 0) {
        const prevId = batchQueue[batchCursor - 1]
        const prevRow = rowById(prevId)
        if (prevRow && !prevRow.finalized && prevRow.text.trim() && prevRow.audioState !== "done") {
          batchCursor--
        } else {
          break
        }
      }
      startGenTimer()
      processNextBatchRow(generationEpoch)
    } else {
      isPaused.value = false
      generating.value = true
      genStartTime = performance.now()
      genElapsed = 0
      completedCount.value = 0
      totalAudioDuration.value = 0
      batchCursor = 0
      clearBlobUrl(finalAudioUrl)
      clearBlobUrl(zipUrl)
      subtitleSrt.value = ""
      composeError.value = ""
      generationTime.value = "--:--"
      rtf.value = "--"
      generationEpoch++
      buildBatchQueue()
      startGenTimer()
      processNextBatchRow(generationEpoch)
    }
  }

  function stopRowGenerate(rowId: string) {
    const controller = runningControllers.get(rowId)
    if (!controller) return
    controller.abort()
    runningControllers.delete(rowId)
    pendingTasks.delete(rowId)
    const row = rowById(rowId)
    if (row && row.audioState === "generating") row.audioState = "none"
  }

  function stopBatchGenerate() {
    stopGenTimer()
    abortAllRunning()
    generating.value = false
    isPaused.value = false
    genElapsed = 0
    totalAudioDuration.value = 0
    batchCursor = 0
    batchQueue = []
    generationTime.value = "--:--"
    rtf.value = "--"
  }

  return { toggleBatchGenerate, stopBatchGenerate, stopRowGenerate, retryFailed }
}
