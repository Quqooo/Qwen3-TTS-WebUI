<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from "vue"

const props = defineProps<{
  modelValue: string
  rows?: number
  maxRows?: number
  placeholder?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: string): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const MAX_HEIGHT = 616

function minHeight() {
  const el = textareaRef.value
  if (!el) return 0
  const style = window.getComputedStyle(el)
  const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.4
  const paddingTop = parseFloat(style.paddingTop)
  const paddingBottom = parseFloat(style.paddingBottom)
  const borderTop = parseFloat(style.borderTopWidth)
  const borderBottom = parseFloat(style.borderBottomWidth)
  return lineHeight * (props.rows ?? 3) + paddingTop + paddingBottom + borderTop + borderBottom
}

function computeMaxHeight() {
  const el = textareaRef.value
  if (!el || !props.maxRows) return
  const style = window.getComputedStyle(el)
  const lineHeight = parseFloat(style.lineHeight)
  const paddingTop = parseFloat(style.paddingTop)
  const paddingBottom = parseFloat(style.paddingBottom)
  const borderTop = parseFloat(style.borderTopWidth)
  const borderBottom = parseFloat(style.borderBottomWidth)
  const rowHeight = lineHeight || parseFloat(style.fontSize) * 1.4
  const maxH = rowHeight * props.maxRows + paddingTop + paddingBottom + borderTop + borderBottom
  return maxH
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = "auto"
  const natural = el.scrollHeight
  const target = Math.max(natural, minHeight())
  const limit = props.maxRows ? (computeMaxHeight() ?? MAX_HEIGHT) : MAX_HEIGHT
  if (target >= limit) {
    el.style.height = limit + "px"
    el.style.overflowY = "auto"
  } else {
    el.style.height = target + "px"
    el.style.overflowY = "hidden"
  }
}

onMounted(() => {
  autoResize()
})

watch(() => props.modelValue, () => nextTick(autoResize))

function onInput(ev: Event) {
  if (props.readonly) return
  const target = ev.target as HTMLTextAreaElement
  emit("update:modelValue", target.value)
  autoResize()
}
</script>

<template>
  <textarea
    ref="textareaRef"
    :value="modelValue"
    :rows="rows ?? 3"
    :placeholder="placeholder"
    :readonly="readonly"
    class="w-full px-3 py-2 text-sm resize-none overflow-hidden"
    @input="onInput"
  />
</template>
