<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from "vue"
import { useToast } from "../../composables/useToast"

const props = defineProps<{
  modelValue: string
  rows?: number
  placeholder?: string
  noAutosize?: boolean
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: string): void
}>()

const { error: toastError } = useToast()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const isDragOver = ref(false)
let minHeight = 0
const MAX_HEIGHT = 616

const TEXT_EXTS = new Set([
  ".txt", ".srt", ".lrc", ".vtt", ".ass", ".ssa", ".stl", ".imsc",
  ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml",
  ".html", ".htm", ".css", ".js", ".ts", ".py", ".cfg", ".ini",
])

function autoResize() {
  if (props.noAutosize) return
  const el = textareaRef.value
  if (!el) return
  el.style.height = "auto"
  const natural = el.scrollHeight
  const target = Math.max(natural, minHeight)
  if (target >= MAX_HEIGHT) {
    el.style.height = MAX_HEIGHT + "px"
    el.style.overflowY = "auto"
  } else {
    el.style.height = target + "px"
    el.style.overflowY = "hidden"
  }
}

onMounted(() => {
  if (!props.noAutosize) {
    const el = textareaRef.value
    if (el) {
      el.style.height = "auto"
      minHeight = el.scrollHeight
      autoResize()
    }
  }
})

watch(() => props.modelValue, () => nextTick(autoResize))

function onInput(ev: Event) {
  const target = ev.target as HTMLTextAreaElement
  emit("update:modelValue", target.value)
  autoResize()
}

function isTextFile(file: File): boolean {
  if (file.type.startsWith("text/")) return true
  const ext = "." + file.name.split(".").pop()?.toLowerCase()
  return TEXT_EXTS.has(ext)
}

function onDragOver(ev: DragEvent) {
  if (ev.dataTransfer?.types.includes("Files")) {
    ev.dataTransfer!.dropEffect = "copy"
    isDragOver.value = true
  }
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(ev: DragEvent) {
  isDragOver.value = false
  const file = ev.dataTransfer?.files?.[0]
  if (!file) return
  if (!isTextFile(file)) {
    toastError(`Unsupported file type: ${file.name}`)
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    emit("update:modelValue", props.modelValue + (reader.result as string))
  }
  reader.onerror = () => toastError(`Failed to read file: ${file.name}`)
  reader.readAsText(file)
}
</script>

<template>
  <div
    class="relative"
    :class="noAutosize ? 'flex flex-1 flex-col min-h-0' : ''"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <textarea
      ref="textareaRef"
      :value="modelValue"
      :rows="rows ?? 3"
      :placeholder="placeholder"
      class="w-full px-3 py-2 text-sm border rounded-lg resize-none transition-colors duration-150 focus:border-primary focus:ring-0"
      :class="[noAutosize ? 'flex-1 min-h-0' : '', isDragOver ? 'drag-over' : '']"
      @dragover.prevent="onDragOver"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
      @input="onInput"
    />
  </div>
</template>

<style scoped>
.drag-over {
  border-color: hsl(var(--primary)) !important;
  background-color: hsl(var(--primary) / 0.05);
}
</style>
