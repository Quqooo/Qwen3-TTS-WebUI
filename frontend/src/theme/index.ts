export const theme = {
  shadow: {
    tooltip: "rgba(0,0,0,0.15)",
  },
} as const

export function cssVar(name: string): string {
  return `var(${name})`
}

export function cssRgb(name: string, alpha?: number): string {
  const a = alpha !== undefined && alpha < 1 ? ` / ${alpha}` : ""
  return `rgb(var(${name})${a})`
}

export function cssHsl(name: string, alpha?: number): string {
  const a = alpha !== undefined && alpha < 1 ? ` / ${alpha}` : ""
  return `hsl(var(${name})${a})`
}

let cachedVars = new Map<string, string>()

function readCssVar(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim()
}

export function getCssVar(name: string): string {
  const cached = cachedVars.get(name)
  if (cached !== undefined) return cached
  const val = readCssVar(name)
  cachedVars.set(name, val)
  return val
}

export function clearCssVarCache() {
  cachedVars.clear()
}

export function hslVar(name: string, alpha?: number): string {
  const val = getCssVar(name)
  if (!val) return ""
  if (alpha !== undefined && alpha < 1) {
    return `hsl(${val} / ${alpha})`
  }
  return `hsl(${val})`
}

export function primaryColor(): string {
  const h = getCssVar("--primary")
  return h ? `hsl(${h})` : "hsl(221, 83%, 53%)"
}

export function waveformGray(): string {
  const r = getCssVar("--waveform-gray")
  return r ? `rgb(${r})` : "#5B5B5B"
}

export function destructiveColor(): string {
  const r = getCssVar("--status-destructive")
  return r ? `rgb(${r})` : "#FF4E4E"
}

export function tooltipShadow(): string {
  const bg = getCssVar("--background")
  if (!bg) return "rgba(0,0,0,0.15)"
  const lightness = parseInt(bg.split("%")[0].split(" ").pop() || "100", 10)
  return lightness < 50 ? "rgba(0,0,0,0.4)" : "rgba(0,0,0,0.15)"
}

export function useTheme() {
  return theme
}
