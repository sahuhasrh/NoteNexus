let lastHash = null

function computeHash(bitmap) {
  const small = new OffscreenCanvas(32, 32)
  const ctx = small.getContext('2d')
  ctx.drawImage(bitmap, 0, 0, 32, 32)
  const pixels = ctx.getImageData(0, 0, 32, 32).data
  const gray = []

  for (let i = 0; i < pixels.length; i += 4) {
    gray.push(0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2])
  }

  const mean = gray.reduce((sum, value) => sum + value, 0) / gray.length
  return gray.map(value => value > mean ? 1 : 0).join('')
}

function hashDistance(left, right) {
  let diff = 0
  for (let i = 0; i < left.length; i++) {
    if (left[i] !== right[i]) diff++
  }
  return diff
}

function isDifferent(bitmap) {
  const hash = computeHash(bitmap)
  if (!lastHash) {
    lastHash = hash
    return true
  }

  if (hashDistance(hash, lastHash) > 10) {
    lastHash = hash
    return true
  }

  return false
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer)
  const chunkSize = 0x8000
  let binary = ''

  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize)
    binary += String.fromCharCode.apply(null, chunk)
  }

  return btoa(binary)
}

async function compressFrame(bitmap) {
  const width = Math.max(1, Math.round(bitmap.width * 0.5))
  const height = Math.max(1, Math.round(bitmap.height * 0.5))
  const canvas = new OffscreenCanvas(width, height)
  const ctx = canvas.getContext('2d')
  ctx.drawImage(bitmap, 0, 0, width, height)
  const blob = await canvas.convertToBlob({
    type: 'image/jpeg',
    quality: 0.85
  })
  const buffer = await blob.arrayBuffer()
  return {
    imageData: arrayBufferToBase64(buffer),
    width,
    height
  }
}

async function sendToBackend(frameData, compressed) {
  const res = await fetch('http://localhost:8000/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      imageData: compressed.imageData,
      page_url: frameData.pageUrl,
      timestamp: frameData.timestamp
    })
  })

  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || res.statusText)
  }
  return data
}

class RequestQueue {
  constructor() {
    this.processing = false
    this.pending = null
  }

  async enqueue(frameData) {
    if (this.processing) {
      if (this.pending?.bitmap) this.pending.bitmap.close()
      this.pending = frameData
      return
    }

    this.processing = true
    let current = frameData

    try {
      while (current) {
        await this.process(current)
        current = this.pending
        this.pending = null
      }
    } finally {
      this.processing = false
    }
  }

  async process(frameData) {
    try {
      if (!isDifferent(frameData.bitmap)) {
        self.postMessage({ type: 'unchanged' })
        return
      }

      const compressed = await compressFrame(frameData.bitmap)
      const data = await sendToBackend(frameData, compressed)

      self.postMessage({
        type: 'result',
        data,
        rect: frameData.rect,
        sourceWidth: compressed.width,
        sourceHeight: compressed.height,
        timestamp: frameData.timestamp
      })
    } catch (error) {
      self.postMessage({
        type: 'error',
        error: error.message || String(error)
      })
    } finally {
      frameData.bitmap.close()
    }
  }

  reset() {
    lastHash = null
    if (this.pending?.bitmap) this.pending.bitmap.close()
    this.pending = null
  }
}

const queue = new RequestQueue()

self.onmessage = (event) => {
  const message = event.data || {}
  if (message.type === 'reset') {
    queue.reset()
    return
  }
  if (message.type === 'frame') {
    queue.enqueue(message)
  }
}
