<script setup lang="ts">
import { computed, ref } from "vue"
import { useModelStore } from "../../stores/model"
import { Cpu, Wifi, Sun, Moon } from "@lucide/vue"
import { useTheme } from "../../composables/useTheme"
import AppSelect from "../common/AppSelect.vue"

const { isDark, toggleTheme } = useTheme()
import { getLocale, setLocale, getAvailableLocales, localeLabels } from "../../lang"
import { t } from "../../lang"

const modelStore = useModelStore()

const cacheSummary = computed(() => {
  const loaded = modelStore.cacheStatus.loaded
  if (loaded.length === 0) return null
  const first = loaded[0].id
  if (loaded.length === 1) return first
  return `${first} (+${loaded.length - 1})`
})

const cacheTooltip = computed(() => {
  const loaded = modelStore.cacheStatus.loaded
  if (loaded.length === 0) return ""
  return loaded.map((m) => `${m.id}  (${m.kind})`).join("\n")
})

const workerState = computed(() => {
  if (!modelStore.wsConnected) return { label: t('layout.disconnected'), class: 'text-muted-foreground' }
  const ws = modelStore.workerStatus
  if (ws.error) return { label: t('layout.workerError') ?? ws.error, class: 'text-red-500' }
  if (!ws.alive) return { label: t('layout.notStarted'), class: 'text-yellow-500' }
  return { label: t('layout.ready'), class: 'text-green-600' }
})

const currentLocale = ref(getLocale())
const availableLocales = computed(() =>
  getAvailableLocales().map(code => ({
    value: code,
    label: localeLabels[code] || code,
  }))
)
</script>

<template>
  <header class="h-12 border-b bg-background flex items-center justify-between px-4 shrink-0">
    <div
      class="flex items-center gap-1.5 text-xs text-muted-foreground"
      v-tooltip="cacheTooltip"
      :class="cacheSummary ? 'cursor-help' : ''"
    >
      <Cpu class="w-3.5 h-3.5" />
      <span v-if="cacheSummary">{{ cacheSummary }}</span>
      <span v-else class="italic">{{ $t('layout.noModelLoaded') }}</span>
    </div>
    <div class="flex items-center gap-4">
      <button
        class="w-6 h-6 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        @click="toggleTheme($event)"
        v-tooltip="isDark ? $t('layout.switchToLight') : $t('layout.switchToDark')"
      >
        <Sun v-if="isDark" class="w-3.5 h-3.5" />
        <Moon v-else class="w-3.5 h-3.5" />
      </button>
      <AppSelect
        compact
        :model-value="currentLocale"
        :options="availableLocales"
        @update:model-value="(val: string) => { setLocale(val); currentLocale = val }"
      />
      <div class="flex items-center gap-1 text-xs" :class="workerState.class">
        <Wifi class="w-3 h-3" />
        <span>{{ workerState.label }}</span>
      </div>
    </div>
  </header>
</template>
