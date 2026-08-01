export interface BatchWaveformData {
  peaks: number[][]
  duration: number
}

const MAX_ENTRIES = 500
const cache = new Map<string, BatchWaveformData>()
const revisions = new Map<string, number>()
let cacheEpoch = 0

function touch(rowId: string, entry: BatchWaveformData) {
  cache.delete(rowId)
  cache.set(rowId, entry)
}

function trim() {
  while (cache.size > MAX_ENTRIES) {
    const oldest = cache.keys().next().value
    if (oldest === undefined) return
    cache.delete(oldest)
  }
}

export function getBatchWaveformRevision(rowId: string): number {
  return cacheEpoch + (revisions.get(rowId) ?? 0)
}

export function getBatchWaveform(rowId: string): BatchWaveformData | undefined {
  const entry = cache.get(rowId)
  if (!entry) return undefined
  touch(rowId, entry)
  return entry
}

export function setBatchWaveform(rowId: string, data: BatchWaveformData) {
  touch(rowId, data)
  trim()
}

export function deleteBatchWaveform(rowId: string) {
  cache.delete(rowId)
  revisions.set(rowId, (revisions.get(rowId) ?? 0) + 1)
}

export function clearBatchWaveforms() {
  cache.clear()
  revisions.clear()
  cacheEpoch++
}
