import type { BatchRow } from "../types/batch"

export const CACHE_VERSION = 2

type CachedRow = Partial<BatchRow> & Record<string, unknown>

export function migrateCachedRow(row: CachedRow): Partial<BatchRow> {
  if (row.xVectorOnly === undefined && row.xvecOnly !== undefined) {
    row.xVectorOnly = row.xvecOnly as boolean
  }
  return row
}

export function isSupportedCacheVersion(version: unknown): boolean {
  return typeof version === "number" && version >= 1 && version <= CACHE_VERSION
}
