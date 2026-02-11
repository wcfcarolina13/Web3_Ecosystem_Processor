// Content script for CoinGecko.com
// Extracts coin/project data from ecosystem and category pages

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

  // Get current category/chain from URL
  function getCurrentCategory() {
    // URLs like /en/categories/aptos-ecosystem or /en/chains/aptos
    const categoryMatch = window.location.pathname.match(/\/categories\/([^/]+)/);
    const chainMatch = window.location.pathname.match(/\/chains\/([^/]+)/);
    return categoryMatch ? categoryMatch[1] : (chainMatch ? chainMatch[1] : null);
  }

  // Check if we're on an ecosystem/category page
  function isEcosystemPage() {
    return window.location.pathname.includes('/categories/') ||
           window.location.pathname.includes('/chains/') ||
           window.location.pathname.includes('/ecosystem');
  }

  // Check if we're on a coin detail page
  function isCoinPage() {
    return window.location.pathname.match(/\/coins\/[^/]+$/);
  }

  // Scroll to load all coins (CoinGecko may use pagination or lazy loading)
  async function scrollToLoadAll() {
    const maxScrolls = 15;
    let lastCount = 0;
    let scrollCount = 0;
    let noChangeCount = 0;

    while (scrollCount < maxScrolls && noChangeCount < 3) {
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(600);

      // Count coin links
      const currentCount = document.querySelectorAll('a[href*="/coins/"]').length;

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
        message: `Loading coins... (${currentCount} found)`
      });
    }

    window.scrollTo(0, 0);
    await sleep(300);
    return lastCount;
  }

  // Extract coins from ecosystem/category page
  async function scrapeFromEcosystemPage(chainOverride = null) {
    scrapedProjects = [];
    isScanning = true;

    try {
      const category = getCurrentCategory();

      sendMessage('scrapeProgress', {
        current: 0,
        total: 100,
        message: `Scraping ${category || 'ecosystem'} from CoinGecko...`
      });

      // Try to scroll to load more
      await scrollToLoadAll();

      // Find all coin links in the table/list
      const coinLinks = document.querySelectorAll('a[href*="/coins/"]');
      const seen = new Set();
      const coins = [];

      coinLinks.forEach(link => {
        const href = link.getAttribute('href');
        const match = href.match(/\/coins\/([^/?#]+)/);
        if (match && !seen.has(match[1])) {
          seen.add(match[1]);

          // Get coin name - usually in the link text or nearby
          let name = link.textContent.trim();

          // If it's an image or icon, try to get name from parent row
          if (!name || name.length < 2) {
            const row = link.closest('tr') || link.closest('[class*="coin"]') || link.parentElement;
            if (row) {
              const nameEl = row.querySelector('[class*="name"], td:nth-child(2), span');
              if (nameEl) name = nameEl.textContent.trim();
            }
          }

          // Clean up name (remove ticker symbols like "APT")
          name = name.replace(/\s+\$?[A-Z]{2,10}$/, '').trim();

          if (name && name.length > 1 && name.length < 100) {
            coins.push({
              slug: match[1],
              name: name
            });
          }
        }
      });

      const total = coins.length;
      sendMessage('scrapeProgress', {
        current: 0,
        total: total,
        message: `Found ${total} unique coins. Processing...`
      });

      // Process each coin
      for (let i = 0; i < coins.length && isScanning; i++) {
        const coin = coins[i];

        const project = {
          name: coin.name,
          description: '',
          category: category || 'Cryptocurrency',
          website: '',
          twitter: '',
          discord: '',
          chain: chainOverride || (category ? category.replace('-ecosystem', '').replace(/-/g, ' ') : ''),
          slug: coin.slug,
          coingeckoUrl: `https://www.coingecko.com/en/coins/${coin.slug}`
        };

        scrapedProjects.push(project);

        // Progress update
        if (i % 10 === 0 || i === coins.length - 1) {
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

  // Scrape detailed data from a single coin page
  async function scrapeFromCoinPage() {
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
      const slugMatch = window.location.pathname.match(/\/coins\/([^/]+)/);
      if (slugMatch) project.slug = slugMatch[1];

      // Get name from h1 or title
      const nameEl = document.querySelector('h1, [class*="coin-name"]');
      if (nameEl) project.name = nameEl.textContent.trim().split(/\s+/)[0]; // First word usually is name

      // Get description
      const descEl = document.querySelector('[class*="description"], [itemprop="description"]');
      if (descEl) project.description = descEl.textContent.trim().substring(0, 500);

      // Get category from tags/badges
      const categoryEls = document.querySelectorAll('[class*="badge"], [class*="tag"], [class*="category"]');
      categoryEls.forEach(el => {
        const text = el.textContent.trim();
        if (text && text.length < 30 && !project.category) {
          project.category = text;
        }
      });

      // Get website - look for official links section
      const websiteLink = document.querySelector('a[href][rel="nofollow"][target="_blank"]:not([href*="twitter"]):not([href*="t.me"]):not([href*="discord"]):not([href*="github"])');
      if (websiteLink) project.website = websiteLink.getAttribute('href');

      // Get social links
      const twitterLink = document.querySelector('a[href*="twitter.com"], a[href*="x.com"]');
      if (twitterLink) {
        const href = twitterLink.getAttribute('href');
        const match = href.match(/(?:twitter\.com|x\.com)\/([^/?]+)/);
        if (match) project.twitter = `@${match[1]}`;
      }

      const telegramLink = document.querySelector('a[href*="t.me"]');
      if (telegramLink) project.telegram = telegramLink.getAttribute('href');

      const discordLink = document.querySelector('a[href*="discord"]');
      if (discordLink) project.discord = discordLink.getAttribute('href');

      const githubLink = document.querySelector('a[href*="github.com"]');
      if (githubLink) project.github = githubLink.getAttribute('href');

      // Get chain from blockchain info
      const chainEl = document.querySelector('[class*="blockchain"], [class*="chain"], [class*="network"]');
      if (chainEl) project.chain = chainEl.textContent.trim();

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
  async function startScraping(chainOverride = null) {
    if (isEcosystemPage()) {
      console.log('[Ecosystem Scraper] Scraping CoinGecko ecosystem/category page' + (chainOverride ? ` (chain override: ${chainOverride})` : ''));
      return scrapeFromEcosystemPage(chainOverride);
    } else if (isCoinPage()) {
      console.log('[Ecosystem Scraper] Scraping CoinGecko coin detail page');
      return scrapeFromCoinPage();
    } else {
      sendMessage('scrapeError', {
        error: 'Please navigate to a CoinGecko ecosystem page (e.g., /en/categories/aptos-ecosystem) or coin page'
      });
    }
  }

  // Listen for messages from popup
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startScraping') {
      if (!isScanning) {
        // Accept optional chain override from popup
        const chainOverride = message.chain ? message.chain.name : null;
        startScraping(chainOverride);
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
      const category = getCurrentCategory();
      sendResponse({
        isScanning,
        projectCount: scrapedProjects.length,
        currentCategory: category,
        pageType: isEcosystemPage() ? 'ecosystem' : (isCoinPage() ? 'coin' : 'other')
      });
      return true;
    }
  });

  // Log that content script is loaded
  const category = getCurrentCategory();
  console.log('[Ecosystem Scraper] CoinGecko content script loaded');
  console.log('[Ecosystem Scraper] Current category:', category || 'None');
  console.log('[Ecosystem Scraper] Page type:', isEcosystemPage() ? 'ecosystem/category' : (isCoinPage() ? 'coin detail' : 'other'));

})();
