const DB_NAME = "qwen-tts-batch-audio"
const DB_VERSION = 1
const STORE_NAME = "audio"

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE_NAME)) {
        req.result.createObjectStore(STORE_NAME)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export const audioCacheDB = {
  async put(id: string, blob: Blob): Promise<void> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const txn = db.transaction(STORE_NAME, "readwrite")
      txn.objectStore(STORE_NAME).put(blob, id)
      txn.oncomplete = () => resolve()
      txn.onerror = () => reject(txn.error)
    })
  },

  async get(id: string): Promise<Blob | undefined> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const txn = db.transaction(STORE_NAME, "readonly")
      const req = txn.objectStore(STORE_NAME).get(id)
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
  },

  async remove(id: string): Promise<void> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const txn = db.transaction(STORE_NAME, "readwrite")
      txn.objectStore(STORE_NAME).delete(id)
      txn.oncomplete = () => resolve()
      txn.onerror = () => reject(txn.error)
    })
  },

  async clear(): Promise<void> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const txn = db.transaction(STORE_NAME, "readwrite")
      txn.objectStore(STORE_NAME).clear()
      txn.oncomplete = () => resolve()
      txn.onerror = () => reject(txn.error)
    })
  },

  putRefAudio(rowId: string, blob: Blob): Promise<void> {
    return this.put(`ref:${rowId}`, blob)
  },

  getRefAudio(rowId: string): Promise<Blob | undefined> {
    return this.get(`ref:${rowId}`)
  },

  removeRefAudio(rowId: string): Promise<void> {
    return this.remove(`ref:${rowId}`)
  },

  async clearRefAudio(): Promise<void> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const txn = db.transaction(STORE_NAME, "readwrite")
      const req = txn.objectStore(STORE_NAME).openCursor()
      req.onsuccess = () => {
        const cursor = req.result
        if (cursor) {
          if (typeof cursor.key === "string" && cursor.key.startsWith("ref:")) {
            cursor.delete()
          }
          cursor.continue()
        } else {
          resolve()
        }
      }
      req.onerror = () => reject(req.error)
    })
  },

  async putComposeAudio(blob: Blob): Promise<void> {
    return this.put("compose:audio", blob)
  },
  async getComposeAudio(): Promise<Blob | undefined> {
    return this.get("compose:audio")
  },
  async putComposeZip(blob: Blob): Promise<void> {
    return this.put("compose:zip", blob)
  },
  async getComposeZip(): Promise<Blob | undefined> {
    return this.get("compose:zip")
  },
  async putComposeSrt(srt: string): Promise<void> {
    return this.put("compose:srt", new Blob([srt], { type: "text/plain" }))
  },
  async getComposeSrt(): Promise<string | undefined> {
    const blob = await this.get("compose:srt")
    if (!blob) return undefined
    return blob.text()
  },
  async removeCompose(): Promise<void> {
    await this.remove("compose:audio")
    await this.remove("compose:zip")
    await this.remove("compose:srt")
  },
}
