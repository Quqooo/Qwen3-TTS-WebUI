<script setup lang="ts">
import { ref, watch } from "vue"

const props = defineProps<{
  modelValue: number
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: number): void
}>()

const rawH = ref(0)
const rawM = ref(0)
const rawS = ref(0)
const rawMs = ref(0)
const focusedSegment = ref<string | null>(null)
const inputH = ref<HTMLInputElement | null>(null)
const inputM = ref<HTMLInputElement | null>(null)
const inputS = ref<HTMLInputElement | null>(null)
const inputMs = ref<HTMLInputElement | null>(null)
let syncing = false

inputH // template ref

function syncFromModel() {
  if (syncing) return
  syncing = true
  const val = props.modelValue
  rawH.value = Math.floor(val / 3600)
  rawM.value = Math.floor((val % 3600) / 60)
  rawS.value = Math.floor(val % 60)
  rawMs.value = Math.round((val - Math.floor(val)) * 1000)
  syncing = false
}

syncFromModel()

watch(() => props.modelValue, syncFromModel)

function rebuild() {
  syncing = true
  emit("update:modelValue", rawH.value * 3600 + rawM.value * 60 + rawS.value + rawMs.value / 1000)
  syncing = false
}

function onSegmentInput(segment: "h" | "m" | "s" | "ms", raw: string) {
  const val = parseInt(raw, 10)
  if (isNaN(val)) return
  if (segment === "h") rawH.value = val
  else if (segment === "m") rawM.value = val
  else if (segment === "s") rawS.value = val
  else rawMs.value = val
}

function onBlur(segment: "h" | "m" | "s" | "ms") {
  focusedSegment.value = null
  const refMap = { h: rawH, m: rawM, s: rawS, ms: rawMs } as const
  const current = refMap[segment].value
  const clamped = segment === "ms" ? Math.min(999, Math.max(0, current))
    : segment === "h" ? Math.max(0, current)
    : Math.min(59, Math.max(0, current))
  if (clamped !== current) refMap[segment].value = clamped
  rebuild()
}

function inputValue(ev: Event): string {
  return (ev.target as HTMLInputElement).value
}

function onKeyEnter(segment: "h" | "m" | "s" | "ms") {
  const next: Record<string, HTMLInputElement | null> = { h: inputM.value, m: inputS.value, s: inputMs.value, ms: null }
  next[segment]?.focus()
}

function onWheel(segment: "h" | "m" | "s" | "ms", ev: WheelEvent) {
  if (props.disabled) return
  ev.preventDefault()
  ev.stopPropagation()
  if (ev.deltaY === 0) return
  const delta = ev.deltaY > 0 ? -1 : 1
  const refMap = { h: rawH, m: rawM, s: rawS, ms: rawMs } as const
  const current = refMap[segment].value
  const next = current + delta
  const clamped = segment === "ms" ? Math.min(999, Math.max(0, next))
    : segment === "h" ? Math.max(0, next)
    : Math.min(59, Math.max(0, next))
  refMap[segment].value = clamped
  rebuild()
}
</script>

<template>
  <span class="inline-flex items-center gap-0.5 font-mono text-xs tabular-nums" :class="disabled ? 'opacity-50 pointer-events-none' : ''">
    <input
      ref="inputH"
      :value="focusedSegment === 'h' ? String(rawH) : String(rawH).padStart(2, '0')"
      class="w-5 text-center bg-transparent border-0 outline-none p-0 hover:bg-accent/30 focus:bg-accent/30 rounded"
      maxlength="2"
      @focus="focusedSegment = 'h'"
      @input="onSegmentInput('h', inputValue($event))"
      @blur="onBlur('h')"
      @keydown.enter="onKeyEnter('h')"
      @wheel="onWheel('h', $event)"
    />
    <span class="text-muted-foreground">:</span>
    <input
      ref="inputM"
      :value="focusedSegment === 'm' ? String(rawM) : String(rawM).padStart(2, '0')"
      class="w-5 text-center bg-transparent border-0 outline-none p-0 hover:bg-accent/30 focus:bg-accent/30 rounded"
      maxlength="2"
      @focus="focusedSegment = 'm'"
      @input="onSegmentInput('m', inputValue($event))"
      @blur="onBlur('m')"
      @keydown.enter="onKeyEnter('m')"
      @wheel="onWheel('m', $event)"
    />
    <span class="text-muted-foreground">:</span>
    <input
      ref="inputS"
      :value="focusedSegment === 's' ? String(rawS) : String(rawS).padStart(2, '0')"
      class="w-5 text-center bg-transparent border-0 outline-none p-0 hover:bg-accent/30 focus:bg-accent/30 rounded"
      maxlength="2"
      @focus="focusedSegment = 's'"
      @input="onSegmentInput('s', inputValue($event))"
      @blur="onBlur('s')"
      @keydown.enter="onKeyEnter('s')"
      @wheel="onWheel('s', $event)"
    />
    <span class="text-muted-foreground">.</span>
    <input
      ref="inputMs"
      :value="focusedSegment === 'ms' ? String(rawMs) : String(rawMs).padStart(3, '0')"
      class="w-6 text-center bg-transparent border-0 outline-none p-0 hover:bg-accent/30 focus:bg-accent/30 rounded"
      maxlength="3"
      @focus="focusedSegment = 'ms'"
      @input="onSegmentInput('ms', inputValue($event))"
      @blur="onBlur('ms')"
      @keydown.enter="onKeyEnter('ms')"
      @wheel="onWheel('ms', $event)"
    />
  </span>
</template>
