<script setup lang="ts">
import AutoTextarea from "./AutoTextarea.vue"

defineProps<{
  message: string
}>()
</script>

<template>
  <div class="border rounded-xl p-4 space-y-2 bg-card">
    <label class="label">{{ $t('components.statusOutput.label') }}</label>
    <AutoTextarea
      :model-value="message"
      :placeholder="$t('components.statusOutput.placeholder')"
      :rows="4"
      :max-rows="10"
      readonly
    />
  </div>
</template>
