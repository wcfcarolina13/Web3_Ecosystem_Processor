// Content script for DappRadar.com
// Extracts dapp data from rankings pages and individual dapp pages

(function() {
  'use strict';

  let isScanning = false;
  let scrapedProjects = [];

  // Send message to extension
  function sendMessage(type, data) {
    chrome.runtime.sendMessage({ type, ...data });
  }

  // Sleep helper
  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // Get current chain/protocol from URL (e.g., /rankings/protocol/aptos -> aptos)
  function getCurrentChain() {
    const match = window.location.pathname.match(/\/protocol\/([^/]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  // Check if we're on a rankings page
  function isRankingsPage() {
    return window.location.pathname.includes('/rankings');
  }

  // Check if we're on a dapp detail page
  function isDappPage() {
    return window.location.pathname.includes('/dapp/');
  }

  // Scroll to load all dapps (DappRadar uses infinite scroll)
  async function scrollToLoadAll() {
    const maxScrolls = 20;
    let lastCount = 0;
    let scrollCount = 0;
    let noChangeCount = 0;

    while (scrollCount < maxScrolls && noChangeCount < 3) {
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(800);

      const currentCount = document.querySelectorAll('a[href*="/dapp/"]').length;

      if (currentCount === lastCount) {
        noChangeCount++;
      } else {
        noChangeCount = 0;
      }

      lastCount = currentCount;
      scrollCount++;

      sendMessage('scrapeProgress', {
        current: currentCount,
        total: 100,
        message: `Loading dapps... (${currentCount} found)`
      });
    }

    window.scrollTo(0, 0);
    await sleep(300);
    return lastCount;
  }

  // Extract dapp data from rankings page DOM
  async function scrapeFromRankingsPage() {
    scrapedProjects = [];
    isScanning = true;

    try {
      const chain = getCurrentChain();

      sendMessage('scrapeProgress', {
        current: 0,
        total: 100,
        message: `Scraping ${chain || 'all'} dapps from DappRadar...`
      });

      // Scroll to load all dapps
      await scrollToLoadAll();

      // Find all dapp links
      const dappLinks = document.querySelectorAll('a[href*="/dapp/"]');
      const seen = new Set();
      const dappSlugs = [];

      dappLinks.forEach(link => {
        const href = link.getAttribute('href');
        const match = href.match(/\/dapp\/([^/]+)/);
        if (match && !seen.has(match[1])) {
          seen.add(match[1]);
          const name = link.textContent.trim();
          if (name && name.length > 0 && name.length < 100) {
            dappSlugs.push({
              slug: match[1],
              name: name
            });
          }
        }
      });

      const total = dappSlugs.length;
      sendMessage('scrapeProgress', {
        current: 0,
        total: total,
        message: `Found ${total} unique dapps. Processing...`
      });

      // Process each dapp - extract basic info from the list
      for (let i = 0; i < dappSlugs.length && isScanning; i++) {
        const dapp = dappSlugs[i];

        const project = {
          name: dapp.name,
          description: '',
          category: '',
          website: '',
          twitter: '',
          discord: '',
          chain: chain || 'Multiple',
          slug: dapp.slug,
          dappradarUrl: `https://dappradar.com/dapp/${dapp.slug}`
        };

        scrapedProjects.push(project);

        // Progress update every 10 items
        if (i % 10 === 0 || i === dappSlugs.length - 1) {
          sendMessage('scrapeProgress', {
            current: i + 1,
            total: total,
            message: `Processed: ${project.name}`
          });
        }
      }

      // Complete
      sendMessage('scrapeComplete', {
        data: scrapedProjects
      });

    } catch (error) {
      console.error('Scraping error:', error);
      sendMessage('scrapeError', {
        error: error.message
      });
    }

    isScanning = false;
  }

  // Scrape detailed data from a single dapp page
  async function scrapeFromDappPage() {
    scrapedProjects = [];
    isScanning = true;

    try {
      await sleep(1000); // Wait for page to fully load

      const project = {
        name: '',
        description: '',
        category: '',
        website: '',
        twitter: '',
        telegram: '',
        discord: '',
        github: '',
        chain: '',
        slug: ''
      };

      // Get slug from URL
      const slugMatch = window.location.pathname.match(/\/dapp\/([^/]+)/);
      if (slugMatch) project.slug = slugMatch[1];

      // Get name
      const nameEl = document.querySelector('h1');
      if (nameEl) project.name = nameEl.textContent.trim();

      // Get description
      const descEl = document.querySelector('p');
      if (descEl) {
        const text = descEl.textContent.trim();
        if (text.length > 20 && text.length < 500) {
          project.description = text;
        }
      }

      // Get category from breadcrumb or badge
      const categoryEls = document.querySelectorAll('[class*="badge"], [class*="category"], [class*="tag"]');
      categoryEls.forEach(el => {
        const text = el.textContent.trim();
        if (text && text.length < 30 && !project.category) {
          project.category = text;
        }
      });

      // Get website from "Open dapp" button or similar
      const openBtn = document.querySelector('a[target="_blank"][href*="http"]:not([href*="dappradar"]):not([href*="twitter"]):not([href*="t.me"]):not([href*="discord"]):not([href*="github"])');
      if (openBtn) project.website = openBtn.getAttribute('href');

      // Get social links
      document.querySelectorAll('a[href*="twitter.com"], a[href*="x.com"]').forEach(a => {
        const href = a.getAttribute('href');
        if (href && !project.twitter) {
          const match = href.match(/(?:twitter\.com|x\.com)\/([^/?]+)/);
          if (match) project.twitter = `@${match[1]}`;
        }
      });

      document.querySelectorAll('a[href*="t.me"]').forEach(a => {
        const href = a.getAttribute('href');
        if (href && !project.telegram) project.telegram = href;
      });

      document.querySelectorAll('a[href*="discord"]').forEach(a => {
        const href = a.getAttribute('href');
        if (href && !project.discord) project.discord = href;
      });

      document.querySelectorAll('a[href*="github.com"]').forEach(a => {
        const href = a.getAttribute('href');
        if (href && !project.github) project.github = href;
      });

      // Get chains from chain indicators
      const chainEls = document.querySelectorAll('[class*="chain"] img, [alt*="chain"], [title*="chain"]');
      const chains = [];
      chainEls.forEach(el => {
        const chain = el.getAttribute('alt') || el.getAttribute('title') || '';
        if (chain && !chains.includes(chain)) chains.push(chain);
      });
      project.chain = chains.join(', ') || 'Unknown';

      if (project.name) {
        scrapedProjects.push(project);
      }

      sendMessage('scrapeComplete', {
        data: scrapedProjects
      });

    } catch (error) {
      console.error('Scraping error:', error);
      sendMessage('scrapeError', {
        error: error.message
      });
    }

    isScanning = false;
  }

  // Main entry point
  async function startScraping() {
    if (isRankingsPage()) {
      console.log('[Ecosystem Scraper] Scraping DappRadar rankings page');
      return scrapeFromRankingsPage();
    } else if (isDappPage()) {
      console.log('[Ecosystem Scraper] Scraping DappRadar dapp detail page');
      return scrapeFromDappPage();
    } else {
      sendMessage('scrapeError', {
        error: 'Please navigate to a DappRadar rankings page (e.g., /rankings/protocol/aptos) or dapp page'
      });
    }
  }

  // Listen for messages from popup
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startScraping') {
      if (!isScanning) {
        startScraping();
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, error: 'Already scanning' });
      }
      return true;
    }

    if (message.action === 'stopScraping') {
      isScanning = false;
      sendResponse({ success: true });
      return true;
    }

    if (message.action === 'getStatus') {
      const chain = getCurrentChain();
      sendResponse({
        isScanning,
        projectCount: scrapedProjects.length,
        currentChain: chain,
        pageType: isRankingsPage() ? 'rankings' : (isDappPage() ? 'dapp' : 'other')
      });
      return true;
    }
  });

  // Log that content script is loaded
  const chain = getCurrentChain();
  console.log('[Ecosystem Scraper] DappRadar content script loaded');
  console.log('[Ecosystem Scraper] Current chain:', chain || 'None');
  console.log('[Ecosystem Scraper] Page type:', isRankingsPage() ? 'rankings' : (isDappPage() ? 'dapp detail' : 'other'));

})();
