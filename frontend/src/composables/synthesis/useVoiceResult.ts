import { ref, type Ref } from "vue"
import { trimAudioBlob } from "../../api/audio"
import { voicesApi } from "../../api/voices"
import { useToast } from "../useToast"
import { t } from "../../lang"

export function useVoiceResult(
  resultAudioUrl: Ref<string | null>,
  synthesisText: Ref<string>,
  resultDuration: Ref<number | undefined>,
  streamingEnabled: Ref<boolean>,
  outputFormat: Ref<string>,
  voiceFiles?: Ref<{ value: string; label: string }[]>,
) {
  const showVoiceSaveDialog = ref(false)
  const voiceSaveName = ref("")
  const voiceSaveText = ref("")
  const voiceSaveModel = ref("")
  const voiceSaveAudioUrl = ref<string | null>(null)
  const voiceSaveTrimStart = ref(0)
  const voiceSaveTrimEnd = ref(0)

  function downloadAudio() {
    if (!resultAudioUrl.value) return
    const ts = Math.floor(Date.now() / 1000)
    const safeText = synthesisText.value
      .replace(/[\n\r\/\\:*?"<>|]/g, '')
      .trim()
      .slice(0, 7) || 'audio'
    const ext = streamingEnabled.value ? 'wav' : outputFormat.value
    const filename = `${ts}_${safeText}.${ext}`
    const a = document.createElement('a')
    a.href = resultAudioUrl.value
    a.download = filename
    a.click()
  }

  function onSaveVoice() {
    if (!resultAudioUrl.value || !synthesisText.value) return
    voiceSaveName.value = ''
    voiceSaveText.value = synthesisText.value
    voiceSaveModel.value = ''
    voiceSaveAudioUrl.value = null
    voiceSaveTrimStart.value = 0
    voiceSaveTrimEnd.value = 0
    showVoiceSaveDialog.value = true
  }

  async function doSaveVoice(name: string, modelId: string) {
    showVoiceSaveDialog.value = false
    const text = voiceSaveText.value.trim()
    if (!resultAudioUrl.value || !name.trim() || !modelId) return
    const { success: toastSuccess } = useToast()
    try {
      const sourceUrl = voiceSaveAudioUrl.value || resultAudioUrl.value
      const resp = await fetch(sourceUrl!)
      let blob = await resp.blob()
      if (!voiceSaveAudioUrl.value && (voiceSaveTrimStart.value > 0 || voiceSaveTrimEnd.value > 0)) {
        const dur = resultDuration.value ?? 0
        const end = voiceSaveTrimEnd.value > 0 ? voiceSaveTrimEnd.value : dur
        if (end > voiceSaveTrimStart.value) {
          blob = await trimAudioBlob(blob, voiceSaveTrimStart.value, end)
        }
      }
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result as string)
        reader.onerror = reject
        reader.readAsDataURL(blob)
      })
      await voicesApi.upload({
        audio: base64,
        customName: name.trim() || undefined,
        model: modelId,
        text: text || undefined,
      })
      toastSuccess(t('views.voices.voiceSaved'))
      if (voiceFiles) {
        const res = await voicesApi.list()
        voiceFiles.value = res.voices.map((v: string) => ({ value: v, label: v }))
      }
    } catch {
      // error already shown via toast
    }
  }

  return {
    showVoiceSaveDialog,
    voiceSaveName,
    voiceSaveText,
    voiceSaveModel,
    voiceSaveAudioUrl,
    voiceSaveTrimStart,
    voiceSaveTrimEnd,
    downloadAudio,
    onSaveVoice,
    doSaveVoice,
  }
}
