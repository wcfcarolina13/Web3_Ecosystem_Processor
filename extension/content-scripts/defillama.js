// Content script for DefiLlama.com
// Extracts protocol data from __NEXT_DATA__ or DefiLlama API

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

  // Get current chain from URL (e.g., /chain/Aptos -> Aptos)
  function getCurrentChain() {
    const match = window.location.pathname.match(/\/chain\/([^/]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

  // Main scraping function - uses __NEXT_DATA__ for chain pages
  async function scrapeFromNextData() {
    scrapedProjects = [];
    isScanning = true;

    try {
      const chain = getCurrentChain();

      // Check for __NEXT_DATA__
      const nextDataEl = document.getElementById('__NEXT_DATA__');
      if (!nextDataEl) {
        throw new Error('__NEXT_DATA__ not found. This may not be a DefiLlama page.');
      }

      const nextData = JSON.parse(nextDataEl.textContent);
      const pageProps = nextData?.props?.pageProps;

      if (!pageProps) {
        throw new Error('pageProps not found in __NEXT_DATA__');
      }

      // Get protocols from page data
      let protocols = pageProps.protocols || [];

      if (protocols.length === 0) {
        throw new Error('No protocols found in page data. Try the /chain/[ChainName] page.');
      }

      const total = protocols.length;
      sendMessage('scrapeProgress', {
        current: 0,
        total: total,
        message: `Found ${total} protocols${chain ? ` for ${chain}` : ''}`
      });

      // Process each protocol
      for (let i = 0; i < protocols.length && isScanning; i++) {
        const item = protocols[i];

        const project = {
          name: item.name || '',
          description: '', // Not available in chain page data
          category: item.category || '',
          website: '', // Need to fetch from API
          twitter: '', // Need to fetch from API
          discord: '',
          chain: chain || (item.chains ? item.chains.join(', ') : ''),
          tvl: item.tvl?.default?.tvl || item.tvl || 0,
          slug: item.slug || ''
        };

        // Only add if we got a name
        if (project.name) {
          scrapedProjects.push(project);
        }

        // Send progress update every 10 items
        if (i % 10 === 0 || i === protocols.length - 1) {
          sendMessage('scrapeProgress', {
            current: scrapedProjects.length,
            total: total,
            message: `Processing: ${project.name}`
          });
        }

        // Small delay to not freeze UI
        if (i % 20 === 0) {
          await sleep(10);
        }
      }

      // Now enrich with API data (URL, Twitter, etc.)
      await enrichWithApiData();

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

  // Enrich protocols with data from DefiLlama API
  async function enrichWithApiData() {
    sendMessage('scrapeProgress', {
      current: scrapedProjects.length,
      total: scrapedProjects.length,
      message: 'Enriching with API data (Twitter, URLs)...'
    });

    try {
      const response = await fetch('https://api.llama.fi/protocols');
      if (!response.ok) {
        console.warn('Could not fetch API data for enrichment');
        return;
      }

      const allProtocols = await response.json();

      // Create lookup by slug and name
      const bySlug = {};
      const byName = {};
      for (const p of allProtocols) {
        if (p.slug) bySlug[p.slug.toLowerCase()] = p;
        if (p.name) byName[p.name.toLowerCase()] = p;
      }

      // Enrich our scraped projects
      for (const project of scrapedProjects) {
        const apiData = bySlug[project.slug?.toLowerCase()] ||
                        byName[project.name?.toLowerCase()];

        if (apiData) {
          project.website = apiData.url || '';
          project.twitter = apiData.twitter ? `@${apiData.twitter}` : '';
          project.description = apiData.description || '';
          project.logo = apiData.logo || '';
        }
      }

      sendMessage('scrapeProgress', {
        current: scrapedProjects.length,
        total: scrapedProjects.length,
        message: 'Enrichment complete!'
      });

    } catch (error) {
      console.warn('API enrichment failed:', error.message);
    }
  }

  // Alternative: Scrape directly from API (for all chains)
  async function scrapeFromApi(chainFilter = null) {
    scrapedProjects = [];
    isScanning = true;

    try {
      sendMessage('scrapeProgress', {
        current: 0,
        total: 100,
        message: 'Fetching protocols from DefiLlama API...'
      });

      const response = await fetch('https://api.llama.fi/protocols');
      if (!response.ok) {
        throw new Error(`API request failed: ${response.status}`);
      }

      const allProtocols = await response.json();

      // Filter by chain if specified
      let protocols = allProtocols;
      if (chainFilter) {
        protocols = allProtocols.filter(p =>
          p.chains && p.chains.some(c =>
            c.toLowerCase() === chainFilter.toLowerCase()
          )
        );
      }

      const total = protocols.length;
      sendMessage('scrapeProgress', {
        current: 0,
        total: total,
        message: `Found ${total} protocols${chainFilter ? ` for ${chainFilter}` : ''}`
      });

      // Process each protocol
      for (let i = 0; i < protocols.length && isScanning; i++) {
        const item = protocols[i];

        const project = {
          name: item.name || '',
          description: item.description || '',
          category: item.category || '',
          website: item.url || '',
          twitter: item.twitter ? `@${item.twitter}` : '',
          discord: '',
          chain: chainFilter || (item.chains ? item.chains.join(', ') : ''),
          tvl: item.tvl || 0,
          slug: item.slug || '',
          logo: item.logo || ''
        };

        // Only add if we got a name
        if (project.name) {
          scrapedProjects.push(project);
        }

        // Send progress update every 20 items
        if (i % 20 === 0 || i === protocols.length - 1) {
          sendMessage('scrapeProgress', {
            current: scrapedProjects.length,
            total: total,
            message: `Processing: ${project.name}`
          });
        }

        // Small delay to not freeze UI
        if (i % 50 === 0) {
          await sleep(10);
        }
      }

      // Complete
      sendMessage('scrapeComplete', {
        data: scrapedProjects
      });

    } catch (error) {
      console.error('API scraping error:', error);
      sendMessage('scrapeError', {
        error: error.message
      });
    }

    isScanning = false;
  }

  // Main entry point
  async function startScraping(useApi = false) {
    const chain = getCurrentChain();

    if (useApi || !chain) {
      // Use API directly (works anywhere on DefiLlama)
      console.log('[Ecosystem Scraper] Using DefiLlama API');
      return scrapeFromApi(chain);
    } else {
      // Use __NEXT_DATA__ for chain pages (faster, but less data)
      console.log('[Ecosystem Scraper] Using __NEXT_DATA__ + API enrichment');
      return scrapeFromNextData();
    }
  }

  // Listen for messages from popup
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startScraping') {
      if (!isScanning) {
        // Default to API mode for better data
        startScraping(true);
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
        hasNextData: !!document.getElementById('__NEXT_DATA__')
      });
      return true;
    }
  });

  // Log that content script is loaded
  const chain = getCurrentChain();
  console.log('[Ecosystem Scraper] DefiLlama content script loaded');
  console.log('[Ecosystem Scraper] Current chain:', chain || 'None (will scrape all)');
  console.log('[Ecosystem Scraper] __NEXT_DATA__ available:', !!document.getElementById('__NEXT_DATA__'));

})();
