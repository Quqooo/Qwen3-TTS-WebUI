import { ref, type Ref } from "vue"
import JSZip from "jszip"
import type { BatchRow } from "./useBatchTypes"
import { audioCacheDB } from "../utils/audioCacheDB"
import { useToast } from "./useToast"
import { CACHE_VERSION } from "./useBatchCache"
import { t } from "../lang"

const STORAGE_KEY = "batch_cache_persist"

export interface BatchBackupOptions {
  rows: Ref<BatchRow[]>
  saveCache: () => Promise<void>
  restoreCache: () => Promise<void>
  clearAllTasks: () => Promise<void>
}

export function useBatchBackup({
  rows,
  saveCache,
  restoreCache,
  clearAllTasks,
}: BatchBackupOptions) {
  const backupInputRef = ref<HTMLInputElement | null>(null)

  async function exportBackup() {
    const { success, error } = useToast()
    try {
      await saveCache()
      const zip = new JSZip()
      const metadata = localStorage.getItem(STORAGE_KEY)
      if (metadata) zip.file("batch.json", metadata)

      for (const row of rows.value) {
        if (row.audioState === "done") {
          const blob = await audioCacheDB.get(row.id)
          if (blob) zip.file(`audio/${row.id}.wav`, blob)
        }
        const reference = await audioCacheDB.getRefAudio(row.id)
        if (reference) zip.file(`ref/${row.id}.wav`, reference)
      }

      const [audio, resultZip, subtitle] = await Promise.all([
        audioCacheDB.getComposeAudio(),
        audioCacheDB.getComposeZip(),
        audioCacheDB.getComposeSrt(),
      ])
      if (audio) zip.file("compose/audio.wav", audio)
      if (resultZip) zip.file("compose/result.zip", resultZip)
      if (subtitle) zip.file("compose/result.srt", subtitle)

      const blob = await zip.generateAsync({ type: "blob" })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `qwen-tts-backup-${Date.now()}.zip`
      anchor.click()
      URL.revokeObjectURL(url)
      success(t("views.batch.moreConfigDialog.exportSuccess"))
    } catch (cause) {
      error(cause instanceof Error ? cause.message : t("views.batch.moreConfigDialog.exportFailed"))
    }
  }

  async function importBackup(event?: Event) {
    const { success, error } = useToast()
    const input = event?.target instanceof HTMLInputElement
      ? event.target
      : backupInputRef.value
    if (!input?.files?.length) return

    try {
      const zip = await JSZip.loadAsync(input.files[0])
      const metadata = zip.file("batch.json")
      const audioDir = zip.folder("audio")
      const referenceDir = zip.folder("ref")
      if (!metadata && !audioDir) {
        throw new Error(t("views.batch.moreConfigDialog.importInvalid"))
      }

      let metadataText: string | null = null
      if (metadata) {
        metadataText = await metadata.async("text")
        const meta = JSON.parse(metadataText)
        if (meta.version === undefined || meta.version < CACHE_VERSION) {
          throw new Error(t("views.batch.moreConfigDialog.importVersionMismatch"))
        }
      }

      await clearAllTasks()
      const writes: Promise<void>[] = []
      collectBlobEntries(audioDir, (id, blob) => audioCacheDB.put(id, blob), writes)
      collectBlobEntries(referenceDir, (id, blob) => audioCacheDB.putRefAudio(id, blob), writes)

      const composeAudio = zip.file("compose/audio.wav")
      const composeZip = zip.file("compose/result.zip")
      const composeSrt = zip.file("compose/result.srt")
      if (composeAudio) writes.push(composeAudio.async("blob").then(audioCacheDB.putComposeAudio.bind(audioCacheDB)))
      if (composeZip) writes.push(composeZip.async("blob").then(audioCacheDB.putComposeZip.bind(audioCacheDB)))
      if (composeSrt) writes.push(composeSrt.async("text").then(audioCacheDB.putComposeSrt.bind(audioCacheDB)))
      await Promise.all(writes)

      if (metadataText) localStorage.setItem(STORAGE_KEY, metadataText)
      await restoreCache()
      success(t("views.batch.moreConfigDialog.importSuccess"))
    } catch (cause) {
      error(cause instanceof Error ? cause.message : t("views.batch.moreConfigDialog.importFailed"))
    } finally {
      input.value = ""
    }
  }

  return { backupInputRef, exportBackup, importBackup }
}

function collectBlobEntries(
  folder: JSZip | null,
  write: (id: string, blob: Blob) => Promise<void>,
  writes: Promise<void>[],
) {
  folder?.forEach((relativePath, entry) => {
    if (entry.dir) return
    const id = relativePath.replace(/\.wav$/i, "")
    if (!id) return
    writes.push(entry.async("blob").then((blob) => write(id, blob)))
  })
}
