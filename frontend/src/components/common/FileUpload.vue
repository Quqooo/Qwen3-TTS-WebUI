<script setup lang="ts">
import { ref } from "vue"
import { Upload } from "@lucide/vue"

const props = defineProps<{
  accept?: string
  label?: string
}>()

const emit = defineEmits<{
  (e: "file", file: File): void
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const isDragOver = ref(false)

function onDrop(ev: DragEvent) {
  isDragOver.value = false
  const file = ev.dataTransfer?.files[0]
  if (file) emit("file", file)
}

function onInput(ev: Event) {
  const target = ev.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) emit("file", file)
  target.value = ""
}

function onClick() {
  inputRef.value?.click()
}
</script>

<template>
  <div
    class="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors hover:border-primary/50"
    :class="isDragOver ? 'border-primary bg-primary/5' : 'border-border'"
    @drop.prevent="onDrop"
    @dragover.prevent="isDragOver = true"
    @dragleave="isDragOver = false"
    @click="onClick"
  >
    <input ref="inputRef" type="file" :accept="accept" class="hidden" @input="onInput" />
    <div class="flex flex-col items-center gap-2">
      <Upload class="w-6 h-6 text-muted-foreground" />
      <p class="text-sm text-muted-foreground">{{ label ?? $t('components.fileUpload.defaultLabel') }}</p>
    </div>
  </div>
</template>
