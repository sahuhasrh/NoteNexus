const API = 'http://localhost:8000'
let capturing = false
let currentUrl = ''
let accumulatedTerms = []
const BLOCKED_TERM_WORDS = new Set([
  'subscribe',
  'subscribed',
  'like',
  'share',
  'comment',
  'comments',
  'notification',
  'notifications',
  'bell',
  'channel',
  'youtube',
  'video',
  'watch',
  'views',
  'playlist',
  'shorts',
  'live',
  'thanks',
  'thank',
  'follow',
  'download',
  'upload',
  'skip',
  'ad',
  'ads',
  'sponsor',
  'sponsored'
])

document.addEventListener('DOMContentLoaded', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
    currentUrl = tabs[0]?.url || ''
    loadStoredTerms()
  })

  document.getElementById('toggleBtn').addEventListener('click', toggleCapture)
  document.getElementById('summarizeBtn').addEventListener('click', takeSummary)
  document.getElementById('askBtn').addEventListener('click', askQuestion)
  document.getElementById('timelineBtn').addEventListener('click', loadTimeline)

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'OCR_RESULT') {
      displayOCRResult(msg.payload)
    }
  })
})

function storageKeyForTerms() {
  return `notesnexus_terms_${currentUrl || 'unknown'}`
}

function sendToActiveTab(message) {
  chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
    if (!tabs[0]?.id) return
    chrome.tabs.sendMessage(tabs[0].id, message)
  })
}

function injectIntoActiveTab() {
  return new Promise(resolve => {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (!tabs[0]?.id) {
        resolve()
        return
      }
      chrome.scripting.executeScript(
        { target: { tabId: tabs[0].id }, files: ['inject.js'] },
        () => resolve()
      )
    })
  })
}

async function toggleCapture() {
  capturing = !capturing
  const btn = document.getElementById('toggleBtn')
  btn.textContent = capturing ? 'Stop NotesNexus' : 'Start NotesNexus'
  btn.style.background = capturing ? '#e53e3e' : '#4285F4'

  if (capturing) {
    await injectIntoActiveTab()
    sendToActiveTab({ type: 'START' })
  } else {
    sendToActiveTab({ type: 'STOP' })
  }
}

function displayOCRResult(payload) {
  const el = document.getElementById('ocrOutput')
  if (!el) return
  el.textContent = `Slide ${payload.slide_number} [${payload.timestamp}]: ${(payload.full_text || '').slice(0, 100)}...`

  addTerms(payload.entities || [])
}

function cleanTerm(term) {
  return (term || '').replace(/\s+/g, ' ').trim()
}

function isUsefulTerm(term) {
  const normalized = term.toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim()
  if (!normalized || normalized.length < 3) return false
  return !normalized.split(' ').some(word => BLOCKED_TERM_WORDS.has(word))
}

function addTerms(entities) {
  const newTerms = entities
    .map(e => cleanTerm(e.entity))
    .filter(isUsefulTerm)

  let changed = false
  newTerms.forEach(term => {
    const exists = accumulatedTerms.some(existing => existing.toLowerCase() === term.toLowerCase())
    if (!exists) {
      accumulatedTerms.push(term)
      changed = true
    }
  })

  if (accumulatedTerms.length > 60) {
    accumulatedTerms = accumulatedTerms.slice(-60)
    changed = true
  }

  if (changed) {
    chrome.storage.local.set({ [storageKeyForTerms()]: accumulatedTerms })
  }
  renderTerms()
}

function loadStoredTerms() {
  chrome.storage.local.get([storageKeyForTerms()], result => {
    accumulatedTerms = (result[storageKeyForTerms()] || []).filter(isUsefulTerm)
    chrome.storage.local.set({ [storageKeyForTerms()]: accumulatedTerms })
    renderTerms()
  })
}

function renderTerms() {
  const entEl = document.getElementById('entities')
  if (!entEl) return

  if (accumulatedTerms.length) {
    entEl.textContent = accumulatedTerms.join(', ')
  } else {
    entEl.textContent = 'No lecture key terms captured yet.'
  }
}

async function takeSummary() {
  const btn = document.getElementById('summarizeBtn')
  btn.textContent = 'Generating...'
  btn.disabled = true

  try {
    const res = await fetch(`${API}/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_url: currentUrl })
    })
    const data = await res.json()
    displaySummary(data)
  } catch (e) {
    document.getElementById('summaryOutput').textContent = 'Error: ' + e.message
  } finally {
    btn.textContent = 'Summarize Notes'
    btn.disabled = false
  }
}

function displaySummary(data) {
  const el = document.getElementById('summaryOutput')
  if (!el) return
  if (data.error) {
    el.textContent = data.error
    return
  }

  el.innerHTML = `
    <strong>Summary:</strong><br>${data.summary || ''}<br><br>
    <strong>Key Concepts:</strong><br>${(data.key_concepts || []).join(', ')}<br><br>
    <strong>Notes:</strong><br>${(data.bullet_notes || []).map(n => '&bull; ' + n).join('<br>')}
  `
}

async function askQuestion() {
  const q = document.getElementById('questionInput').value.trim()
  if (!q) return

  const btn = document.getElementById('askBtn')
  btn.textContent = 'Asking...'
  btn.disabled = true

  try {
    const res = await fetch(`${API}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, page_url: currentUrl })
    })
    const data = await res.json()
    document.getElementById('answerOutput').textContent = data.answer || data.error || ''
  } catch (e) {
    document.getElementById('answerOutput').textContent = 'Error: ' + e.message
  } finally {
    btn.textContent = 'Ask'
    btn.disabled = false
  }
}

async function loadTimeline() {
  try {
    const res = await fetch(`${API}/timeline?page_url=${encodeURIComponent(currentUrl)}`)
    const data = await res.json()
    const el = document.getElementById('timelineOutput')
    if (!el) return
    el.innerHTML = (data.timeline || [])
      .map(s => `<div><strong>${s.timestamp}</strong> - Slide ${s.slide_number}: ${s.text}</div>`)
      .join('')
  } catch (e) {
    console.error(e)
  }
}
