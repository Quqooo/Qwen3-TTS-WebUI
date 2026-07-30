import { ref, type Ref } from 'vue'
import { zh_cn } from './zh_cn'
import { en_us } from './en_us'

export type TranslationDict = typeof zh_cn

const LOCALE_KEY = 'qwen-tts:locale'

const locales: Record<string, any> = {
  zh_cn,
  en_us,
}

function detectBrowserLocale(): string {
  if (typeof navigator === 'undefined') return 'en_us'
  const lang = navigator.language?.toLowerCase().replace('-', '_') || ''
  if (lang in locales) return lang
  if (lang.startsWith('zh')) return 'zh_cn'
  return 'en_us'
}

const currentLocale: Ref<string> = ref(localStorage.getItem(LOCALE_KEY) || detectBrowserLocale())
const currentDict: Ref<TranslationDict> = ref(locales[currentLocale.value] || zh_cn)
const localeVersion: Ref<number> = ref(0)

function resolveKey(dict: TranslationDict, path: string): unknown {
  const keys = path.split('.')
  let result: unknown = dict
  for (const key of keys) {
    if (result && typeof result === 'object' && key in (result as Record<string, unknown>)) {
      result = (result as Record<string, unknown>)[key]
    } else {
      return undefined
    }
  }
  return result
}

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template
  return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, key: string) => {
    return params[key] !== undefined ? String(params[key]) : `{{ ${key} }}`
  })
}

export function setLocale(locale: string): void {
  if (locales[locale]) {
    currentLocale.value = locale
    currentDict.value = locales[locale]
    localeVersion.value++
    localStorage.setItem(LOCALE_KEY, locale)
  }
}

export function getLocale(): string {
  return currentLocale.value
}

export function getAvailableLocales(): string[] {
  return Object.keys(locales)
}

export const localeLabels: Record<string, string> = {
  zh_cn: '中文',
  en_us: 'English',
}

export function t(path: string, params?: Record<string, string | number>): string {
  void localeVersion.value
  const value = resolveKey(currentDict.value, path)
  if (value === undefined) {
    console.warn(`[i18n] Missing translation key: ${path}`)
    return path
  }
  if (typeof value === 'string') {
    return interpolate(value, params)
  }
  console.warn(`[i18n] Key "${path}" is not a string, got ${typeof value}`)
  return path
}

export function useI18n() {
  return {
    t,
    locale: currentLocale,
    setLocale,
    getLocale,
    getAvailableLocales,
  }
}
