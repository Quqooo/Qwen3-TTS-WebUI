<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted, onUnmounted } from "vue"
import type { Component } from "vue"

export type Segment = {
  value: string
  label: string
  icon: Component
}

const props = withDefaults(defineProps<{
  modelValue: string
  title?: string
  segments?: Segment[]
  canDeselect?: boolean
  showDivider?: boolean
  nested?: boolean
}>(), {
  canDeselect: true,
  showDivider: false,
})

const emit = defineEmits<{
  (e: "update:modelValue", val: string): void
}>()

const wrapper = ref<HTMLDivElement | null>(null)
const inner = ref<HTMLDivElement | null>(null)

const resolvedSegments = computed<Segment[]>(() => {
  return props.segments ?? []
})

function syncHeight() {
  const el = wrapper.value
  const content = inner.value
  if (!el || !content) return
  el.style.height = content.scrollHeight + "px"
}

watch(() => props.modelValue, () => {
  // 片段切换后强制校准高度。ResizeObserver 仅在尺寸变化时触发，
  // 若切换前后片段高度相同或测量时机不同可能错过，故手动同步一次。
  nextTick(syncHeight)
}, { immediate: true })

watch(resolvedSegments, (segs) => {
  if (props.canDeselect === false && segs.length > 0) {
    const valid = segs.some((s) => s.value === props.modelValue)
    if (!valid) emit("update:modelValue", segs[0].value)
  }
}, { immediate: true })

onMounted(() => {
  const content = inner.value
  if (!content) return
  const ro = new ResizeObserver(syncHeight)
  ro.observe(content)
  onUnmounted(() => ro.disconnect())
})

function select(val: string) {
  emit("update:modelValue", val === props.modelValue && props.canDeselect ? "" : val)
}
</script>

<template>
  <div :class="nested ? '' : 'border rounded-xl bg-card'">
    <div v-if="title" :class="nested ? 'mb-1' : 'px-4 pt-3 pb-1'">
      <label class="label">{{ title }}</label>
    </div>
    <div
      :class="nested ? 'flex gap-1 py-1 mb-3 bg-muted/50 rounded-lg' : title ? 'flex p-1 gap-1 mx-3 mb-3 bg-muted/50 rounded-lg' : 'flex p-1 gap-1'"
    >
      <template v-for="(seg, idx) in resolvedSegments" :key="seg.value">
        <div
          v-if="idx > 0 && showDivider"
          class="w-px bg-border self-center h-4"
        />
        <button
          class="btn-segment"
          :class="modelValue === seg.value
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
          @click="select(seg.value)"
        >
          <component :is="seg.icon" class="w-3.5 h-3.5" />
          {{ seg.label }}
        </button>
      </template>
    </div>

    <div
      ref="wrapper"
      class="transition-[height] duration-200 ease-out"
    >
      <div ref="inner">
        <template v-for="seg in resolvedSegments" :key="seg.value">
          <div
            v-show="modelValue === seg.value"
            :class="nested ? 'space-y-1' : 'border-t px-2 pb-3 pt-2.5 mx-1.5 space-y-2'"
          >
            <slot :name="seg.value" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
