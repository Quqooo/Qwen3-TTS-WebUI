<script setup lang="ts">
import { onMounted } from "vue"
import { useModelStore } from "./stores/model"
import AppSidebar from "./components/layout/AppSidebar.vue"
import AppHeader from "./components/layout/AppHeader.vue"
import AppFooter from "./components/layout/AppFooter.vue"
import ToastNotification from "./components/common/ToastNotification.vue"

const modelStore = useModelStore()
onMounted(() => { modelStore.startCacheWatcher() })
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <AppHeader />
    <div class="flex flex-1 overflow-hidden">
      <AppSidebar />
      <main class="flex-1 overflow-hidden p-6">
        <router-view v-slot="{ Component }">
          <KeepAlive>
            <component :is="Component" class="page-enter" />
          </KeepAlive>
        </router-view>
      </main>
    </div>
    <AppFooter />
    <ToastNotification />
  </div>
</template>
