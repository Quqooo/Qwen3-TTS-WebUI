import { nextTick, ref, type Ref } from "vue"
import type { BatchRow } from "./useBatchTypes"

export interface BatchRowInteractionOptions {
  rows: Ref<BatchRow[]>
  selectedIndexes: Ref<Set<number>>
  editingIndex: Ref<number>
  generating: Ref<boolean>
}

export function useBatchRowInteractions({
  rows,
  selectedIndexes,
  editingIndex,
  generating,
}: BatchRowInteractionOptions) {
  const lastClickedIndex = ref(-1)
  const editingTextId = ref<string | null>(null)
  const editingTextValue = ref("")
  const dragRowIndex = ref(-1)

  function onRowClick(index: number, event: MouseEvent) {
    if (!event.ctrlKey && !event.metaKey && !event.shiftKey) return
    const target = event.target as HTMLElement
    if (target.closest('button, input, textarea, select, a[href], label, [draggable="true"]')) return
    const rowElement = event.currentTarget as HTMLElement
    if (rowElement.firstElementChild?.contains(target)) return
    if (rows.value[index]?.audioState === "generating") return
    toggleRowSelect(index, event)
  }

  function toggleRowSelect(index: number, event: MouseEvent) {
    const finalized = rows.value[index]?.finalized
    if (event.ctrlKey || event.metaKey) {
      const selection = new Set(selectedIndexes.value)
      if (selection.has(index)) selection.delete(index)
      else if (!finalized) selection.add(index)
      selectedIndexes.value = selection
      lastClickedIndex.value = index
      return
    }

    if (event.shiftKey && lastClickedIndex.value >= 0) {
      const selection = new Set<number>()
      const start = Math.min(lastClickedIndex.value, index)
      const end = Math.max(lastClickedIndex.value, index)
      for (let current = start; current <= end; current++) {
        if (!rows.value[current]?.finalized) selection.add(current)
      }
      for (const selected of selectedIndexes.value) selection.add(selected)
      selectedIndexes.value = selection
      return
    }

    if (finalized) return
    selectedIndexes.value = selectedIndexes.value.size === 1 && selectedIndexes.value.has(index)
      ? new Set()
      : new Set([index])
    lastClickedIndex.value = index
  }

  function startEditText(row: BatchRow, index: number) {
    if (row.finalized) return
    editingTextValue.value = row.text
    editingTextId.value = row.id
    editingIndex.value = index
    nextTick(() => {
      const input = document.querySelector<HTMLInputElement>(`[data-edit-input="${row.id}"]`)
      input?.focus()
      input?.select()
    })
  }

  function confirmEditText() {
    if (editingTextId.value) {
      const row = rows.value.find(item => item.id === editingTextId.value)
      if (row) row.text = editingTextValue.value
    }
    editingTextId.value = null
  }

  function cancelEditText() {
    editingTextId.value = null
  }

  function onRowDragStart(index: number, event: DragEvent) {
    if (generating.value) return
    dragRowIndex.value = index
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move"
      event.dataTransfer.setData("text/plain", "")
    }
  }

  function onRowDragEnterItem(index: number) {
    const from = dragRowIndex.value
    if (from < 0 || from === index) return
    const [row] = rows.value.splice(from, 1)
    rows.value.splice(index, 0, row)
    dragRowIndex.value = index
    adjustIndexesAfterMove(from, index)
  }

  function onRowDragEnd() {
    dragRowIndex.value = -1
  }

  function adjustIndexesAfterMove(from: number, to: number) {
    if (editingIndex.value === from) editingIndex.value = to
    else if (editingIndex.value === to) editingIndex.value = from

    const selection = new Set<number>()
    for (const selected of selectedIndexes.value) {
      if (selected === from) selection.add(to)
      else if (selected === to) selection.add(from)
      else selection.add(selected)
    }
    selectedIndexes.value = selection

    if (lastClickedIndex.value === from) lastClickedIndex.value = to
    else if (lastClickedIndex.value === to) lastClickedIndex.value = from
  }

  function adjustIndexesAfterRemove(index: number) {
    if (editingIndex.value === index) editingIndex.value = -1
    else if (editingIndex.value > index) editingIndex.value--

    const selection = new Set<number>()
    for (const selected of selectedIndexes.value) {
      if (selected < index) selection.add(selected)
      else if (selected > index) selection.add(selected - 1)
    }
    selectedIndexes.value = selection

    if (lastClickedIndex.value === index) lastClickedIndex.value = -1
    else if (lastClickedIndex.value > index) lastClickedIndex.value--
  }

  return {
    editingTextId,
    editingTextValue,
    dragRowIndex,
    onRowClick,
    toggleRowSelect,
    startEditText,
    confirmEditText,
    cancelEditText,
    onRowDragStart,
    onRowDragEnterItem,
    onRowDragEnd,
    adjustIndexesAfterRemove,
  }
}
