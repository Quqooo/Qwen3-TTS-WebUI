<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import { MicVocal, Speech, Palette, ListChecks, HardDrive, Settings } from "@lucide/vue"
import { t } from "../../lang"

const route = useRoute()
const router = useRouter()

const navItems = computed(() => [
  { path: "/base", label: t('nav.base'), icon: MicVocal },
  { path: "/custom-voice", label: t('nav.customVoice'), icon: Speech },
  { path: "/voice-design", label: t('nav.voiceDesign'), icon: Palette },
  { path: "/batch", label: t('nav.batch'), icon: ListChecks },
  { path: "/voices", label: t('nav.voices'), icon: HardDrive },
  { path: "/settings", label: t('nav.settings'), icon: Settings },
])
</script>

<template>
  <aside class="w-56 border-r bg-card flex flex-col shrink-0">
    <div class="p-4 border-b">
      <h1 class="text-sm font-bold text-foreground">{{ $t('layout.title') }}</h1>
      <p class="text-xs text-muted-foreground mt-0.5">{{ $t('layout.subtitle') }}</p>
    </div>
    <nav class="flex-1 p-2 space-y-1">
      <button
        v-for="item in navItems"
        :key="item.path"
        @click="router.push(item.path)"
        class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
        :class="
          route.path.startsWith(item.path)
            ? 'bg-primary/10 text-primary font-medium'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        "
      >
        <component :is="item.icon" class="w-4 h-4 shrink-0" />
        {{ item.label }}
      </button>
    </nav>
  </aside>
</template>
