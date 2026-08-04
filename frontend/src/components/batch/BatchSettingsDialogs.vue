<script setup lang="ts">
import { AlertTriangle, Download, Upload, X } from "@lucide/vue"
import ModelConfigPanel from "./ModelConfigPanel.vue"
import type { ModelConfig } from "./ModelConfigPanel.vue"
import AppSlider from "../common/AppSlider.vue"
import { destructiveColor } from "../../theme"

const showConfirmClear = defineModel<boolean>("showConfirmClear", { required: true })
const showBatchConfig = defineModel<boolean>("showBatchConfig", { required: true })
const showMoreConfig = defineModel<boolean>("showMoreConfig", { required: true })
const batchConfig = defineModel<ModelConfig>("batchConfig", { required: true })
const persistent = defineModel<boolean>("persistent", { required: true })
const keepAlive = defineModel<boolean>("keepAlive", { required: true })
const priorityMode = defineModel<"model" | "serial">("priorityMode", { required: true })
const strictMode = defineModel<boolean>("strictMode", { required: true })
const minSilenceMs = defineModel<number>("minSilenceMs", { required: true })
const concurrentTasks = defineModel<number>("concurrentTasks", { required: true })

const emit = defineEmits<{
  confirmClear: []
  applyBatchConfig: [config: ModelConfig]
  clearCache: []
  saveCache: []
  exportBackup: []
  importBackup: [event: Event]
}>()
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="showConfirmClear" class="fixed inset-0 z-50 flex items-center justify-center" @keydown.escape="showConfirmClear = false">
        <div class="fixed inset-0 bg-black/30" @click="showConfirmClear = false" />
        <div class="dialog-content relative bg-card border rounded-xl shadow-lg mx-4 w-96 p-8 flex flex-col items-center gap-4" @click.stop>
          <AlertTriangle class="w-10 h-10" :style="{ color: destructiveColor() }" />
          <div class="text-center">
            <h3 class="text-base font-semibold mb-1">{{ $t('views.batch.clearDialog.title') }}</h3>
            <p class="text-xs text-muted-foreground">{{ $t('views.batch.clearDialog.message') }}</p>
          </div>
          <div class="flex gap-2 w-full">
            <button class="flex-1 px-3 py-1.5 text-sm rounded-lg border hover:bg-accent transition-colors" @click="showConfirmClear = false">
              {{ $t('views.batch.clearDialog.cancel') }}
            </button>
            <button class="flex-1 px-3 py-1.5 text-sm rounded-lg transition-colors" :style="{ backgroundColor: destructiveColor(), color: 'white' }" @click="emit('confirmClear')">
              {{ $t('views.batch.clearDialog.confirmClear') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="showBatchConfig" class="fixed inset-0 z-50 flex items-center justify-center" @keydown.escape="showBatchConfig = false">
        <div class="fixed inset-0 bg-black/30" @click="showBatchConfig = false" />
        <div class="dialog-content relative bg-card border rounded-xl shadow-lg mx-4 w-[420px] h-[75vh] flex flex-col" @click.stop>
          <div class="flex items-center justify-between px-6 py-4 border-b shrink-0">
            <h3 class="text-base font-semibold">{{ $t('views.batch.batchConfigDialog.title') }}</h3>
            <button class="text-muted-foreground hover:text-foreground transition-colors" @click="showBatchConfig = false">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto px-6 py-4">
            <ModelConfigPanel v-model="batchConfig" hide-text hide-time-offset />
          </div>
          <div class="flex justify-end gap-2 px-6 py-4 border-t shrink-0">
            <button class="px-3 py-1.5 text-sm rounded-lg border hover:bg-accent transition-colors" @click="showBatchConfig = false">
              {{ $t('views.batch.batchConfigDialog.cancel') }}
            </button>
            <button class="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity" @click="emit('applyBatchConfig', batchConfig)">
              {{ $t('views.batch.batchConfigDialog.apply') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="showMoreConfig" class="fixed inset-0 z-50 flex items-center justify-center" @keydown.escape="showMoreConfig = false">
        <div class="fixed inset-0 bg-black/30" @click="showMoreConfig = false" />
        <div class="dialog-content relative bg-card border rounded-xl shadow-lg mx-4 w-[420px] p-6" @click.stop>
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-base font-semibold">{{ $t('views.batch.moreConfigDialog.title') }}</h3>
            <button class="text-muted-foreground hover:text-foreground transition-colors" @click="showMoreConfig = false">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="flex flex-col gap-4">
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium">{{ $t('views.batch.moreConfigDialog.persistentCache') }}</span>
              <div class="flex p-0.5 gap-0.5 border rounded-lg">
                <button
                  class="btn-segment border-0"
                  :class="!persistent ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
                  @click="persistent = false; emit('clearCache')"
                >{{ $t('views.batch.moreConfigDialog.cacheDisabled') }}</button>
                <div class="w-px bg-border self-center h-4" />
                <button
                  class="btn-segment border-0"
                  :class="persistent ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
                  @click="persistent = true; emit('saveCache')"
                >{{ $t('views.batch.moreConfigDialog.cacheEnabled') }}</button>
              </div>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-sm font-medium">{{ $t('views.batch.moreConfigDialog.keepAlive') }}</span>
              <div class="flex p-0.5 gap-0.5 border rounded-lg">
                <button
                  class="btn-segment border-0"
                  :class="!keepAlive ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
                  @click="keepAlive = false"
                >{{ $t('views.batch.moreConfigDialog.cacheDisabled') }}</button>
                <div class="w-px bg-border self-center h-4" />
                <button
                  class="btn-segment border-0"
                  :class="keepAlive ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
                  @click="keepAlive = true"
                >{{ $t('views.batch.moreConfigDialog.cacheEnabled') }}</button>
              </div>
            </div>

            <div class="flex gap-2">
              <button class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs rounded-lg border hover:bg-accent transition-colors" @click="emit('exportBackup')">
                <Download class="w-3.5 h-3.5" /> {{ $t('views.batch.moreConfigDialog.exportBackup') }}
              </button>
              <label class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs rounded-lg border hover:bg-accent transition-colors cursor-pointer">
                <Upload class="w-3.5 h-3.5" /> {{ $t('views.batch.moreConfigDialog.importBackup') }}
                <input type="file" accept=".zip" class="hidden" @input="emit('importBackup', $event)" />
              </label>
            </div>

            <div class="border-t border-border" />
            <div>
              <div class="text-xs text-muted-foreground mb-1.5">{{ $t('views.batch.moreConfigDialog.genOrder') }}</div>
              <div class="flex p-0.5 gap-0.5 border rounded-lg">
                <button class="btn-segment border-0" :class="priorityMode === 'model' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'" @click="priorityMode = 'model'">
                  {{ $t('views.batch.moreConfigDialog.modelFirst') }}
                </button>
                <div class="w-px bg-border self-center h-4" />
                <button class="btn-segment border-0" :class="priorityMode === 'serial' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'" @click="priorityMode = 'serial'">
                  {{ $t('views.batch.moreConfigDialog.seqFirst') }}
                </button>
              </div>
            </div>

            <div>
              <div class="text-xs text-muted-foreground mb-1.5">{{ $t('views.batch.moreConfigDialog.timelineAlign') }}</div>
              <div class="flex p-0.5 gap-0.5 border rounded-lg">
                <button class="btn-segment border-0" :class="!strictMode ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'" @click="strictMode = false">
                  {{ $t('views.batch.moreConfigDialog.lenient') }}
                </button>
                <div class="w-px bg-border self-center h-4" />
                <button class="btn-segment border-0" :class="strictMode ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'" @click="strictMode = true">
                  {{ $t('views.batch.moreConfigDialog.strict') }}
                </button>
              </div>
            </div>

            <div>
              <label class="text-xs text-muted-foreground mb-1.5 block">{{ $t('views.batch.moreConfigDialog.minSilence') }}</label>
              <AppSlider v-model="minSilenceMs" :min="0" :max="2000" :step="10" />
            </div>

            <div>
              <label class="text-xs text-muted-foreground mb-1.5 block">{{ $t('views.batch.moreConfigDialog.concurrency') }}</label>
              <AppSlider v-model="concurrentTasks" :min="1" :max="10" :step="1" />
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
