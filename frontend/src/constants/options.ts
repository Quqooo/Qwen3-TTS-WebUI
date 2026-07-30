import { t } from '../lang'

export interface OptionItem {
  value: string
  label: string
}

const SPEAKER_LABELS: Record<string, string> = {
  serena: t('speakers.serena'),
  vivian: t('speakers.vivian'),
  uncle_fu: t('speakers.uncleFu'),
  ryan: t('speakers.ryan'),
  aiden: t('speakers.aiden'),
  ono_anna: t('speakers.onoAnna'),
  sohee: t('speakers.sohee'),
  eric: t('speakers.eric'),
  dylan: t('speakers.dylan'),
}

export function speakerLabel(value: string): string | null {
  return SPEAKER_LABELS[value] ?? null
}

function normalizeOption(value: string | OptionItem): OptionItem {
  return typeof value === 'string' ? { value, label: value } : value
}

export function buildSpeakerOptions(values: readonly (string | OptionItem)[]): OptionItem[] {
  return values.map(normalizeOption).map(option => ({
    value: option.value,
    label: SPEAKER_LABELS[option.value] ?? option.label,
  }))
}

export function buildLanguageOptions(values: readonly (string | OptionItem)[]): OptionItem[] {
  return values.map(normalizeOption)
}

export const FORMAT_OPTIONS: OptionItem[] = [
  { value: "wav", label: "WAV" },
  { value: "mp3", label: "MP3" },
  { value: "flac", label: "FLAC" },
  { value: "ogg", label: "OGG" },
  { value: "opus", label: "OPUS" },
  { value: "pcm", label: "PCM" },
]

export const SAMPLE_RATE_OPTIONS: OptionItem[] = [
  { value: "12000", label: "12000 Hz" },
  { value: "16000", label: "16000 Hz" },
  { value: "24000", label: "24000 Hz" },
  { value: "32000", label: "32000 Hz" },
  { value: "44100", label: "44100 Hz" },
  { value: "48000", label: "48000 Hz" },
]
