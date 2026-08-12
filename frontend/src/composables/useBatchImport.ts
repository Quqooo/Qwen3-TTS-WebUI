import { ref, watch, type Ref } from "vue"
import type { ModelConfig } from "../components/batch/ModelConfigPanel.vue"
import type { BatchRow } from "../types/batch"
import { parseSubtitleFile } from "../utils/subtitleParser"
import { t } from "../lang"

export interface BatchImportOptions {
  rows: Ref<BatchRow[]>
  importConfig: Ref<ModelConfig>
  fillTimeline: Ref<boolean>
  createRow: (text?: string) => BatchRow
}

export function useBatchImport({ rows, importConfig, fillTimeline, createRow }: BatchImportOptions) {
  const showTextImport = ref(false)
  const showFileImport = ref(false)
  const fileInputRef = ref<HTMLInputElement | null>(null)
  const importText = ref("")
  const importSplitChars = ref(".。!！?？\\n")
  const importRetainSplit = ref<boolean | null>(true)
  const importSplitMode = ref(1)
  const importFiles = ref<File[]>([])
  const fileImportError = ref("")
  const isDragging = ref(false)
  const dragFileIndex = ref(-1)
  let dragCounter = 0

  watch(showTextImport, (visible) => {
    if (!visible) return
    importText.value = ""
    importSplitChars.value = ".。!！?？\\n"
    importRetainSplit.value = true
    importSplitMode.value = 1
  })

  watch(showFileImport, (visible) => {
    if (!visible) return
    importFiles.value = []
    fileImportError.value = ""
  })

  function confirmTextImport() {
    const characters = importSplitChars.value
      .replace(/\\n/g, "\n")
      .replace(/\\t/g, "\t")
      .replace(/\\r/g, "\r")
    if (!characters) return

    const escaped = characters.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&")
    const delimiter = new RegExp(`([${escaped}]+)`)
    const parts = importText.value.split(delimiter)
    const pairs: [string, string][] = []
    for (let index = 0; index < parts.length; index += 2) {
      if (parts[index]) pairs.push([parts[index], parts[index + 1] ?? ""])
    }

    const groupSize = Math.max(1, importSplitMode.value)
    for (let index = 0; index < pairs.length; index += groupSize) {
      const merged = pairs.slice(index, index + groupSize)
        .map(([text, suffix]) => text + suffix)
        .join("")
      const text = (importRetainSplit.value === false
        ? merged.replace(new RegExp(`[${escaped}]+$`), "")
        : merged).trim()
      const row = createRow(text)
      Object.assign(row, importConfig.value, { text })
      rows.value.push(row)
    }

    showTextImport.value = false
  }

  function onFileDragOver(event: DragEvent) {
    event.preventDefault()
  }

  function onFileDragEnter() {
    dragCounter++
    isDragging.value = true
  }

  function onFileDragLeave() {
    dragCounter--
    if (dragCounter <= 0) {
      dragCounter = 0
      isDragging.value = false
    }
  }

  function onFileDrop(event: DragEvent) {
    event.preventDefault()
    dragCounter = 0
    isDragging.value = false
    addImportFiles(Array.from(event.dataTransfer?.files ?? []))
  }

  function onFileInput(event: Event) {
    const input = event.target as HTMLInputElement
    addImportFiles(Array.from(input.files ?? []))
    input.value = ""
  }

  function onFileDragStart(index: number, event: DragEvent) {
    dragFileIndex.value = index
    if (!event.dataTransfer) return
    event.dataTransfer.effectAllowed = "move"
    event.dataTransfer.setData("text/plain", "")
  }

  function onFileDragEnterItem(index: number) {
    const from = dragFileIndex.value
    if (from < 0 || from === index) return
    const [file] = importFiles.value.splice(from, 1)
    importFiles.value.splice(index, 0, file)
    dragFileIndex.value = index
  }

  function onFileDragEnd() {
    dragFileIndex.value = -1
  }

  function addImportFiles(files: File[]) {
    fileImportError.value = ""
    for (const file of files) {
      const extension = file.name.split(".").pop()?.toLowerCase()
      if (extension === "srt" || extension === "lrc") importFiles.value.push(file)
    }
    if (importFiles.value.length === 0) {
      fileImportError.value = t("views.batch.statusPanel.fileTypeError")
    }
  }

  function removeImportFile(index: number) {
    importFiles.value.splice(index, 1)
  }

  async function confirmFileImport() {
    for (const file of importFiles.value) {
      try {
        const segments = await parseSubtitleFile(file)
        for (const segment of segments) {
          const row = createRow(segment.text)
          Object.assign(row, importConfig.value, { text: segment.text })
          if (fillTimeline.value && segment.start !== undefined) {
            row.timelineEnabled = true
            row.timelineStart = segment.start
            row.timelineEnd = segment.end ?? 0
          }
          rows.value.push(row)
        }
      } catch {
        // Skip malformed subtitle files while importing the remaining files.
      }
    }
    importFiles.value = []
    showFileImport.value = false
  }

  return {
    showTextImport,
    showFileImport,
    fileInputRef,
    importText,
    importSplitChars,
    importRetainSplit,
    importSplitMode,
    importFiles,
    fileImportError,
    isDragging,
    dragFileIndex,
    confirmTextImport,
    onFileDragOver,
    onFileDragEnter,
    onFileDragLeave,
    onFileDrop,
    onFileInput,
    onFileDragStart,
    onFileDragEnterItem,
    onFileDragEnd,
    removeImportFile,
    confirmFileImport,
  }
}
