<script setup lang="ts">
defineProps<{
  open: boolean
  title: string
  message: string
}>()

const emit = defineEmits<{
  (e: "confirm"): void
  (e: "cancel"): void
}>()
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="fixed inset-0 bg-black/30" @click="emit('cancel')" />
        <div class="dialog-content relative bg-card border rounded-xl shadow-lg p-6 w-full max-w-sm mx-4">
          <h3 class="text-base font-semibold mb-2">{{ title }}</h3>
          <p class="text-sm text-muted-foreground mb-4">{{ message }}</p>
          <div class="flex justify-end gap-2">
            <button
              class="px-3 py-1.5 text-sm rounded-lg border hover:bg-accent transition-colors"
              @click="emit('cancel')"
            >
              {{ $t('components.confirmDialog.cancel') }}
            </button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-destructive text-destructive-foreground hover:opacity-90 transition-opacity"
              @click="emit('confirm')"
            >
              {{ $t('components.confirmDialog.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
