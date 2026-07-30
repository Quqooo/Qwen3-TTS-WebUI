<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from "vue"
import { onClickOutside } from "@vueuse/core"
import { t } from "../../lang"

const props = defineProps<{
  modelValue: string
  options: { value: string; label: string }[]
  placeholder?: string
  disabled?: boolean
  filterable?: boolean
  compact?: boolean
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: string): void
}>()

const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const filterInput = ref("")
const highlightIndex = ref(0)

onClickOutside(triggerRef, () => { open.value = false }, { ignore: [dropdownRef] })

const dropdownStyle = ref<Record<string, string>>({})

function updateDropdownPosition() {
  const trigger = triggerRef.value
  if (!trigger) return

  const rect = trigger.getBoundingClientRect()
  const gap = 4
  const maxHeight = 240
  const spaceBelow = window.innerHeight - rect.bottom - gap
  const spaceAbove = rect.top - gap
  const openAbove = spaceBelow < 160 && spaceAbove > spaceBelow
  const availableHeight = Math.max(80, Math.min(maxHeight, openAbove ? spaceAbove : spaceBelow))

  dropdownStyle.value = {
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    maxHeight: `${availableHeight}px`,
    ...(openAbove
      ? { bottom: `${window.innerHeight - rect.top + gap}px` }
      : { top: `${rect.bottom + gap}px` }),
  }
}

function onViewportChange() {
  if (open.value) updateDropdownPosition()
}

watch(open, async (isOpen) => {
  if (isOpen) {
    await nextTick()
    updateDropdownPosition()
    window.addEventListener("resize", onViewportChange)
    window.addEventListener("scroll", onViewportChange, true)
  } else {
    window.removeEventListener("resize", onViewportChange)
    window.removeEventListener("scroll", onViewportChange, true)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", onViewportChange)
  window.removeEventListener("scroll", onViewportChange, true)
})

const selectedOption = computed(() =>
  props.options.find((o) => o.value === props.modelValue),
)

const selectedLabel = computed(() => {
  if (selectedOption.value) return selectedOption.value.label
  if (props.modelValue) return props.modelValue
  return props.placeholder ?? t('components.appSelect.placeholder')
})

const filteredOptions = computed(() => {
  const q = filterInput.value.toLowerCase()
  if (!q) return props.options
  return props.options.filter((o) =>
    o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
  )
})

watch(filterInput, () => {
  if (filterInput.value) highlightIndex.value = 0
})

function openDropdown() {
  if (props.disabled) return
  open.value = true
  filterInput.value = ""
  const idx = filteredOptions.value.findIndex((o) => o.value === props.modelValue)
  highlightIndex.value = idx >= 0 ? idx : 0
  setTimeout(() => {
    const input = triggerRef.value?.querySelector<HTMLInputElement>(".app-select-input")
    input?.focus()
    if (dropdownRef.value) {
      const item = dropdownRef.value.querySelector(`[data-idx="${highlightIndex.value}"]`) as HTMLElement | null
      item?.scrollIntoView({ block: "nearest" })
    }
  }, 50)
}

function select(val: string) {
  emit("update:modelValue", val)
  open.value = false
  filterInput.value = ""
}

function delayedClose() {
  setTimeout(() => { open.value = false }, 150)
}

function onKeydown(ev: KeyboardEvent) {
  if (ev.key === "ArrowDown") {
    ev.preventDefault()
    highlightIndex.value = Math.min(highlightIndex.value + 1, filteredOptions.value.length - 1)
  } else if (ev.key === "ArrowUp") {
    ev.preventDefault()
    highlightIndex.value = Math.max(highlightIndex.value - 1, 0)
  } else if (ev.key === "Enter") {
    ev.preventDefault()
    const target = filteredOptions.value[highlightIndex.value]
    if (target) select(target.value)
  } else if (ev.key === "Escape") {
    open.value = false
  }
}

const ESC_MAP: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }
function escHtml(s: string) { return s.replace(/[&<>"']/g, c => ESC_MAP[c]) }

function highlightedHtml(label: string): string {
  const q = filterInput.value.trim()
  const escapedLabel = escHtml(label)
  if (!q) return escapedLabel
  const escapedQ = escHtml(q)
  const idx = escapedLabel.toLowerCase().indexOf(escapedQ.toLowerCase())
  if (idx === -1) return escapedLabel
  const before = escapedLabel.slice(0, idx)
  const match = escapedLabel.slice(idx, idx + escapedQ.length)
  const after = escapedLabel.slice(idx + escapedQ.length)
  return `${before}<mark class="bg-transparent text-primary font-medium">${match}</mark>${after}`
}
</script>

<template>
  <div ref="triggerRef" class="relative">
    <button
      v-if="!filterable || !open"
      class="w-full flex items-center justify-between border rounded-lg bg-background transition-all duration-150"
      :class="[
        compact ? 'gap-1 px-2 py-1 text-xs' : 'gap-2 px-3 py-2 text-sm',
        disabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-primary/50 cursor-pointer',
        open ? 'border-primary ring-1 ring-primary/20' : 'border-border',
        !disabled && 'cursor-pointer'
      ]"
      @click="openDropdown"
    >
      <span class="truncate" :class="!selectedOption ? 'text-muted-foreground' : ''">
        {{ selectedLabel }}
      </span>
      <svg
        class="text-muted-foreground shrink-0 transition-transform duration-200"
        :class="[compact ? 'w-3 h-3' : 'w-3.5 h-3.5', open ? 'rotate-180' : '']"
        fill="none" viewBox="0 0 24 24" stroke="currentColor"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <div v-else class="relative">
      <input
        v-model="filterInput"
        type="text"
        class="app-select-input w-full border rounded-lg bg-background transition-all duration-150 border-primary ring-1 ring-primary/20"
        :class="compact ? 'px-2 py-1 pr-7 text-xs' : 'px-3 py-2 pr-8 text-sm'"
        :placeholder="selectedLabel"
        @keydown="onKeydown"
        @blur="delayedClose"
      />
      <svg
        class="absolute top-1/2 -translate-y-1/2 text-muted-foreground"
        :class="compact ? 'right-2 w-3 h-3' : 'right-2.5 w-3.5 h-3.5'"
        fill="none" viewBox="0 0 24 24" stroke="currentColor"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </div>

    <Teleport to="body">
      <Transition
        enter-active-class="transition-all duration-150 ease-out"
        enter-from-class="opacity-0 scale-95 -translate-y-1"
        enter-to-class="opacity-100 scale-100 translate-y-0"
        leave-active-class="transition-all duration-100 ease-in"
        leave-from-class="opacity-100 scale-100 translate-y-0"
        leave-to-class="opacity-0 scale-95 -translate-y-1"
      >
        <div
          v-if="open"
          ref="dropdownRef"
          class="fixed z-[100] border rounded-lg bg-card shadow-lg overflow-y-auto"
          :style="dropdownStyle"
        >
          <div v-if="filteredOptions.length === 0" class="text-muted-foreground text-center" :class="compact ? 'px-2 py-3 text-xs' : 'px-3 py-4 text-xs'">
            {{ $t('components.appSelect.noMatch') }}
          </div>
          <div
            v-for="(opt, idx) in filteredOptions"
            :key="opt.value"
            :data-idx="idx"
            class="cursor-pointer transition-colors duration-75"
            :class="[
              compact ? 'px-2 py-1.5 text-xs' : 'px-3 py-2 text-sm',
              idx === highlightIndex && !filterInput ? 'bg-primary/10 text-primary' : 'hover:bg-accent text-foreground',
              opt.value === modelValue && idx !== highlightIndex && !filterInput ? 'font-medium' : ''
            ]"
            @mouseenter="highlightIndex = idx"
            @mousedown.prevent="select(opt.value)"
            v-html="highlightedHtml(opt.label)"
          />
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
