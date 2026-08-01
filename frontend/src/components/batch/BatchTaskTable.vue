<script setup lang="ts">
import { ref } from "vue"
import { useVirtualizer } from "@tanstack/vue-virtual"
import { Download, GripVertical, Pause, Play, Settings, Square, Trash2, WandSparkles } from "@lucide/vue"
import BatchWaveform from "./BatchWaveform.vue"
import type { BatchRow } from "../../composables/useBatchTypes"

const props = defineProps<{
  rows: BatchRow[]
  selectedIndexes: Set<number>
  editingIndex: number
  editingTextId: string | null
  editingTextValue: string
  dragRowIndex: number
  generating: boolean
  tableVolume: number
  rowProgress: Record<string, number>
  voiceLabel: (row: BatchRow) => string
}>()

const emit = defineEmits<{
  contextMenu: [event: MouseEvent]
  tableVolumeWheel: [event: WheelEvent]
  rowClick: [index: number, event: MouseEvent]
  rowDragEnter: [index: number]
  toggleRowSelect: [index: number, event: MouseEvent]
  rowDragStart: [index: number, event: DragEvent]
  rowDragEnd: []
  startEditText: [row: BatchRow, index: number]
  updateEditingText: [value: string]
  confirmEditText: []
  cancelEditText: []
  togglePlayRow: [index: number]
  seekWaveform: [rowId: string, value: number]
  downloadRowAudio: [index: number]
  removeRow: [index: number]
  generateRow: [index: number]
  stopRowGenerate: [rowId: string]
  toggleBatchGenerate: []
  toggleFinalized: [index: number]
  toggleDetails: [index: number]
}>()

const scrollBodyRef = ref<HTMLElement | null>(null)
const virtualizer = useVirtualizer({
  get count() { return props.rows.length },
  getScrollElement: () => scrollBodyRef.value,
  estimateSize: () => 44,
  overscan: 10,
})

function measureRow(element: unknown) {
  if (element instanceof Element) virtualizer.value.measureElement(element)
}

function scrollToStart() {
  scrollBodyRef.value?.scrollTo({ top: 0, behavior: "smooth" })
}

function scrollToEnd() {
  scrollBodyRef.value?.scrollTo({ top: scrollBodyRef.value.scrollHeight, behavior: "smooth" })
}

defineExpose({ scrollToStart, scrollToEnd })
</script>

<template>
  <div class="flex-1 border rounded-xl bg-card overflow-hidden flex flex-col">
    <div class="grid grid-cols-batch text-xs font-medium text-muted-foreground border-b bg-secondary/20 shrink-0">
      <div class="px-2 py-2 text-center truncate min-w-0 border-r border-border/50" v-tooltip="$t('views.batch.columns.sortTooltip')">{{ $t('views.batch.columns.sort') }}</div>
      <div class="px-2 py-2 text-center truncate min-w-0 border-r border-border/50">{{ $t('views.batch.columns.drag') }}</div>
      <div class="px-2 py-2 text-center truncate min-w-0 border-r border-border/50">{{ $t('views.batch.columns.text') }}</div>
      <div class="px-2 py-2 text-center truncate min-w-0 border-r border-border/50">{{ $t('views.batch.columns.voice') }}</div>
      <div class="px-2 py-2 text-center min-w-0 border-r border-border/50">
        {{ $t('views.batch.columns.audio') }}
        <span class="font-mono tabular-nums cursor-ns-resize ml-1" v-tooltip="$t('views.batch.columns.audioVolumeTooltip')" @wheel.prevent="emit('tableVolumeWheel', $event)">
          {{ Math.round(props.tableVolume * 100) }}%
        </span>
      </div>
      <div class="px-2 py-2 text-center truncate min-w-0 border-r border-border/50">{{ $t('views.batch.columns.delete') }}</div>
      <div class="px-2 py-2 text-center truncate min-w-0 border-r border-border/50">{{ $t('views.batch.columns.generate') }}</div>
      <div class="px-2 py-2 text-center truncate min-w-0 border-r border-border/50">{{ $t('views.batch.columns.finalize') }}</div>
      <div class="px-2 py-2 text-center truncate min-w-0">{{ $t('views.batch.columns.details') }}</div>
    </div>

    <div v-if="props.rows.length > 0" ref="scrollBodyRef" class="flex-1 overflow-y-auto" @contextmenu="emit('contextMenu', $event)">
      <div :style="{ height: virtualizer.getTotalSize() + 'px', width: '100%', position: 'relative' }">
        <div
          v-for="virtualRow in virtualizer.getVirtualItems()"
          :key="String(virtualRow.key)"
          :ref="measureRow"
          :data-index="virtualRow.index"
          :style="{ position: 'absolute', top: 0, left: 0, width: '100%', transform: 'translateY(' + virtualRow.start + 'px)' }"
          class="grid grid-cols-batch text-sm border-b border-border/25 transition-all duration-150 h-11"
          :class="[
            props.selectedIndexes.has(virtualRow.index) ? 'bg-primary/5' : 'hover:bg-accent/30',
            props.editingIndex === virtualRow.index ? 'ring-1 ring-inset ring-primary/30' : '',
            props.dragRowIndex === virtualRow.index ? 'opacity-40 scale-[0.97]' : '',
          ]"
          v-memo="[
            props.rows[virtualRow.index]?.audioState,
            props.rows[virtualRow.index]?.finalized,
            props.rows[virtualRow.index]?.isPlaying,
            props.rows[virtualRow.index]?.text,
            props.rows[virtualRow.index]?.audioUrl,
            props.selectedIndexes.has(virtualRow.index),
            props.editingIndex === virtualRow.index,
            props.editingTextId === props.rows[virtualRow.index]?.id,
            props.dragRowIndex === virtualRow.index,
            props.generating,
            props.rowProgress[props.rows[virtualRow.index]?.id],
            props.voiceLabel(props.rows[virtualRow.index]),
          ]"
          @click="emit('rowClick', virtualRow.index, $event)"
          @dragenter.prevent="emit('rowDragEnter', virtualRow.index)"
        >
          <div
            class="px-2 py-2 text-xs text-muted-foreground text-center select-none flex items-center justify-center border-r border-border/25 min-w-0"
            :class="props.rows[virtualRow.index].audioState === 'generating' ? 'cursor-default' : 'cursor-pointer'"
            @click="props.rows[virtualRow.index].audioState !== 'generating' && emit('toggleRowSelect', virtualRow.index, $event)"
          >
            <span class="w-5 h-5 flex items-center justify-center rounded shrink-0" :class="props.selectedIndexes.has(virtualRow.index) ? 'bg-primary text-primary-foreground' : ''">
              {{ virtualRow.index + 1 }}
            </span>
          </div>

          <div
            class="px-2 py-2 text-muted-foreground/30 flex items-center justify-center border-r border-border/25 min-w-0"
            :class="props.rows[virtualRow.index].audioState === 'generating' || props.generating ? 'cursor-not-allowed opacity-30' : 'cursor-grab'"
            :draggable="props.rows[virtualRow.index].audioState !== 'generating' && !props.generating"
            @dragstart="emit('rowDragStart', virtualRow.index, $event)"
            @dragend="emit('rowDragEnd')"
          >
            <GripVertical class="w-3.5 h-3.5 shrink-0" />
          </div>

          <div
            class="px-2 py-2 text-xs border-r border-border/25 flex items-center min-w-0"
            :class="props.rows[virtualRow.index].audioState === 'generating' ? 'pointer-events-none' : ''"
            v-tooltip="props.rows[virtualRow.index].text"
            @dblclick="emit('startEditText', props.rows[virtualRow.index], virtualRow.index)"
          >
            <input
              v-if="props.editingTextId === props.rows[virtualRow.index].id"
              :value="props.editingTextValue"
              class="w-full text-xs border-0 outline-none bg-transparent p-0"
              :data-edit-input="props.rows[virtualRow.index].id"
              @input="emit('updateEditingText', ($event.target as HTMLInputElement).value)"
              @keydown.enter="emit('confirmEditText')"
              @keydown.escape="emit('cancelEditText')"
              @blur="emit('confirmEditText')"
            />
            <span v-else class="truncate min-w-0 flex-1">{{ props.rows[virtualRow.index].text || $t('views.batch.row.emptyText') }}</span>
          </div>

          <div class="px-2 py-2 text-xs text-center border-r border-border/25 flex items-center justify-center min-w-0" v-tooltip="props.voiceLabel(props.rows[virtualRow.index])">
            <span class="truncate min-w-0 flex-1">{{ props.voiceLabel(props.rows[virtualRow.index]) }}</span>
          </div>

          <div class="px-2 py-2 flex items-center gap-1.5 border-r border-border/25 min-w-0">
            <button
              class="w-6 h-6 flex items-center justify-center rounded-full shrink-0 transition-colors"
              :class="{
                'bg-primary text-primary-foreground hover:opacity-90': props.rows[virtualRow.index].audioState === 'done',
                'bg-destructive/10 text-destructive cursor-default': props.rows[virtualRow.index].audioState === 'error',
                'bg-primary/10 text-primary cursor-default': props.rows[virtualRow.index].audioState === 'generating',
                'bg-secondary text-muted-foreground/30 cursor-default': props.rows[virtualRow.index].audioState === 'none',
              }"
              :disabled="props.rows[virtualRow.index].audioState !== 'done'"
              v-tooltip="props.rows[virtualRow.index].audioState === 'error' ? props.rows[virtualRow.index].errorMessage : ''"
              @click="emit('togglePlayRow', virtualRow.index)"
            >
              <span v-if="props.rows[virtualRow.index].audioState === 'generating'" class="block w-3 h-3">
                <span class="block w-full h-full rounded-full border-2 border-current border-t-transparent animate-spin" />
              </span>
              <Play v-else-if="props.rows[virtualRow.index].audioState === 'done' && !props.rows[virtualRow.index].isPlaying" class="w-3 h-3 fill-current ml-0.5" />
              <Pause v-else-if="props.rows[virtualRow.index].audioState === 'done' && props.rows[virtualRow.index].isPlaying" class="w-3 h-3 fill-current" />
              <Play v-else class="w-3 h-3 fill-current ml-0.5" :class="props.rows[virtualRow.index].audioState === 'none' ? 'opacity-30' : ''" />
            </button>
            <div class="flex-1 relative h-6 min-w-0">
              <BatchWaveform
                v-if="props.rows[virtualRow.index].audioState === 'done'"
                :row-id="props.rows[virtualRow.index].id"
                :audio-url="props.rows[virtualRow.index].audioUrl"
                :progress="props.rowProgress[props.rows[virtualRow.index].id] ?? 0"
                @seek="emit('seekWaveform', props.rows[virtualRow.index].id, $event)"
              />
              <div v-else-if="props.rows[virtualRow.index].audioState === 'generating'" class="w-full h-full rounded-sm breathe-bar" />
              <div v-else class="w-full h-full rounded-sm bg-muted/20" />
            </div>
            <button
              class="w-6 h-6 flex items-center justify-center rounded transition-colors shrink-0"
              :class="props.rows[virtualRow.index].audioState === 'done' ? 'text-muted-foreground hover:text-foreground hover:bg-secondary' : 'text-muted-foreground/30 cursor-default'"
              :disabled="props.rows[virtualRow.index].audioState !== 'done'"
              v-tooltip="$t('views.batch.row.download')"
              @click="emit('downloadRowAudio', virtualRow.index)"
            >
              <Download class="w-3.5 h-3.5" />
            </button>
          </div>

          <div class="px-2 py-2 flex items-center justify-center border-r border-border/25 min-w-0">
            <button
              class="w-6 h-6 flex items-center justify-center rounded transition-colors"
              :class="props.rows[virtualRow.index].audioState === 'generating' || props.rows[virtualRow.index].finalized ? 'text-muted-foreground/30 cursor-not-allowed' : 'text-muted-foreground hover:text-destructive hover:bg-destructive/10'"
              :disabled="props.rows[virtualRow.index].audioState === 'generating' || props.rows[virtualRow.index].finalized"
              v-tooltip="$t('views.batch.row.delete')"
              @click="emit('removeRow', virtualRow.index)"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>

          <div class="px-2 py-2 flex items-center justify-center border-r border-border/25 min-w-0">
            <button
              class="w-6 h-6 flex items-center justify-center rounded transition-colors"
              :class="props.rows[virtualRow.index].audioState === 'generating'
                ? 'bg-destructive/10 text-destructive'
                : props.rows[virtualRow.index].finalized
                  ? 'text-muted-foreground/30 cursor-not-allowed'
                  : props.generating
                    ? 'opacity-30 cursor-not-allowed'
                    : 'text-muted-foreground hover:text-primary hover:bg-primary/10'"
              v-tooltip="props.rows[virtualRow.index].audioState === 'generating' ? (props.generating ? $t('views.batch.row.pause') : $t('views.batch.row.stop')) : props.rows[virtualRow.index].finalized ? $t('views.batch.row.finalized') : props.generating ? $t('views.batch.row.batchGenerating') : $t('views.batch.row.generateThis')"
              :disabled="props.rows[virtualRow.index].finalized || (!!props.generating && props.rows[virtualRow.index].audioState !== 'generating')"
              @click="props.rows[virtualRow.index].audioState === 'generating'
                ? (props.generating ? emit('toggleBatchGenerate') : emit('stopRowGenerate', props.rows[virtualRow.index].id))
                : emit('generateRow', virtualRow.index)"
            >
              <Square v-if="props.rows[virtualRow.index].audioState === 'generating'" class="w-3 h-3" />
              <WandSparkles v-else class="w-3.5 h-3.5" />
            </button>
          </div>

          <div class="px-2 py-2 flex items-center justify-center border-r border-border/25 min-w-0">
            <label class="inline-flex items-center select-none" :class="props.rows[virtualRow.index].audioState !== 'done' ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'" @click="props.rows[virtualRow.index].audioState === 'done' && emit('toggleFinalized', virtualRow.index)">
              <span
                class="w-4 h-4 rounded border-2 flex items-center justify-center transition-all duration-150"
                :class="props.rows[virtualRow.index].finalized
                  ? props.rows[virtualRow.index].audioState === 'done' ? 'bg-primary border-primary' : 'bg-muted border-muted-foreground/20'
                  : 'border-muted-foreground/30 hover:border-primary/50'"
              >
                <svg class="w-3 h-3 text-primary-foreground transition-opacity duration-150" :class="props.rows[virtualRow.index].finalized ? 'opacity-100' : 'opacity-0'" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                </svg>
              </span>
            </label>
          </div>

          <div class="px-2 py-2 flex items-center justify-center min-w-0">
            <button
              class="w-6 h-6 flex items-center justify-center rounded transition-colors"
              :class="props.editingIndex === virtualRow.index ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-primary hover:bg-primary/10'"
              v-tooltip="$t('views.batch.row.configure')"
              @click="emit('toggleDetails', virtualRow.index)"
            >
              <Settings class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="flex-1 flex items-center justify-center text-xs text-muted-foreground py-12" @contextmenu="emit('contextMenu', $event)">
      {{ $t('views.batch.empty') }}
    </div>

    <slot name="footer" />
  </div>
</template>

<style scoped>
.grid-cols-batch {
  grid-template-columns: 1fr 1fr 6fr 2fr 6fr 1fr 1fr 1fr 1fr;
}

.breathe-bar {
  background-color: hsl(var(--muted) / 0.2);
  animation: breathe 3s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { background-color: hsl(var(--muted) / 0.2); }
  50% { background-color: hsl(var(--primary) / 0.15); }
}
</style>
