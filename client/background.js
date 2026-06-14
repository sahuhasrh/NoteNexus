chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if ((message.type === "ocr_result" || message.type === "OCR_RESULT") && message.payload) {
    const pageUrl = message.payload.page_url || (sender.tab && sender.tab.url) || "unknown";
    const termsKey = `notesnexus_terms_${pageUrl}`;
    const incomingTerms = (message.payload.entities || [])
      .map((entity) => (entity.entity || "").replace(/\s+/g, " ").trim())
      .filter(Boolean);

    chrome.storage.local.set({
      latest_ocr_result: message.payload,
      latest_ocr_at: Date.now(),
    });

    if (incomingTerms.length) {
      chrome.storage.local.get([termsKey], (result) => {
        let terms = result[termsKey] || [];
        incomingTerms.forEach((term) => {
          const exists = terms.some((existing) => existing.toLowerCase() === term.toLowerCase());
          if (!exists) terms.push(term);
        });
        if (terms.length > 60) terms = terms.slice(-60);
        chrome.storage.local.set({ [termsKey]: terms });
      });
    }
    return;
  }

  if (!message.myPopupIsOpen) return;

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tabId = tabs[0] && tabs[0].id;
    if (!tabId) return;

    chrome.scripting.executeScript({
      target: { tabId },
      files: ["inject.js"],
    });
  });
});
