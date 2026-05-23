chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "ocr_result" && message.payload) {
    chrome.storage.local.set({
      latest_ocr_result: message.payload,
      latest_ocr_at: Date.now(),
    });
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
