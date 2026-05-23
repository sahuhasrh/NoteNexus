const API_BASE = "http://localhost:8000";

function getActiveTabUrl() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      resolve(tabs[0] && tabs[0].url ? tabs[0].url : "");
    });
  });
}

function appendAccumulatedText(newText) {
  chrome.storage.local.get(["accumulated_text"], (result) => {
    const existing = result.accumulated_text || "";
    const combined = existing ? `${existing} ${newText}` : newText;
    chrome.storage.local.set({ accumulated_text: combined.trim() });
  });
}

function applyOcrResult(result) {
  if (!result || !result.lines) return;

  const datestring = new Date()
    .toLocaleString()
    .replace(",", "")
    .replace(/:.. /, " ");

  const notes = document.getElementById("notes-list");
  let newNote = `<p><strong>${datestring}</strong></p>`;
  for (const line of result.lines) {
    newNote += `<li>${line.text}</li>`;
  }
  newNote += "<br>";
  notes.innerHTML = newNote + notes.innerHTML;

  if (result.full_text) {
    appendAccumulatedText(result.full_text);
  }

  const entities = document.getElementById("entities-list");
  let newEntities = `<p><strong>${datestring}</strong></p>`;
  for (const line of result.entities || []) {
    const wiki_link = `https://en.wikipedia.org/wiki/${line.entity}`;
    newEntities += `<li><a class="link" href="${wiki_link}" target="_blank">${line.entity}</a> (${line.label})</li><br>`;
  }
  newEntities += "<br><br>";
  entities.innerHTML = newEntities + entities.innerHTML;

  chrome.storage.local.set({ notes_html: notes.innerHTML });
  chrome.storage.local.set({ entities_html: entities.innerHTML });
}

async function loadSavedNotes(pageUrl) {
  if (!pageUrl) return;

  try {
    const res = await fetch(
      `${API_BASE}/notes?page_url=${encodeURIComponent(pageUrl)}`
    );
    const data = await res.json();
    if (!data.notes || data.notes.length === 0) return;

    const latest = data.notes[0];
    const notes = document.getElementById("notes-list");
    const entities = document.getElementById("entities-list");
    const summary = document.getElementById("summary");

    if (latest.raw_text) {
      notes.innerHTML = `<li>${latest.raw_text}</li>` + notes.innerHTML;
    }

    if (latest.entities && latest.entities.length) {
      let entitiesHtml = "";
      for (const line of latest.entities) {
        const wiki_link = `https://en.wikipedia.org/wiki/${line["entity"]}`;
        entitiesHtml += `<li><a class="link" href="${wiki_link}" target="_blank">${line["entity"]}</a> (${line["label"]})</li><br>`;
      }
      entities.innerHTML = entitiesHtml + entities.innerHTML;
    }

    if (
      latest.summary &&
      !latest.summary.includes("Summary unavailable") &&
      !latest.summary.includes("gemini-1.5-flash")
    ) {
      summary.innerHTML = `<p>${latest.summary}</p>` + summary.innerHTML;
    }

    chrome.storage.local.set({ accumulated_text: latest.raw_text || "" });
  } catch (err) {
    console.error("Failed to load notes:", err);
  }
}

document.addEventListener(
  "DOMContentLoaded",
  async () => {
    const pageUrl = await getActiveTabUrl();
    await loadSavedNotes(pageUrl);

    chrome.storage.local.get(["notes_html"], function (result) {
      var notes = document.getElementById("notes-list");
      if (result["notes_html"] != null) {
        notes.innerHTML = result["notes_html"];
      }
    });
    chrome.storage.local.get(["entities_html"], function (result) {
      var entities = document.getElementById("entities-list");
      if (result["entities_html"] != null) {
        entities.innerHTML = result["entities_html"];
      }
    });
    chrome.storage.local.get(["summary_html"], function (result) {
      var summary = document.getElementById("summary");
      const html = result["summary_html"];
      if (html != null && !html.includes("Summary unavailable") && !html.includes("gemini-1.5-flash")) {
        summary.innerHTML = html;
      } else if (html != null) {
        chrome.storage.local.remove(["summary_html"]);
      }
    });

    chrome.storage.local.get(["latest_ocr_result"], (r) => {
      if (r.latest_ocr_result) applyOcrResult(r.latest_ocr_result);
    });

    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes.latest_ocr_result) return;
      applyOcrResult(changes.latest_ocr_result.newValue);
    });

    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "ocr_result" && msg.payload) {
        applyOcrResult(msg.payload);
      }
      document.getElementById("capture-btn").innerHTML = "Start NotesNexus";
    });

    function hello() {
      chrome.storage.local.set({ notesnexus_active: true });
      chrome.runtime.sendMessage({ myPopupIsOpen: true });
    }

    document.getElementById("capture-btn").addEventListener("click", hello);

    document.getElementById("clear-btn").addEventListener("click", () => {
      chrome.storage.local.remove(
        ["notes_html", "entities_html", "summary_html", "accumulated_text"],
        () => {
          document.getElementById("notes-list").innerHTML = "";
          document.getElementById("entities-list").innerHTML = "";
          document.getElementById("summary").innerHTML = "";
          document.getElementById("ask-answer").innerHTML = "";
          alert("Cleared popup cache. Click Take Notes for a fresh summary.");
        }
      );
    });

    document.getElementById("stop-btn").addEventListener("click", () => {
      chrome.storage.local.set({ notesnexus_active: false });
      alert("NotesNexus paused. Click Start NotesNexus to resume, or refresh the page to clear overlays.");
    });

    document.getElementById("take-notes-btn").addEventListener("click", async () => {
      const takeNotesBtn = document.getElementById("take-notes-btn");
      const url = await getActiveTabUrl();
      takeNotesBtn.innerHTML = "Indexing...";

      chrome.storage.local.get(["accumulated_text"], async (result) => {
        const text = result.accumulated_text || "";
        if (!text.trim()) {
          takeNotesBtn.innerHTML = "Take Notes";
          alert("No text captured yet. Start NotesNexus on a video first.");
          return;
        }

        try {
          await fetch(`${API_BASE}/index_notes`, {
            method: "POST",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ text, page_url: url }),
          });

          takeNotesBtn.innerHTML = "Summarizing...";
          const summarizeRes = await fetch(`${API_BASE}/summarize`, {
            method: "POST",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ text, page_url: url }),
          });
          const summarizeData = await summarizeRes.json();

          const summary = document.getElementById("summary");
          if (!summarizeRes.ok || summarizeData.error) {
            alert(`Summary failed: ${summarizeData.error || summarizeRes.statusText}`);
          } else if (summarizeData.summary) {
            const note = summarizeData.used_fallback
              ? "<p><em>(Local summary — Gemini quota full)</em></p>"
              : "";
            summary.innerHTML =
              `<p><strong>${new Date().toLocaleString()}</strong></p>` +
              note +
              summarizeData.summary.replace(/\n/g, "<br>") +
              `<br>` +
              summary.innerHTML;
            chrome.storage.local.set({ summary_html: summary.innerHTML });
          }

          takeNotesBtn.innerHTML = "Take Notes";
          alert(`Indexed ${text.split(/\s+/).length} words for Q&A.`);
        } catch (err) {
          takeNotesBtn.innerHTML = "Take Notes";
          console.error(err);
          alert("Failed to index notes. Is the Flask server running?");
        }
      });
    });

    document.getElementById("ask-btn").addEventListener("click", async () => {
      const questionInput = document.getElementById("question-input");
      const askBtn = document.getElementById("ask-btn");
      const loading = document.getElementById("ask-loading");
      const answerDiv = document.getElementById("ask-answer");
      const question = questionInput.value.trim();

      if (!question) return;

      const url = await getActiveTabUrl();
      askBtn.disabled = true;
      loading.style.display = "block";
      loading.textContent = "Thinking... (first time may take 1-2 min)";
      answerDiv.innerHTML = "";

      const stored = await new Promise((resolve) => {
        chrome.storage.local.get(["accumulated_text"], (r) => resolve(r));
      });
      const lectureText = stored.accumulated_text || "";

      if (!lectureText.trim()) {
        answerDiv.innerHTML =
          "<p>Capture text first (Start NotesNexus), wait for notes, then click Take Notes or Ask again.</p>";
        askBtn.disabled = false;
        loading.style.display = "none";
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/ask`, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ question, page_url: url, text: lectureText }),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          answerDiv.innerHTML = `<p><strong>Error:</strong> ${data.error || res.statusText}</p>`;
        } else {
          const ans = (data.answer || "No answer returned.").replace(/\n/g, "<br>");
          answerDiv.innerHTML = `<div>${ans}</div>`;
        }
      } catch (err) {
        answerDiv.innerHTML = `<p>Failed to get an answer: ${err.message}. Is Flask running?</p>`;
        console.error(err);
      } finally {
        askBtn.disabled = false;
        loading.style.display = "none";
        loading.textContent = "Loading...";
      }
    });

    var a = document.getElementById("notes-div");
    var b = document.getElementById("entities-div");
    var c = document.getElementById("summary-div");

    const notesButton = document.getElementById("notesbtn");
    notesButton.addEventListener("click", () => {
      a.style.display = "block";
      b.style.display = c.style.display = "none";
    });

    const entitiesButton = document.getElementById("topicsbtn");
    entitiesButton.addEventListener("click", () => {
      b.style.display = "block";
      a.style.display = c.style.display = "none";
    });

    const summaryButton = document.getElementById("summarybtn");
    summaryButton.addEventListener("click", () => {
      c.style.display = "block";
      a.style.display = b.style.display = "none";
    });

    const button = document.getElementById("capture-btn");
    button.addEventListener(
      "click",
      () => {
        button.innerHTML = "Capturing...";
      },
      false
    );
  },
  false
);
