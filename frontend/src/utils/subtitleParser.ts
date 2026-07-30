export interface ParsedSegment {
  text: string
  start?: number
  end?: number
}

function parseSrtTime(ts: string): number {
  const m = ts.match(/(\d{2}):(\d{2}):(\d{2})[,.](\d{2,3})/)
  if (!m) return 0
  const h = parseInt(m[1]); const min = parseInt(m[2]); const s = parseInt(m[3])
  let ms = parseInt(m[4])
  if (ms < 100) ms *= 10
  return h * 3600 + min * 60 + s + ms / 1000
}

function parseAssTime(ts: string): number {
  const m = ts.match(/(\d+):(\d{2}):(\d{2})[.,](\d{2,3})/)
  if (!m) return 0
  const h = parseInt(m[1]); const min = parseInt(m[2]); const s = parseInt(m[3])
  let cs = parseInt(m[4])
  if (cs < 100) cs *= 10
  return h * 3600 + min * 60 + s + cs / 1000
}

function parseLrcTime(ts: string): number {
  const m = ts.match(/(\d{2}):(\d{2})(?:\.(\d{2,3}))?/)
  if (!m) return 0
  const min = parseInt(m[1]); const s = parseInt(m[2])
  let ms = m[3] ? parseInt(m[3]) : 0
  if (ms < 100 && m[3] && m[3].length === 2) ms *= 10
  return min * 60 + s + ms / 1000
}

// ── SR ──────────────────────────────────────────────────────────────────

export function parseSrtContent(content: string): ParsedSegment[] {
  const blocks = content.replace(/\r\n/g, "\n").split(/\n\n+/)
  const result: ParsedSegment[] = []
  for (const block of blocks) {
    const lines = block.split("\n")
    const timeLine = lines.find(l => l.includes("-->"))
    if (!timeLine) { result.push({ text: lines.filter(l => l.trim()).join(" ").trim() }); continue }
    const parts = timeLine.split("-->")
    if (parts.length < 2) { result.push({ text: lines.filter(l => l.trim()).join(" ").trim() }); continue }
    const start = parseSrtTime(parts[0].trim())
    const end = parseSrtTime(parts[1].trim())
    const text = lines.filter((l, i) => i > 0 && l !== timeLine).join(" ").trim()
    result.push({ text, start, end })
  }
  return result.filter(s => s.text)
}

// ── VTT ─────────────────────────────────────────────────────────────────

function parseVtt(content: string): ParsedSegment[] {
  const normalized = content.replace(/\r\n/g, "\n")
  const blocks = normalized.split(/\n\n+/)
  const result: ParsedSegment[] = []
  for (const block of blocks) {
    if (block.startsWith("WEBVTT") || block.startsWith("STYLE") || block.startsWith("NOTE")) continue
    const lines = block.split("\n")
    let timeLineIdx = -1
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes("-->")) { timeLineIdx = i; break }
    }
    if (timeLineIdx < 0) { result.push({ text: lines.filter(l => l.trim()).join(" ").trim() }); continue }
    const parts = lines[timeLineIdx].split("-->")
    if (parts.length < 2) { result.push({ text: lines.filter(l => l.trim()).join(" ").trim() }); continue }
    const startStr = parts[0].replace(/\s+.*$/, "").trim()
    const endStr = parts[1].trim().replace(/\s+.*$/, "").trim()
    const start = parseSrtTime(startStr)
    const end = parseSrtTime(endStr)
    const text = lines.slice(timeLineIdx + 1).join(" ").trim()
    result.push({ text, start, end })
  }
  return result.filter(s => s.text)
}

// ── ASS / SSA ───────────────────────────────────────────────────────────

function parseAss(content: string): ParsedSegment[] {
  const normalized = content.replace(/\r\n/g, "\n")
  const lines = normalized.split("\n")
  let inEvents = false
  let formatFields: string[] = []
  const result: ParsedSegment[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith("[")) {
      inEvents = trimmed.toLowerCase() === "[events]"
      continue
    }
    if (!inEvents) continue
    if (trimmed.toLowerCase().startsWith("format:")) {
      formatFields = trimmed.slice(7).split(",").map(f => f.trim().toLowerCase())
      continue
    }
    if (!trimmed.toLowerCase().startsWith("dialogue:")) continue
    const rest = trimmed.slice(9).trim()
    const parts: string[] = []
    let remaining = rest
    for (let i = 0; i < formatFields.length - 1; i++) {
      const idx = remaining.indexOf(",")
      if (idx >= 0) { parts.push(remaining.slice(0, idx)); remaining = remaining.slice(idx + 1) }
      else { parts.push(remaining); remaining = ""; break }
    }
    parts.push(remaining)
    let start = 0; let end = 0; let text = ""
    for (let i = 0; i < formatFields.length && i < parts.length; i++) {
      const f = formatFields[i]
      if (f === "start") start = parseAssTime(parts[i].trim())
      else if (f === "end") end = parseAssTime(parts[i].trim())
      else if (f === "text") text = parts[i].trim()
    }
    text = text.replace(/\{[^}]*\}/g, "").replace(/\\[Nn]/, " ").trim()
    if (text) result.push({ text, start, end })
  }
  return result
}

// ── STL ─────────────────────────────────────────────────────────────────

function parseStl(buffer: ArrayBuffer): ParsedSegment[] {
  const bytes = new Uint8Array(buffer)
  const DATA_START = 1024
  const TTI_SIZE = 128
  if (bytes.length < DATA_START) return []
  const f25 = 25.0
  const result: ParsedSegment[] = []
  for (let offset = DATA_START; offset + TTI_SIZE <= bytes.length; offset += TTI_SIZE) {
    const tci = [bytes[offset + 6], bytes[offset + 7], bytes[offset + 8], bytes[offset + 9]]
    const tco = [bytes[offset + 10], bytes[offset + 11], bytes[offset + 12], bytes[offset + 13]]
    if ((tci[3] & 0x80) || (tco[3] & 0x80)) continue
    const start = tci[0] * 3600 + tci[1] * 60 + tci[2] + tci[3] / f25
    const end = tco[0] * 3600 + tco[1] * 60 + tco[2] + tco[3] / f25
    if (start >= end && end > 0) continue
    const textBytes: number[] = []
    for (let i = 16; i < 112; i++) {
      const b = bytes[offset + i]
      if (b === 0 || b === 0x8A || b === 0x8F) break
      textBytes.push(b)
    }
    let text = ""
    try {
      text = new TextDecoder("iso-8859-1").decode(new Uint8Array(textBytes)).trim()
    } catch { continue }
    if (!text) continue
    result.push({ text, start, end })
  }
  return result
}

// ── LRC ─────────────────────────────────────────────────────────────────

function parseLrc(content: string): ParsedSegment[] {
  const lines = content.split("\n")
  const entries: { time: number; text: string }[] = []
  for (const line of lines) {
    const m = line.match(/^\[(\d{2}:\d{2}(?:\.\d{2,3})?)\](.*)/)
    if (!m) continue
    const time = parseLrcTime(m[1])
    const text = m[2].trim()
    if (text) entries.push({ time, text })
  }
  if (entries.length === 0) return []
  entries.sort((a, b) => a.time - b.time)
  const result: ParsedSegment[] = []
  for (let i = 0; i < entries.length; i++) {
    const start = entries[i].time
    const end = i + 1 < entries.length ? entries[i + 1].time : undefined
    result.push({ text: entries[i].text, start, end })
  }
  return result
}

// ── IMSC (TTML) ─────────────────────────────────────────────────────────

function extractImscText(el: Element): string {
  const parts: string[] = []
  for (const child of Array.from(el.childNodes)) {
    if (child.nodeType === 3) { parts.push(child.textContent ?? "") }
    else if (child.nodeType === 1) {
      const e = child as Element
      if (e.localName === "br" || e.nodeName === "br") { parts.push(" ") }
      else if (e.localName === "span" || e.nodeName === "span") { parts.push(extractImscText(e)) }
      else { parts.push(e.textContent ?? "") }
    }
  }
  return parts.join("")
}

function parseImsc(content: string): ParsedSegment[] {
  const parser = new DOMParser()
  let doc: XMLDocument
  try { doc = parser.parseFromString(content, "text/xml") } catch { return [] }
  if (doc.querySelector("parsererror")) return []
  const ps = doc.getElementsByTagNameNS("*", "p")
  if (ps.length === 0) return []
  const result: ParsedSegment[] = []
  for (const p of Array.from(ps)) {
    const begin = p.getAttribute("begin") ?? p.getAttributeNS("http://www.w3.org/ns/ttml", "begin") ?? ""
    const end = p.getAttribute("end") ?? p.getAttributeNS("http://www.w3.org/ns/ttml", "end") ?? ""
    if (!begin) continue
    const start = parseSrtTime(begin)
    const endTime = end ? parseSrtTime(end) : undefined
    const text = extractImscText(p).trim()
    if (text) result.push({ text, start, end: endTime })
  }
  return result
}

// ── Dispatchers ─────────────────────────────────────────────────────────

function parseTextSubtitle(content: string, ext: string): ParsedSegment[] {
  switch (ext) {
    case "srt": return parseSrtContent(content)
    case "vtt": return parseVtt(content)
    case "ass":
    case "ssa": return parseAss(content)
    case "lrc": return parseLrc(content)
    case "imsc": return parseImsc(content)
    default: return []
  }
}

/** 从 File 对象读取并解析为 ParsedSegment[]，自动识别格式 */
export async function parseSubtitleFile(file: File): Promise<ParsedSegment[]> {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? ""
  if (ext === "stl") {
    const buffer = await file.arrayBuffer()
    return parseStl(buffer)
  }
  const text = await file.text()
  return parseTextSubtitle(text, ext)
}
