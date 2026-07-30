<script setup lang="ts">
defineProps<{
  status: string
}>()

const statusColors: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  running: "bg-blue-100 text-blue-700",
  processing: "bg-blue-100 text-blue-700",
  queued: "bg-yellow-100 text-yellow-700",
  pending: "bg-yellow-100 text-yellow-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
  done: "bg-green-100 text-green-700",
}
</script>

<template>
  <span
    class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
    :class="statusColors[status] ?? 'bg-gray-100 text-gray-600'"
  >
    {{ status }}
  </span>
</template>
