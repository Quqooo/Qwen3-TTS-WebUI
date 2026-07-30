import { useStorage } from "@vueuse/core"
import { ref, watch } from "vue"
import { clearCssVarCache } from "../theme"

const THEME_KEY = "qwen-tts:theme"

function detectBrowserTheme(): "dark" | "light" {
  if (typeof window === "undefined") return "light"
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function applyTheme(theme: "dark" | "light") {
  const root = document.documentElement
  if (theme === "dark") {
    root.classList.add("dark")
  } else {
    root.classList.remove("dark")
  }
  root.style.colorScheme = theme
}

const saved = useStorage<"dark" | "light" | "auto">(THEME_KEY, "auto", localStorage)
const resolved = ref<"dark" | "light">(
  saved.value === "auto" ? detectBrowserTheme() : saved.value
)
const isDark = ref(resolved.value === "dark")

applyTheme(resolved.value)

const mql = window.matchMedia("(prefers-color-scheme: dark)")
mql.addEventListener("change", function onChange(e: MediaQueryListEvent) {
  if (saved.value === "auto") {
    resolved.value = e.matches ? "dark" : "light"
  }
})

watch(resolved, (val) => {
  applyTheme(val)
  clearCssVarCache()
  isDark.value = val === "dark"
})

watch(saved, (val) => {
  resolved.value = val === "auto" ? detectBrowserTheme() : val
})

function commitTheme(next: "dark" | "light") {
  saved.value = next
  resolved.value = next
  applyTheme(next)
  clearCssVarCache()
  isDark.value = next === "dark"
}

export function useTheme() {
  function toggleTheme(event?: MouseEvent) {
    if (event) {
      const target = event.currentTarget as HTMLElement
      const rect = target.getBoundingClientRect()
      document.documentElement.style.setProperty("--theme-x", (rect.left + rect.width / 2) + "px")
      document.documentElement.style.setProperty("--theme-y", (rect.top + rect.height / 2) + "px")
    }

    const next = resolved.value === "dark" ? "light" : "dark"

    const d = document as unknown as { startViewTransition?: (cb: () => void) => void }
    if (d.startViewTransition) {
      d.startViewTransition(() => commitTheme(next))
    } else {
      commitTheme(next)
    }
  }

  function setTheme(mode: "dark" | "light" | "auto") {
    saved.value = mode
  }

  return {
    isDark,
    toggleTheme,
    setTheme,
    mode: saved,
  }
}
