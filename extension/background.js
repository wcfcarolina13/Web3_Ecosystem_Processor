// Background service worker for Ecosystem Scraper extension

// Listen for installation
chrome.runtime.onInstalled.addListener(() => {
  console.log('Ecosystem Scraper extension installed');
});

// Handle messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Forward messages to popup if needed
  if (message.type === 'scrapeProgress' || message.type === 'scrapeComplete' || message.type === 'scrapeError') {
    // The popup listens for these messages directly
    return;
  }

  // Handle any background tasks here
  if (message.action === 'log') {
    console.log('[Ecosystem Scraper]', message.data);
  }
});

// Clean up stored data when tab closes
chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.local.remove(`data_${tabId}`);
});
