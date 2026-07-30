import type { Directive } from "vue"
import { tooltipShadow } from "../theme"

const valueMap = new WeakMap<HTMLElement, string>()
const cleanupMap = new WeakMap<HTMLElement, () => void>()

function createTooltip(text: string): HTMLElement {
  const el = document.createElement("div")
  el.textContent = text
  el.style.cssText = `
    position: fixed;
    z-index: 9999;
    pointer-events: none;
    font-size: 12px;
    line-height: 1.5;
    border-radius: 6px;
    padding: 4px 10px;
    max-width: 280px;
    word-break: break-word;
    opacity: 0;
    transition: opacity 0.15s ease;
    background: hsl(var(--popover));
    color: hsl(var(--popover-foreground));
    border: 1px solid hsl(var(--border));
    box-shadow: 0 4px 12px ${tooltipShadow()};
  `
  return el
}

function position(anchor: HTMLElement, tooltip: HTMLElement) {
  const anchorRect = anchor.getBoundingClientRect()
  const tooltipRect = tooltip.getBoundingClientRect()
  const gap = 6

  let top = anchorRect.top - tooltipRect.height - gap
  let left = anchorRect.left + (anchorRect.width - tooltipRect.width) / 2

  if (top < 4) {
    top = anchorRect.bottom + gap
  }
  left = Math.max(4, Math.min(left, window.innerWidth - tooltipRect.width - 4))

  tooltip.style.top = `${Math.round(top)}px`
  tooltip.style.left = `${Math.round(left)}px`
}

export const vTooltip: Directive<HTMLElement, string> = {
  mounted(el, binding) {
    valueMap.set(el, binding.value)
    el.removeAttribute("title")

    let tooltipEl: HTMLElement | null = null
    let showTimer: ReturnType<typeof setTimeout> | null = null
    let hideTimer: ReturnType<typeof setTimeout> | null = null
    let scrollCleanup: (() => void) | null = null

    const onEnter = () => {
      const text = valueMap.get(el)
      if (!text) return
      if (hideTimer) clearTimeout(hideTimer)
      if (showTimer) clearTimeout(showTimer)

      showTimer = setTimeout(() => {
        if (tooltipEl) return
        tooltipEl = createTooltip(text)
        document.body.appendChild(tooltipEl)
        position(el, tooltipEl)
        requestAnimationFrame(() => {
          if (tooltipEl) tooltipEl.style.opacity = "1"
        })

        const onScroll = () => onLeave()
        window.addEventListener("scroll", onScroll, { capture: true })
        scrollCleanup = () => window.removeEventListener("scroll", onScroll, { capture: true })
      }, 200)
    }

    const onLeave = () => {
      if (showTimer) clearTimeout(showTimer)
      if (hideTimer) clearTimeout(hideTimer)
      scrollCleanup?.()
      scrollCleanup = null
      if (tooltipEl) {
        tooltipEl.style.opacity = "0"
        hideTimer = setTimeout(() => {
          tooltipEl?.remove()
          tooltipEl = null
        }, 150)
      }
    }

    el.addEventListener("mouseenter", onEnter)
    el.addEventListener("mouseleave", onLeave)
    el.addEventListener("focus", onEnter)
    el.addEventListener("blur", onLeave)

    cleanupMap.set(el, () => {
      el.removeEventListener("mouseenter", onEnter)
      el.removeEventListener("mouseleave", onLeave)
      el.removeEventListener("focus", onEnter)
      el.removeEventListener("blur", onLeave)
      if (showTimer) clearTimeout(showTimer)
      if (hideTimer) clearTimeout(hideTimer)
      scrollCleanup?.()
      tooltipEl?.remove()
    })
  },

  updated(el, binding) {
    valueMap.set(el, binding.value)
  },

  unmounted(el) {
    cleanupMap.get(el)?.()
    cleanupMap.delete(el)
    valueMap.delete(el)
  },
}
