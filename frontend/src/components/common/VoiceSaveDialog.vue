<script setup lang="ts">
import { ref, computed, watch } from "vue"
import AppSelect from "./AppSelect.vue"
import AudioEditor from "../audio/AudioEditor.vue"
import { useModelStore } from "../../stores/model"
import { t } from "../../lang"

const props = defineProps<{
  open: boolean
  name: string
  model: string
  audioUrl?: string | null
  text: string
}>()

const emit = defineEmits<{
  (e: "update:name", val: string): void
  (e: "update:model", val: string): void
  (e: "update:text", val: string): void
  (e: "update:trimStart", val: number): void
  (e: "update:trimEnd", val: number): void
  (e: "update:audioUrl", val: string | null): void
  (e: "confirm"): void
  (e: "cancel"): void
}>()

const modelStore = useModelStore()

const modelOptions = computed(() =>
  modelStore.baseModels.map((m) => ({ value: m.id, label: m.id })),
)

const defaultModel = computed(() => {
  const loadedBase = modelStore.cacheStatus.loaded.find((m) => m.kind === "base")
  if (loadedBase) return loadedBase.id
  const first = modelStore.baseModels[0]
  return first ? first.id : ""
})

const trimStart = ref(0)
const trimEnd = ref(0)
const editorAudioUrl = ref<string | null>(null)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      trimStart.value = 0
      trimEnd.value = 0
      editorAudioUrl.value = props.audioUrl ?? null
      emit("update:trimStart", 0)
      emit("update:trimEnd", 0)
      if (!props.model) {
        emit("update:model", defaultModel.value)
      }
      if (!props.name) {
        emit("update:name", "")
      }
    }
  },
)

function onTrimStart(v: number) {
  trimStart.value = v
  emit("update:trimStart", v)
}

function onTrimEnd(v: number) {
  trimEnd.value = v
  emit("update:trimEnd", v)
}

function onFile(file: File | null) {
  if (file) {
    if (editorAudioUrl.value) URL.revokeObjectURL(editorAudioUrl.value)
    editorAudioUrl.value = URL.createObjectURL(file)
    emit("update:audioUrl", editorAudioUrl.value)
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="fixed inset-0 bg-black/30" @click="emit('cancel')" />
        <div class="dialog-content relative bg-card border rounded-xl shadow-lg p-6 w-full max-w-md mx-4 space-y-4 max-h-[90vh] overflow-y-auto">
          <h3 class="text-base font-semibold">{{ t('components.voiceSaveDialog.title') }}</h3>

          <div class="space-y-1.5">
            <label class="label">{{ t('components.voiceSaveDialog.modelLabel') }}</label>
            <AppSelect
              :model-value="model"
              :options="modelOptions"
              :placeholder="t('components.voiceSaveDialog.selectModel')"
              @update:model-value="emit('update:model', $event)"
            />
          </div>

          <div class="space-y-1.5">
            <label class="label">{{ t('components.voiceSaveDialog.nameLabel') }}</label>
            <input
              :value="name"
              type="text"
              class="w-full px-2 py-1.5 text-sm border rounded-lg bg-background"
              :placeholder="t('components.voiceSaveDialog.namePlaceholder')"
              @input="emit('update:name', ($event.target as HTMLInputElement).value)"
            />
          </div>

          <div class="space-y-1.5">
            <label class="label">{{ t('components.voiceSaveDialog.audioLabel') }}</label>
            <AudioEditor
              :audio-url="editorAudioUrl"
              :trim-start="trimStart"
              :trim-end="trimEnd"
              @file="onFile"
              @update:trim-start="onTrimStart"
              @update:trim-end="onTrimEnd"
            />
          </div>

          <div class="space-y-1.5">
            <label class="label">{{ t('components.voiceSaveDialog.textLabel') }}</label>
            <textarea
              :value="text"
              rows="3"
              class="w-full px-2 py-1.5 text-sm border rounded-lg bg-background resize-none"
              :placeholder="t('components.voiceSaveDialog.textPlaceholder')"
              @input="emit('update:text', ($event.target as HTMLTextAreaElement).value)"
            />
          </div>

          <div class="flex justify-end gap-2 pt-1">
            <button
              class="px-3 py-1.5 text-sm rounded-lg border hover:bg-accent transition-colors"
              @click="emit('cancel')"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
              :disabled="!name.trim() || !model"
              :class="(name.trim() && model) ? '' : 'opacity-50 cursor-not-allowed'"
              @click="emit('confirm')"
            >
              {{ t('common.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
