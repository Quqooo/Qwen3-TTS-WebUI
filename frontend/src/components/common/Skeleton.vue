<template>
  <div class="animate-pulse rounded bg-muted/50" :class="cn" />
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{
  class?: string
}>()

const cn = computed(() => props.class)
</script>
