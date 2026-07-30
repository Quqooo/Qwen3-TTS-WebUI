<script setup lang="ts">
import DropTextarea from "../common/DropTextarea.vue"

defineProps<{
  i18nPrefix: string
  modelValue: string
}>()

defineEmits<{
  "update:modelValue": [val: string]
}>()
</script>

<template>
  <div class="card flex flex-1 flex-col min-h-0">
    <label class="label mb-2 block shrink-0">{{ $t(`${i18nPrefix}.inputText`) }}</label>
    <DropTextarea
      :model-value="modelValue"
      noAutosize
      :placeholder="$t(`${i18nPrefix}.inputTextPlaceholder`)"
      @update:model-value="$emit('update:modelValue', $event)"
    />
  </div>
</template>
