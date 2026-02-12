// Popup script for Ecosystem Scraper extension

// Dynamic site detection — no hardcoded list needed.
// The scraper engine matches sites via config/sites/*.js configs.
async function detectSite(tab) {
  try {
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'getSiteConfig' });
    return response && response.matched ? { id: response.siteId, name: response.siteName } : null;
  } catch (e) {
    return null;
  }
}

let scrapedData = [];
let isScanning = false;
let chainsConfig = [];
let selectedChain = null; // null = auto-detect

// DOM elements
const siteNameEl = document.getElementById('site-name');
const projectCountEl = document.getElementById('project-count');
const progressContainer = document.getElementById('progress-container');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const copyCsvBtn = document.getElementById('copy-csv-btn');
const downloadCsvBtn = document.getElementById('download-csv-btn');
const copyJsonBtn = document.getElementById('copy-json-btn');
const mainContent = document.getElementById('main-content');
const unsupportedContent = document.getElementById('unsupported-content');
const toast = document.getElementById('toast');
const chainSelect = document.getElementById('chain-select');

// Load chains configuration
async function loadChainsConfig() {
  try {
    const url = chrome.runtime.getURL('config/chains.json');
    const response = await fetch(url);
    const data = await response.json();
    chainsConfig = data.chains || [];
    populateChainDropdown();
  } catch (error) {
    console.warn('Could not load chains.json:', error);
    // Extension still works, just without chain selection
  }
}

// Populate chain selector dropdown
function populateChainDropdown() {
  // Keep the "Auto-detect" option, add chains
  chainsConfig.forEach(chain => {
    const option = document.createElement('option');
    option.value = chain.id;
    option.textContent = chain.name;
    chainSelect.appendChild(option);
  });

  // Restore last selected chain
  chrome.storage.local.get('selectedChainId', (result) => {
    if (result.selectedChainId) {
      chainSelect.value = result.selectedChainId;
      selectedChain = chainsConfig.find(c => c.id === result.selectedChainId) || null;
    }
  });
}

// Get the selected chain name (for CSV export and display)
function getSelectedChainName() {
  if (selectedChain) return selectedChain.name;
  return '';  // Empty string = auto-detect from content script
}

// Initialize popup
async function init() {
  await loadChainsConfig();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Ask the engine if this site is supported (dynamic detection)
  const site = await detectSite(tab);

  if (site) {
    siteNameEl.textContent = site.name;
    mainContent.style.display = 'block';
    unsupportedContent.style.display = 'none';

    // Load any previously scraped data for this tab
    const stored = await chrome.storage.local.get(`data_${tab.id}`);
    if (stored[`data_${tab.id}`]) {
      scrapedData = stored[`data_${tab.id}`];
      updateCount(scrapedData.length);
      enableExportButtons();
    }
  } else {
    mainContent.style.display = 'none';
    unsupportedContent.style.display = 'block';
  }
}

// Update project count display
function updateCount(count) {
  projectCountEl.textContent = count;
}

// Update progress bar
function updateProgress(current, total, message) {
  progressContainer.classList.add('active');
  const percent = Math.round((current / total) * 100);
  progressFill.style.width = `${percent}%`;
  progressText.textContent = message || `Processing ${current} of ${total}...`;
}

// Show toast notification
function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}

// Enable export buttons
function enableExportButtons() {
  copyCsvBtn.disabled = false;
  downloadCsvBtn.disabled = false;
  copyJsonBtn.disabled = false;
}

// Convert data to CSV — 27-column team standard
function toCSV(data) {
  if (data.length === 0) return '';

  // CSV headers matching the 27-column team standard (lib/columns.py)
  const headers = [
    'Project Name',
    'Suspect USDT support?',
    'Skip',
    'Added',
    'Web3 but no stablecoin',
    'General Stablecoin Adoption',
    'To be Added',
    'Processed?',
    'In Admin',
    'TG/TON appstore (no main URL)',
    'Final Status',
    'Website',
    'X Link',
    'X Handle',
    'Telegram',
    'Category',
    'Release Date',
    'Product Status',
    'The Grid Status',
    'Profile Name',
    'Root ID',
    'Matched URL',
    'Matched via',
    'Chain',
    'Source',
    'Notes',
    'Evidence URLs'
  ];

  const chainName = getSelectedChainName();
  const sourceSite = siteNameEl.textContent || '';

  // DeFi categories that likely involve stablecoin/USDT support
  const defiCategories = new Set([
    'CEX', 'Dexes', 'Lending', 'Derivatives', 'Bridge', 'RWA',
    'DeFi', 'Exchanges', 'Yield', 'Liquid Staking', 'Payments',
    'Launchpad'
  ]);

  const rows = data.map(item => {
    const category = item.category || '';
    const isDefi = defiCategories.has(category);
    const twitter = item.twitter || '';
    const handleClean = twitter.replace(/^@/, '');
    const xLink = handleClean ? `https://x.com/${handleClean}` : '';
    const notes = [
      category ? `${category} from ${sourceSite}` : '',
      item.description || ''
    ].filter(Boolean).join(' - ');

    return [
      item.name || '',                          // Project Name
      isDefi ? 'TRUE' : '',                     // Suspect USDT support?
      '',                                        // Skip
      '',                                        // Added
      isDefi ? '' : 'TRUE',                     // Web3 but no stablecoin
      '',                                        // General Stablecoin Adoption
      '',                                        // To be Added
      '',                                        // Processed?
      '',                                        // In Admin
      '',                                        // TG/TON appstore (no main URL)
      '',                                        // Final Status
      item.website || '',                        // Website
      xLink,                                     // X Link
      twitter,                                   // X Handle
      item.telegram || '',                       // Telegram
      category,                                  // Category
      '',                                        // Release Date
      '',                                        // Product Status
      '',                                        // The Grid Status
      '',                                        // Profile Name
      '',                                        // Root ID
      '',                                        // Matched URL
      '',                                        // Matched via
      item.chain || chainName || '',             // Chain
      sourceSite,                                // Source
      notes,                                     // Notes
      ''                                         // Evidence URLs
    ].map(val => {
      // Escape CSV values
      if (typeof val === 'string' && (val.includes(',') || val.includes('"') || val.includes('\n'))) {
        return `"${val.replace(/"/g, '""')}"`;
      }
      return val;
    }).join(',');
  });

  return [headers.join(','), ...rows].join('\n');
}

// Start scraping
async function startScraping() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  isScanning = true;
  startBtn.style.display = 'none';
  stopBtn.style.display = 'block';
  scrapedData = [];
  updateCount(0);
  updateProgress(0, 100, 'Initializing...');

  try {
    // Build message with optional chain override
    const message = { action: 'startScraping' };
    if (selectedChain) {
      message.chain = selectedChain;  // Pass full chain config object
    }

    // Send message to content script to start scraping
    const response = await chrome.tabs.sendMessage(tab.id, message);

    if (response && response.success) {
      showToast('Scraping started!');
    }
  } catch (error) {
    console.error('Error starting scrape:', error);
    showToast('Error: Could not connect to page. Try refreshing.', true);
    stopScraping();
  }
}

// Stop scraping
async function stopScraping() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  isScanning = false;
  startBtn.style.display = 'block';
  stopBtn.style.display = 'none';
  progressContainer.classList.remove('active');

  try {
    await chrome.tabs.sendMessage(tab.id, { action: 'stopScraping' });
  } catch (error) {
    console.error('Error stopping scrape:', error);
  }
}

// Copy CSV to clipboard
async function copyCSV() {
  const csv = toCSV(scrapedData);
  await navigator.clipboard.writeText(csv);
  showToast('CSV copied to clipboard!');
}

// Download CSV file
function downloadCSV() {
  const csv = toCSV(scrapedData);
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const timestamp = new Date().toISOString().split('T')[0];
  const siteName = siteNameEl.textContent.toLowerCase().replace(/\s+/g, '_');
  const chainName = getSelectedChainName().toLowerCase().replace(/\s+/g, '_') || 'all';

  const a = document.createElement('a');
  a.href = url;
  a.download = `${chainName}_${siteName}_ecosystem_${timestamp}.csv`;
  a.click();

  URL.revokeObjectURL(url);
  showToast('CSV downloaded!');
}

// Copy JSON to clipboard
async function copyJSON() {
  await navigator.clipboard.writeText(JSON.stringify(scrapedData, null, 2));
  showToast('JSON copied to clipboard!');
}

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'scrapeProgress') {
    updateProgress(message.current, message.total, message.message);
    updateCount(message.current);
  } else if (message.type === 'scrapeComplete') {
    scrapedData = message.data;
    updateCount(scrapedData.length);
    progressContainer.classList.remove('active');
    startBtn.style.display = 'block';
    stopBtn.style.display = 'none';
    enableExportButtons();
    showToast(`Scraped ${scrapedData.length} projects!`);

    // Store data
    chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      chrome.storage.local.set({ [`data_${tab.id}`]: scrapedData });
    });
  } else if (message.type === 'scrapeError') {
    showToast(message.error, true);
    stopScraping();
  }
});

// Chain selector change handler
chainSelect.addEventListener('change', (e) => {
  const chainId = e.target.value;
  if (chainId) {
    selectedChain = chainsConfig.find(c => c.id === chainId) || null;
  } else {
    selectedChain = null;  // Auto-detect
  }
  // Persist selection
  chrome.storage.local.set({ selectedChainId: chainId });
});

// Event listeners
startBtn.addEventListener('click', startScraping);
stopBtn.addEventListener('click', stopScraping);
copyCsvBtn.addEventListener('click', copyCSV);
downloadCsvBtn.addEventListener('click', downloadCSV);
copyJsonBtn.addEventListener('click', copyJSON);

// Initialize
init();
