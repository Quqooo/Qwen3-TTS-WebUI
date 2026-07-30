<script setup lang="ts">
import { ref } from "vue"
import { FileText, GripVertical, Plus, Upload, X } from "@lucide/vue"
import DropTextarea from "../common/DropTextarea.vue"
import ModelConfigPanel from "./ModelConfigPanel.vue"
import type { ModelConfig } from "./ModelConfigPanel.vue"

const showTextImport = defineModel<boolean>("showTextImport", { required: true })
const showFileImport = defineModel<boolean>("showFileImport", { required: true })
const importText = defineModel<string>("importText", { required: true })
const importSplitChars = defineModel<string>("importSplitChars", { required: true })
const importRetainSplit = defineModel<boolean | null>("importRetainSplit", { required: true })
const importSplitMode = defineModel<number>("importSplitMode", { required: true })
const importConfig = defineModel<ModelConfig>("importConfig", { required: true })
const fillTimeline = defineModel<boolean>("fillTimeline", { required: true })

const props = defineProps<{
  importFiles: File[]
  fileImportError: string
  isDragging: boolean
  dragFileIndex: number
}>()

const emit = defineEmits<{
  confirmTextImport: []
  fileInput: [event: Event]
  fileDragOver: [event: DragEvent]
  fileDragEnter: []
  fileDragLeave: []
  fileDrop: [event: DragEvent]
  fileDragStart: [index: number, event: DragEvent]
  fileDragEnterItem: [index: number]
  fileDragEnd: []
  removeImportFile: [index: number]
  confirmFileImport: []
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="showTextImport" class="fixed inset-0 z-50 flex items-center justify-center" @keydown.escape="showTextImport = false">
        <div class="fixed inset-0 bg-black/30" />
        <div class="dialog-content relative bg-card border rounded-xl shadow-lg mx-4 w-[1060px] h-[700px] flex flex-col" @click.stop>
          <div class="flex items-center justify-between px-6 py-4 border-b shrink-0">
            <h3 class="text-base font-semibold">{{ $t('views.batch.addTextDialog.title') }}</h3>
            <button class="text-muted-foreground hover:text-foreground transition-colors" @click="showTextImport = false">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="flex gap-4 p-6 flex-1 min-h-0">
            <div class="flex-1 flex flex-col min-w-0">
              <div class="flex-1 flex flex-col">
                <label class="text-xs text-muted-foreground mb-1">{{ $t('views.batch.addTextDialog.contentLabel') }}</label>
                <DropTextarea v-model="importText" noAutosize :placeholder="$t('views.batch.addTextDialog.contentPlaceholder')" />
              </div>
              <div class="grid grid-cols-3 gap-4 mt-3 shrink-0">
                <div class="space-y-1">
                  <label class="text-xs text-muted-foreground">{{ $t('views.batch.addTextDialog.splitLabel') }}</label>
                  <input v-model="importSplitChars" type="text" class="w-full px-3 py-2 text-sm font-mono" />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-muted-foreground">{{ $t('views.batch.addTextDialog.splitModeLabel') }}</label>
                  <input
                    v-model.number="importSplitMode"
                    type="number"
                    min="1"
                    step="1"
                    class="w-full px-3 py-2 text-sm"
                    @wheel.prevent="importSplitMode = Math.max(1, importSplitMode + (($event as WheelEvent).deltaY < 0 ? 1 : -1))"
                    @blur="importSplitMode = Math.max(1, Math.round(importSplitMode) || 1)"
                  />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-muted-foreground">{{ $t('views.batch.addTextDialog.retainSplitLabel') }}</label>
                  <div class="flex p-0.5 gap-0.5 bg-muted/50 rounded-lg">
                    <button
                      class="btn-segment border-0"
                      :class="importRetainSplit === true ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
                      @click="importRetainSplit = importRetainSplit === true ? null : true"
                    >{{ $t('views.batch.addTextDialog.retain') }}</button>
                    <button
                      class="btn-segment border-0"
                      :class="importRetainSplit === false ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
                      @click="importRetainSplit = importRetainSplit === false ? null : false"
                    >{{ $t('views.batch.addTextDialog.notRetain') }}</button>
                  </div>
                </div>
              </div>
            </div>
            <div class="w-80 min-w-0 overflow-y-auto border-l border-border pl-4">
              <label class="text-xs text-muted-foreground mb-2 block">{{ $t('views.batch.addTextDialog.defaultConfig') }}</label>
              <ModelConfigPanel v-model="importConfig" hide-text hide-time-offset />
            </div>
          </div>
          <div class="flex justify-end gap-2 px-6 py-4 border-t shrink-0">
            <button class="px-3 py-1.5 text-sm rounded-lg border hover:bg-accent transition-colors" @click="showTextImport = false">
              {{ $t('views.batch.addTextDialog.cancel') }}
            </button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
              :disabled="!importText.trim()"
              @click="emit('confirmTextImport')"
            >{{ $t('views.batch.addTextDialog.add') }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="showFileImport" class="fixed inset-0 z-50 flex items-center justify-center" @keydown.escape="showFileImport = false">
        <div class="fixed inset-0 bg-black/30" />
        <div class="dialog-content relative bg-card border rounded-xl shadow-lg mx-4 w-[1060px] h-[700px] flex flex-col" @click.stop>
          <div class="flex items-center justify-between px-6 py-4 border-b shrink-0">
            <h3 class="text-base font-semibold">{{ $t('views.batch.addFileDialog.title') }}</h3>
            <button class="text-muted-foreground hover:text-foreground transition-colors" @click="showFileImport = false">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="flex gap-4 p-6 flex-1 min-h-0">
            <div class="flex-1 flex flex-col min-w-0">
              <input ref="fileInputRef" type="file" multiple accept=".srt,.lrc,.ass,.ssa,.vtt,.stl,.imsc" class="hidden" @input="emit('fileInput', $event)" />
              <template v-if="props.importFiles.length === 0">
                <div
                  class="flex-1 border-2 border-dashed rounded-lg flex flex-col items-center justify-center cursor-pointer transition-colors"
                  :class="props.isDragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'"
                  @drop.prevent="emit('fileDrop', $event)"
                  @dragover.prevent="emit('fileDragOver', $event)"
                  @dragenter="emit('fileDragEnter')"
                  @dragleave="emit('fileDragLeave')"
                  @click="fileInputRef?.click()"
                >
                  <Upload class="w-10 h-10 text-muted-foreground/40 mb-3" />
                  <p class="text-sm text-muted-foreground">{{ $t('views.batch.addFileDialog.dropHint') }}</p>
                </div>
              </template>
              <template v-else>
                <div
                  class="flex-1 border-2 rounded-lg flex flex-col transition-colors"
                  :class="props.isDragging ? 'border-primary bg-primary/5 border-dashed' : 'border-border'"
                  @drop.prevent="emit('fileDrop', $event)"
                  @dragover.prevent="emit('fileDragOver', $event)"
                  @dragenter="emit('fileDragEnter')"
                  @dragleave="emit('fileDragLeave')"
                  @click="fileInputRef?.click()"
                >
                  <div class="flex items-center justify-between px-3 py-2 border-b shrink-0">
                    <span class="text-xs text-muted-foreground">{{ $t('views.batch.addFileDialog.fileCount', { count: props.importFiles.length }) }}</span>
                    <button class="w-6 h-6 flex items-center justify-center rounded text-xs text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors" v-tooltip="$t('views.batch.addFileDialog.addMore')" @click.stop="fileInputRef?.click()">
                      <Plus class="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div class="flex-1 overflow-y-auto p-2 space-y-1">
                    <div
                      v-for="(file, index) in props.importFiles"
                      :key="file.name + file.size + file.lastModified"
                      class="flex items-center gap-2 px-3 py-2 rounded-lg text-xs cursor-grab transition-all duration-150"
                      :class="props.dragFileIndex === index ? 'opacity-40 scale-95 bg-primary/5' : 'bg-secondary/30 hover:bg-secondary/60'"
                      draggable="true"
                      @dragstart="emit('fileDragStart', index, $event)"
                      @dragenter.prevent="emit('fileDragEnterItem', index)"
                      @dragend="emit('fileDragEnd')"
                    >
                      <GripVertical class="w-3.5 h-3.5 text-muted-foreground/40 shrink-0" />
                      <FileText class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                      <span class="truncate flex-1">{{ file.name }}</span>
                      <button class="text-muted-foreground hover:text-destructive transition-colors shrink-0" @click.stop="emit('removeImportFile', index)">
                        <X class="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                </div>
              </template>
              <div v-if="props.fileImportError" class="text-xs text-destructive mt-1 shrink-0">{{ props.fileImportError }}</div>
            </div>
            <div class="w-80 min-w-0 overflow-y-auto border-l border-border pl-4">
              <label class="text-xs text-muted-foreground mb-2 block">{{ $t('views.batch.addFileDialog.defaultConfig') }}</label>
              <ModelConfigPanel v-model="importConfig" hide-text hide-time-offset />
              <div class="flex items-center justify-between mt-4 pt-4 border-t border-border">
                <span class="text-sm font-medium">{{ $t('views.batch.addFileDialog.fillTimeline') }}</span>
                <button
                  type="button"
                  role="switch"
                  :aria-checked="fillTimeline"
                  class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200"
                  :class="fillTimeline ? 'bg-primary' : 'bg-secondary'"
                  @click="fillTimeline = !fillTimeline"
                >
                  <span class="pointer-events-none block h-4 w-4 rounded-full bg-white shadow transition-transform duration-200" :class="fillTimeline ? 'translate-x-4' : 'translate-x-0'" />
                </button>
              </div>
            </div>
          </div>
          <div class="flex justify-end gap-2 px-6 py-4 border-t shrink-0">
            <button class="px-3 py-1.5 text-sm rounded-lg border hover:bg-accent transition-colors" @click="showFileImport = false">
              {{ $t('views.batch.addFileDialog.cancel') }}
            </button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
              :disabled="props.importFiles.length === 0"
              @click="emit('confirmFileImport')"
            >{{ $t('views.batch.addFileDialog.add') }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
