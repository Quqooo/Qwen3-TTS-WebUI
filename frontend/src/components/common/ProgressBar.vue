<script setup lang="ts">
defineProps<{
  value: number
  max?: number
  label?: string
}>()
</script>

<template>
  <div class="space-y-1">
    <div v-if="label" class="flex justify-between text-xs text-muted-foreground">
      <span>{{ label }}</span>
      <span>{{ Math.round((value / (max ?? 100)) * 100) }}%</span>
    </div>
    <div class="h-2 bg-secondary rounded-full overflow-hidden">
      <div
        class="h-full bg-primary rounded-full transition-all duration-300"
        :style="{ width: `${(value / (max ?? 100)) * 100}%` }"
      />
    </div>
  </div>
</template>
