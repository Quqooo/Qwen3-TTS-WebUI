<script setup lang="ts">
import { reactive, watch, onBeforeUnmount } from "vue"
import { useToast } from "../../composables/useToast"
import { CheckCircle2, XCircle, AlertTriangle, Info, ChevronDown, X } from "@lucide/vue"

const { toasts, dismiss } = useToast()

const expanded = reactive<Record<number, boolean>>({})
const progressPct = reactive<Record<number, number>>({})

interface TimerState {
  startTime: number
  duration: number
  paused: boolean
  pausedAt: number
  totalPauseTime: number
}

const timerStates = new Map<number, TimerState>()
let globalRaf = 0

function globalTick() {
  globalRaf = requestAnimationFrame(globalTick)
  const now = performance.now()

  for (const t of toasts.value) {
    const state = timerStates.get(t.id)
    if (!state || state.paused) continue

    const elapsed = (now - state.startTime) - state.totalPauseTime
    const pct = Math.max(0, 100 * (1 - elapsed / state.duration))
    progressPct[t.id] = pct

    if (pct <= 0) {
      dismiss(t.id)
      timerStates.delete(t.id)
      delete progressPct[t.id]
      delete expanded[t.id]
    }
  }

  if (toasts.value.length === 0) {
    cancelAnimationFrame(globalRaf)
    globalRaf = 0
  }
}

function pauseTimer(id: number) {
  const state = timerStates.get(id)
  if (!state || state.paused) return
  state.paused = true
  state.pausedAt = performance.now()
}

function resumeTimer(id: number) {
  const state = timerStates.get(id)
  if (!state || !state.paused) return
  state.totalPauseTime += performance.now() - state.pausedAt
  state.paused = false
}

function toggleExpand(id: number) {
  expanded[id] = !expanded[id]
}

watch(
  () => toasts.value.map(t => t.id).join(","),
  () => {
    const activeIds = new Set(toasts.value.map(t => t.id))
    for (const t of toasts.value) {
      if (!timerStates.has(t.id)) {
        timerStates.set(t.id, {
          startTime: performance.now(),
          duration: t.duration,
          paused: false,
          pausedAt: 0,
          totalPauseTime: 0,
        })
        progressPct[t.id] = 100
      }
    }
    for (const [id] of timerStates) {
      if (!activeIds.has(id)) {
        timerStates.delete(id)
        delete progressPct[id]
        delete expanded[id]
      }
    }
    if (toasts.value.length > 0 && !globalRaf) {
      globalTick()
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (globalRaf) {
    cancelAnimationFrame(globalRaf)
    globalRaf = 0
  }
  timerStates.clear()
})

const icons: Record<string, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

const typeIconColors: Record<string, string> = {
  success: "text-emerald-500",
  error: "text-red-500",
  warning: "text-amber-500",
  info: "text-sky-500",
}

const progressColors: Record<string, string> = {
  success: "bg-emerald-500",
  error: "bg-red-500",
  warning: "bg-amber-500",
  info: "bg-sky-500",
}
</script>

<template>
  <div class="fixed top-4 left-1/2 -translate-x-1/2 z-[9999] flex flex-col items-center gap-2 pointer-events-none max-w-[40vw]">
    <TransitionGroup name="toast">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast-item pointer-events-auto overflow-hidden rounded-lg shadow-lg bg-card"
        @mouseenter="pauseTimer(t.id)"
        @mouseleave="resumeTimer(t.id)"
      >
        <div class="relative h-[3px] bg-muted/30">
          <div
            class="absolute top-0 left-0 h-full transition-none"
            :class="progressColors[t.type]"
            :style="{ width: (progressPct[t.id] ?? 100) + '%' }"
          />
        </div>

        <div class="flex items-center gap-2.5 px-3 py-2.5">
          <component
            :is="icons[t.type]"
            class="w-4 h-4 shrink-0"
            :class="typeIconColors[t.type]"
          />
          <span class="flex-1 min-w-0 text-sm truncate text-center">{{ t.message }}</span>
          <button
            v-if="t.debug"
            class="shrink-0 p-0.5 rounded opacity-50 hover:opacity-100 transition"
            @click.stop="toggleExpand(t.id)"
          >
            <ChevronDown
              class="w-3.5 h-3.5 transition-transform duration-200"
              :class="{ 'rotate-180': expanded[t.id] }"
            />
          </button>
          <button
            class="shrink-0 p-0.5 rounded opacity-50 hover:opacity-100 transition"
            @click.stop="dismiss(t.id)"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>

        <Transition name="expand">
          <div v-if="expanded[t.id] && t.debug" class="overflow-hidden w-0 min-w-full">
            <div class="px-3 pb-3 text-xs text-muted-foreground border-t border-border pt-2 max-h-[6.1rem] overflow-y-auto whitespace-pre-wrap break-all font-mono leading-relaxed">
              {{ t.debug }}
            </div>
          </div>
        </Transition>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active {
  animation: toast-in 0.35s cubic-bezier(0.21, 1.02, 0.73, 1) forwards;
}
.toast-leave-active {
  animation: toast-out 0.25s ease-in forwards;
}
.toast-move {
  transition: transform 0.3s ease;
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateY(-16px) scale(0.92);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes toast-out {
  from {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
  to {
    opacity: 0;
    transform: translateY(-12px) scale(0.9);
  }
}

.expand-enter-active {
  transition: max-height 0.3s ease, opacity 0.3s ease;
}
.expand-leave-active {
  transition: max-height 0.25s ease, opacity 0.25s ease;
}
.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
}
.expand-enter-to,
.expand-leave-from {
  max-height: 10rem;
  opacity: 1;
}
</style>
