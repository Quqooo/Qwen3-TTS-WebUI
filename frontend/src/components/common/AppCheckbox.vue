<script setup lang="ts">
defineProps<{
  modelValue: boolean
  label?: string
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
}>()
</script>

<template>
  <label class="inline-flex items-center gap-2 cursor-pointer select-none group" @click="emit('update:modelValue', !modelValue)">
    <span
      class="w-4 h-4 rounded border-2 flex items-center justify-center transition-all duration-150 shrink-0"
      :class="[
        modelValue
          ? 'bg-primary border-primary'
          : 'border-muted-foreground/30 group-hover:border-primary/50'
      ]"
    >
      <svg class="w-3 h-3 text-primary-foreground transition-opacity duration-150" :class="modelValue ? 'opacity-100' : 'opacity-0'" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
      </svg>
    </span>
    <span v-if="label" class="text-sm">{{ label }}</span>
  </label>
</template>
