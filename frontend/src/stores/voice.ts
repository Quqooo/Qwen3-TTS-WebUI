import { defineStore } from "pinia"
import { ref } from "vue"
import type { VoiceFile } from "../types"
import { voicesApi } from "../api/voices"

export const useVoiceStore = defineStore("voice", () => {
  const voices = ref<VoiceFile[]>([])
  const selectedVoice = ref<VoiceFile | null>(null)
  const loading = ref(false)

  async function fetchVoices() {
    loading.value = true
    try {
      const res = await voicesApi.list()
      voices.value = res.voices.map((name) => ({
        name,
        path: name,
      } as VoiceFile))
    } catch {
      // keep current
    } finally {
      loading.value = false
    }
  }

  function setVoices(list: VoiceFile[]) {
    voices.value = list
  }

  function selectVoice(voice: VoiceFile | null) {
    selectedVoice.value = voice
  }

  function addVoice(voice: VoiceFile) {
    voices.value.push(voice)
  }

  function removeVoice(name: string) {
    voices.value = voices.value.filter((v) => v.name !== name)
    if (selectedVoice.value?.name === name) {
      selectedVoice.value = null
    }
  }

  return { voices, selectedVoice, loading, fetchVoices, setVoices, selectVoice, addVoice, removeVoice }
})
