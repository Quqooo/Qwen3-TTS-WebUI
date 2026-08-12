import { ref, type Ref } from 'vue'
import { zhCN } from './zh-CN'
import { enUS } from './en-US'

export type TranslationDict = typeof zhCN

const LOCALE_KEY = 'qwen-tts:locale'

const locales: Record<string, any> = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

function detectBrowserLocale(): string {
  if (typeof navigator === 'undefined') return 'en-US'
  const lang = navigator.language || ''
  if (lang.startsWith('zh')) return 'zh-CN'
  return 'en-US'
}

const currentLocale: Ref<string> = ref(localStorage.getItem(LOCALE_KEY) || detectBrowserLocale())
const currentDict: Ref<TranslationDict> = ref(locales[currentLocale.value] || zhCN)
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
  'zh-CN': '中文',
  'en-US': 'English',
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
