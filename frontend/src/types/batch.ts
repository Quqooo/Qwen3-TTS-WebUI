import type { ModelKind, GenerationParamsConfig as GenParams } from "../types"

export interface BatchRow {
  id: string
  text: string
  modelKind: ModelKind
  model: string
  speaker: string
  instruct: string
  voiceDescription: string
  voiceFile: string
  refText: string
  xVectorOnly: boolean
  cloneSource: "upload" | "voice_file"
  refAudioUrl: string
  refAudioName: string
  timelineEnabled: boolean
  timelineStart: number
  timelineEnd: number
  language: string
  generationParams: GenParams
  finalized: boolean
  isPlaying: boolean
  audioState: "none" | "generating" | "done" | "error"
  audioUrl?: string
  errorMessage?: string
}
