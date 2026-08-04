<script setup lang="ts">
import { ref, computed } from "vue"

const props = withDefaults(defineProps<{
  modelValue: number
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  format?: (value: number) => string
}>(), {
  min: 0,
  max: 100,
  step: 1,
  disabled: false,
})

const emit = defineEmits<{
  (e: "update:modelValue", val: number): void
}>()

const trackRef = ref<HTMLElement | null>(null)
const interacting = ref(false)
const dragging = ref(false)

const percent = computed(() => {
  const range = props.max - props.min
  if (range <= 0) return 0
  return ((props.modelValue - props.min) / range) * 100
})

const displayText = computed(() =>
  props.format ? props.format(props.modelValue) : String(props.modelValue),
)

function valueFromClientX(clientX: number): number {
  const track = trackRef.value
  if (!track) return props.modelValue
  const rect = track.getBoundingClientRect()
  if (rect.width <= 0) return props.modelValue
  const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
  const raw = props.min + ratio * (props.max - props.min)
  const stepped = Math.round((raw - props.min) / props.step) * props.step + props.min
  return Math.min(props.max, Math.max(props.min, stepped))
}

function onPointerDown(event: PointerEvent) {
  if (props.disabled) return
  interacting.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
  emit("update:modelValue", valueFromClientX(event.clientX))
}

function onPointerMove(event: PointerEvent) {
  if (!interacting.value || props.disabled) return
  dragging.value = true
  emit("update:modelValue", valueFromClientX(event.clientX))
}

function onPointerUp() {
  interacting.value = false
  dragging.value = false
}

function onKeyDown(event: KeyboardEvent) {
  if (props.disabled) return
  const delta = event.key === "ArrowLeft" ? -props.step : event.key === "ArrowRight" ? props.step : 0
  if (delta === 0) return
  event.preventDefault()
  emit("update:modelValue", Math.min(props.max, Math.max(props.min, props.modelValue + delta)))
}
</script>

<template>
  <div
    ref="trackRef"
    role="slider"
    tabindex="0"
    :aria-valuemin="min"
    :aria-valuemax="max"
    :aria-valuenow="modelValue"
    class="relative h-7 rounded-sm bg-secondary overflow-hidden cursor-pointer select-none touch-none outline-none"
    :class="disabled ? 'opacity-50 cursor-not-allowed' : 'focus-visible:ring-2 focus-visible:ring-primary/30'"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @keydown="onKeyDown"
  >
    <div
      class="absolute inset-y-0 left-0 bg-primary"
      :class="dragging ? '' : 'transition-[width] duration-200 ease-out'"
      :style="{ width: percent + '%' }"
    />
    <div class="relative flex items-center h-full px-2 select-none">
      <span class="text-xs font-mono tabular-nums text-muted-foreground">{{ displayText }}</span>
      <span
        class="absolute inset-y-0 left-0 z-10 flex items-center overflow-hidden pointer-events-none"
        :class="dragging ? '' : 'transition-[width] duration-200 ease-out'"
        :style="{ width: percent + '%' }"
      >
        <span class="px-2 text-xs font-mono tabular-nums text-white">{{ displayText }}</span>
      </span>
    </div>
  </div>
</template>
