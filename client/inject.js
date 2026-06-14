(() => {
  if (window.__notesNexusLoaded) return
  window.__notesNexusLoaded = true

  let overlayContainer = null
  let slideNumber = 0
  let captureInterval = 2000
  const minInterval = 1000
  const maxInterval = 8000
  let running = false
  let captureTimer = null
  let worker = null

  function getVideo() {
    return document.querySelector('video')
  }

  function ensureContainer() {
    if (!overlayContainer) {
      overlayContainer = document.createElement('div')
      overlayContainer.id = 'notesnexus-overlays'
      overlayContainer.style.cssText = `
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        pointer-events: none;
        z-index: 9998;
      `
      document.body.appendChild(overlayContainer)
    }
  }

  function clearOverlays() {
    if (overlayContainer) {
      overlayContainer.innerHTML = ''
    }
  }

  function drawOverlays(lines, rect, sourceWidth, sourceHeight) {
    clearOverlays()

    const scaleX = rect.width / sourceWidth
    const scaleY = rect.height / sourceHeight

    lines.forEach(line => {
      const b = line.bounding_box
      const div = document.createElement('div')
      div.style.cssText = `
        position: fixed;
        left: ${rect.left + b.x * scaleX}px;
        top: ${rect.top + b.y * scaleY}px;
        width: ${b.width * scaleX}px;
        height: ${b.height * scaleY}px;
        color: transparent;
        background: transparent;
        user-select: text;
        -webkit-user-select: text;
        cursor: text;
        font-size: ${Math.max(b.height * scaleY * 0.85, 8)}px;
        font-family: monospace;
        white-space: nowrap;
        overflow: hidden;
        pointer-events: all;
        line-height: 1;
        z-index: 9999;
      `
      div.textContent = line.text
      overlayContainer.appendChild(div)
    })
  }

  function getVideoTimestamp(video) {
    const secs = Math.floor(video.currentTime)
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  function getPlainRect(rect) {
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height
    }
  }

  function ensureWorker() {
    if (worker) return worker

    worker = new Worker(chrome.runtime.getURL('ocr-worker.js'))
    worker.onmessage = (event) => {
      const message = event.data || {}

      if (message.type === 'unchanged') {
        captureInterval = Math.min(captureInterval * 1.3, maxInterval)
        return
      }

      if (message.type === 'error') {
        console.error('NotesNexus worker error:', message.error)
        return
      }

      if (message.type !== 'result') return

      const data = message.data || {}
      captureInterval = minInterval
      slideNumber = data.slide_number || slideNumber + 1

      drawOverlays(
        data.lines || [],
        message.rect,
        data.image_width || message.sourceWidth,
        data.image_height || message.sourceHeight
      )

      chrome.runtime.sendMessage({
        type: 'OCR_RESULT',
        payload: {
          lines: data.lines || [],
          entities: data.entities || [],
          full_text: data.full_text || '',
          slide_number: slideNumber,
          timestamp: message.timestamp,
          page_url: window.location.href
        }
      })
    }

    worker.onerror = (error) => {
      console.error('NotesNexus worker failed:', error.message || error)
    }

    return worker
  }

  async function captureAndEnqueue() {
    const video = getVideo()
    if (!video || video.readyState < 2) return

    const rect = video.getBoundingClientRect()
    ensureContainer()

    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720
    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

    const bitmap = await createImageBitmap(canvas)
    ensureWorker().postMessage(
      {
        type: 'frame',
        bitmap,
        rect: getPlainRect(rect),
        sourceWidth: canvas.width,
        sourceHeight: canvas.height,
        pageUrl: window.location.href,
        timestamp: getVideoTimestamp(video)
      },
      [bitmap]
    )
  }

  function startCapture() {
    if (running) return
    running = true
    ensureWorker()

    async function loop() {
      if (!running) return
      try {
        await captureAndEnqueue()
      } catch (error) {
        console.error('NotesNexus capture error:', error)
      }
      captureTimer = setTimeout(loop, captureInterval)
    }
    loop()
  }

  function stopCapture() {
    running = false
    if (captureTimer) clearTimeout(captureTimer)
    clearOverlays()
    captureInterval = 2000
    if (worker) {
      worker.postMessage({ type: 'reset' })
    }
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'START') startCapture()
    if (msg.type === 'STOP') stopCapture()
  })
})()
