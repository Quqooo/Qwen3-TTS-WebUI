<script setup lang="ts">
import { computed } from "vue"
import { t } from "../../lang"

const props = withDefaults(defineProps<{
  modelValue: boolean
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
}>()

const stateLabel = computed(() =>
  props.modelValue
    ? t("components.appSwitch.on")
    : t("components.appSwitch.off"),
)

function toggle() {
  if (props.disabled) return
  emit("update:modelValue", !props.modelValue)
}
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    class="w-full flex items-center justify-between gap-2 border rounded-lg bg-background px-3 py-2 text-sm transition-all duration-150"
    :class="[
      disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
      modelValue ? 'border-primary/40 ring-1 ring-primary/10' : 'border-border hover:border-primary/50',
    ]"
    @click="toggle"
  >
    <span class="truncate">{{ stateLabel }}</span>
    <span
      class="relative inline-flex h-4 w-7 shrink-0 rounded-full transition-colors duration-200"
      :class="modelValue ? 'bg-primary' : 'bg-secondary'"
    >
      <span
        class="absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform duration-200"
        :class="modelValue ? 'translate-x-3' : 'translate-x-0'"
      />
    </span>
  </button>
</template>
