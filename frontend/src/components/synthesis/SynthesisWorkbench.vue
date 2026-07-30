<script setup lang="ts">
import type { ModelKind } from "../../types"

defineProps<{
  kind: ModelKind
}>()
</script>

<template>
  <div class="layout-root">
    <div class="col-left">
      <slot name="left" />
    </div>
    <div class="col-middle">
      <slot name="middle" />
    </div>
    <div class="col-right">
      <slot name="right" />
    </div>
  </div>
</template>
