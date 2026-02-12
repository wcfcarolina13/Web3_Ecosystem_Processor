// Universal Scraper Engine v2.0
// Config-driven ecosystem directory scraping — one engine, many sites.
// Site configs are loaded dynamically from config/sites/registry.json.

(function() {
  'use strict';

  // ==================== STATE ====================
  let isScanning = false;
  let scrapedProjects = [];
  let siteConfigs = [];       // Loaded from registry
  let activeSiteConfig = null; // Current page's matched config
  let configsLoaded = false;

  // ==================== UTILITIES ====================

  function sendMessage(type, data) {
    chrome.runtime.sendMessage({ type, ...data });
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function reportProgress(current, total, message) {
    sendMessage('scrapeProgress', { current, total, message });
  }

  // Navigate dot-path like 'props.pageProps.protocols' into an object
  function getByPath(obj, path) {
    if (!path) return obj;
    return path.split('.').reduce((o, k) => (o != null ? o[k] : undefined), obj);
  }

  // Convert glob pattern to regex: *.example.com/* → regex
  function matchUrlPattern(url, pattern) {
    const escaped = pattern
      .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
      .replace(/\*\*/g, '<<DBLSTAR>>')
      .replace(/\*/g, '[^/]*')
      .replace(/<<DBLSTAR>>/g, '.*');
    return new RegExp('^' + escaped + '$').test(url);
  }

  // ==================== BUILT-IN TRANSFORMS ====================

  const TRANSFORMS = {
    prefixAt: (val) => {
      if (!val) return '';
      const clean = String(val).replace(/^@/, '').trim();
      return clean ? `@${clean}` : '';
    },
    joinComma: (val) => Array.isArray(val) ? val.join(', ') : (val || ''),
    trim: (val) => (val || '').trim(),
    firstWord: (val) => (val || '').trim().split(/\s+/)[0] || '',
    stripTicker: (val) => (val || '').replace(/\s+\$?[A-Z]{2,10}$/, '').trim(),
    objectKeys: (val) => {
      if (val && typeof val === 'object' && !Array.isArray(val)) {
        return Object.values(val).join(', ');
      }
      return Array.isArray(val) ? val.join(', ') : (val || '');
    }
  };

  // ==================== FIELD MAPPING ====================

  function mapFields(sourceItem, fieldMap, context) {
    const result = {};
    for (const [targetField, mapping] of Object.entries(fieldMap)) {
      if (mapping === null || mapping === undefined) continue;

      // Special token: use detected chain
      if (mapping === '$chain') {
        result[targetField] = context.chain || '';
        continue;
      }

      // Simple string: direct field lookup
      if (typeof mapping === 'string') {
        result[targetField] = getByPath(sourceItem, mapping) || '';
        continue;
      }

      // Object with field + transform
      if (typeof mapping === 'object' && mapping.field) {
        let val = getByPath(sourceItem, mapping.field);
        if (mapping.transform) {
          if (typeof mapping.transform === 'function') {
            val = mapping.transform(val);
          } else if (TRANSFORMS[mapping.transform]) {
            val = TRANSFORMS[mapping.transform](val);
          }
        }
        result[targetField] = val || '';
        continue;
      }

      // Function: custom extraction
      if (typeof mapping === 'function') {
        result[targetField] = mapping(sourceItem, context) || '';
      }
    }
    return result;
  }

  // ==================== SCROLL TO LOAD ====================

  async function scrollToLoadAll(config) {
    const maxScrolls = config.maxScrolls || 20;
    const delay = config.delay || 600;
    const countSelector = config.countSelector;
    const noChangeThreshold = config.noChangeThreshold || 3;

    let lastCount = 0;
    let scrollCount = 0;
    let noChangeCount = 0;

    while (scrollCount < maxScrolls && noChangeCount < noChangeThreshold && isScanning) {
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(delay);

      const currentCount = countSelector
        ? document.querySelectorAll(countSelector).length
        : document.body.scrollHeight;

      if (currentCount === lastCount) {
        noChangeCount++;
      } else {
        noChangeCount = 0;
      }

      lastCount = currentCount;
      scrollCount++;
      reportProgress(typeof currentCount === 'number' && countSelector ? currentCount : scrollCount,
                     100, `Loading content... (${countSelector ? currentCount + ' found' : 'scroll ' + scrollCount})`);
    }

    window.scrollTo(0, 0);
    await sleep(300);
    return lastCount;
  }

  // ==================== SOCIAL LINK EXTRACTION ====================

  function extractSocialLinks(rootEl) {
    const root = rootEl || document;
    const result = { twitter: '', telegram: '', discord: '', github: '' };

    const twitterLink = root.querySelector('a[href*="twitter.com"], a[href*="x.com"]');
    if (twitterLink) {
      const href = twitterLink.getAttribute('href');
      const match = href.match(/(?:twitter\.com|x\.com)\/([^/?]+)/);
      if (match && match[1] !== 'share' && match[1] !== 'intent') {
        result.twitter = `@${match[1]}`;
      }
    }

    const tgLink = root.querySelector('a[href*="t.me"]');
    if (tgLink) result.telegram = tgLink.getAttribute('href');

    const discordLink = root.querySelector('a[href*="discord"]');
    if (discordLink) result.discord = discordLink.getAttribute('href');

    const githubLink = root.querySelector('a[href*="github.com"]');
    if (githubLink) result.github = githubLink.getAttribute('href');

    return result;
  }

  // ==================== STRATEGY: JSON EMBEDDED ====================

  async function executeJsonEmbedded(strategyConfig, context) {
    const projects = [];
    const src = strategyConfig.source;
    let rawData;

    if (src.type === 'element') {
      const el = document.querySelector(src.selector);
      if (!el) throw new Error(`Element "${src.selector}" not found on page.`);
      rawData = JSON.parse(el.textContent);
    } else if (src.type === 'global_var') {
      // Content scripts can't read page globals directly — use a bridge
      rawData = await readPageGlobal(src.globalVar, src.waitMs || 2000);
    }

    // Navigate to the array
    let items = getByPath(rawData, strategyConfig.jsonPath);
    if (!items) throw new Error(`No data found at path "${strategyConfig.jsonPath}"`);

    // Handle map-style data: {slug: {profile}} → [{slug, ...profile}]
    if (strategyConfig.isMap && typeof items === 'object' && !Array.isArray(items)) {
      items = Object.entries(items).map(([key, val]) => ({ _mapKey: key, ...val }));
    }

    if (!Array.isArray(items)) throw new Error('Extracted data is not an array');

    // Apply filter
    if (strategyConfig.filter) {
      items = items.filter(strategyConfig.filter);
    }

    const total = items.length;
    reportProgress(0, total, `Found ${total} projects. Processing...`);

    for (let i = 0; i < items.length && isScanning; i++) {
      const item = items[i];
      const project = mapFields(item, strategyConfig.fieldMap, context);

      // Set chain if not mapped
      if (!project.chain) project.chain = context.chain || '';

      // Only add if we got a name
      if (project.name) {
        projects.push(project);
      }

      if (i % (strategyConfig.progressBatchSize || 10) === 0 || i === items.length - 1) {
        reportProgress(projects.length, total, `Processing: ${project.name || '...'}`);
      }
      if (i % (strategyConfig.uiYieldBatchSize || 20) === 0) {
        await sleep(10);
      }
    }

    return projects;
  }

  // ==================== STRATEGY: DOM SCROLL ====================

  async function executeDomScroll(strategyConfig, context) {
    const projects = [];

    // Scroll to load
    if (strategyConfig.scroll) {
      await scrollToLoadAll(strategyConfig.scroll);
    }

    // Custom extraction function (for non-standard DOM like flip cards)
    if (strategyConfig.customExtract) {
      const elements = document.querySelectorAll(strategyConfig.itemSelector);
      const total = elements.length;
      reportProgress(0, total, `Found ${total} elements. Extracting...`);

      const seen = new Set();
      for (let i = 0; i < elements.length && isScanning; i++) {
        const extracted = strategyConfig.customExtract(elements[i]);
        if (extracted && extracted.name) {
          if (!strategyConfig.deduplicate || !seen.has(extracted.name)) {
            seen.add(extracted.name);
            extracted.chain = extracted.chain || context.chain || '';
            projects.push(extracted);
          }
        }
        if (i % 5 === 0) {
          reportProgress(projects.length, total, `Scraped: ${extracted?.name || 'Unknown'}`);
        }
      }
      return projects;
    }

    // Standard link-based extraction
    const links = document.querySelectorAll(strategyConfig.itemSelector);
    const seen = new Set();
    const items = [];

    links.forEach(link => {
      const href = link.getAttribute('href');
      if (!href) return;

      const slugRegex = new RegExp(strategyConfig.slugFromHref);
      const match = href.match(slugRegex);
      if (!match || (strategyConfig.deduplicate !== false && seen.has(match[1]))) return;
      seen.add(match[1]);

      // Extract name
      let name = '';
      if (strategyConfig.nameExtraction === 'textContent') {
        name = link.textContent.trim();
      } else if (typeof strategyConfig.nameExtraction === 'string' && strategyConfig.nameExtraction.startsWith('selector:')) {
        const sel = strategyConfig.nameExtraction.slice(9);
        const row = link.closest('tr') || link.closest('[class*="coin"]') || link.parentElement;
        if (row) {
          const nameEl = row.querySelector(sel);
          if (nameEl) name = nameEl.textContent.trim();
        }
      }

      // Fallback: try parent row for name
      if ((!name || name.length < 2) && strategyConfig.nameFallbackSelector) {
        const row = link.closest('tr') || link.closest('[class*="coin"]') || link.parentElement;
        if (row) {
          const nameEl = row.querySelector(strategyConfig.nameFallbackSelector);
          if (nameEl) name = nameEl.textContent.trim();
        }
      }

      // Apply name transform
      if (name && strategyConfig.nameTransform && TRANSFORMS[strategyConfig.nameTransform]) {
        name = TRANSFORMS[strategyConfig.nameTransform](name);
      }

      if (name && name.length > 1 && (!strategyConfig.nameMaxLength || name.length < strategyConfig.nameMaxLength)) {
        items.push({ slug: match[1], name });
      }
    });

    const total = items.length;
    reportProgress(0, total, `Found ${total} unique items. Processing...`);

    for (let i = 0; i < items.length && isScanning; i++) {
      const item = items[i];
      const project = {
        name: item.name,
        slug: item.slug,
        chain: context.chain || '',
        ...(strategyConfig.staticFields || {}),
      };

      // Computed extra fields (e.g., dappradarUrl from slug)
      if (strategyConfig.extraFields) {
        for (const [field, fn] of Object.entries(strategyConfig.extraFields)) {
          project[field] = typeof fn === 'function' ? fn(item.slug) : fn;
        }
      }

      projects.push(project);

      if (i % 10 === 0 || i === items.length - 1) {
        reportProgress(i + 1, total, `Processed: ${project.name}`);
      }
    }

    return projects;
  }

  // ==================== STRATEGY: DOM DETAIL ====================

  async function executeDomDetail(strategyConfig, context) {
    if (strategyConfig.waitMs) await sleep(strategyConfig.waitMs);

    const project = { chain: context.chain || '' };

    // Extract fields from selectors
    for (const [field, config] of Object.entries(strategyConfig.fields || {})) {
      if (config.fromUrl) {
        const match = window.location.pathname.match(new RegExp(config.fromUrl));
        if (match) project[field] = match[1];
        continue;
      }

      const el = document.querySelector(config.selector);
      if (!el) continue;

      let value = '';
      if (config.extract === 'textContent') {
        value = el.textContent.trim();
        if (config.firstWord) value = value.split(/\s+/)[0] || '';
      } else if (config.extract === 'href') {
        value = el.getAttribute('href') || '';
      }

      if (config.minLength && value.length < config.minLength) continue;
      if (config.maxLength) value = value.substring(0, config.maxLength);

      project[field] = value;
    }

    // Generic social link extraction
    if (strategyConfig.socialLinks) {
      const socials = extractSocialLinks();
      Object.assign(project, socials);
    }

    // Chain detection from DOM
    if (strategyConfig.chainSelector) {
      const chainEls = document.querySelectorAll(strategyConfig.chainSelector);
      const chains = [];
      chainEls.forEach(el => {
        const chain = el.getAttribute('alt') || el.getAttribute('title') || el.textContent.trim();
        if (chain && !chains.includes(chain)) chains.push(chain);
      });
      if (chains.length) project.chain = chains.join(', ');
    }

    return project.name ? [project] : [];
  }

  // ==================== STRATEGY: API FETCH ====================

  async function executeApiFetch(strategyConfig, context) {
    const projects = [];

    reportProgress(0, 100, `Fetching data from API...`);

    const response = await fetch(strategyConfig.url);
    if (!response.ok) throw new Error(`API request failed: ${response.status}`);

    let data = await response.json();
    let items = getByPath(data, strategyConfig.responsePath) || data;

    // Filter by chain
    if (strategyConfig.chainFilter && context.chain) {
      const { field, matchType } = strategyConfig.chainFilter;
      const chainLower = context.chain.toLowerCase();
      items = items.filter(item => {
        const val = getByPath(item, field);
        if (matchType === 'array_includes') {
          return Array.isArray(val) && val.some(c => c.toLowerCase() === chainLower);
        }
        if (matchType === 'equals') return (val || '').toLowerCase() === chainLower;
        if (matchType === 'contains') return (val || '').toLowerCase().includes(chainLower);
        return true;
      });
    }

    const total = items.length;
    reportProgress(0, total, `Found ${total} items. Processing...`);

    for (let i = 0; i < items.length && isScanning; i++) {
      const item = items[i];
      const project = mapFields(item, strategyConfig.fieldMap, context);
      if (!project.chain) project.chain = context.chain || '';

      if (project.name) {
        projects.push(project);
      }

      if (i % (strategyConfig.progressBatchSize || 20) === 0 || i === items.length - 1) {
        reportProgress(projects.length, total, `Processing: ${project.name || '...'}`);
      }
      if (i % (strategyConfig.uiYieldBatchSize || 50) === 0) {
        await sleep(10);
      }
    }

    return projects;
  }

  // ==================== ENRICHMENT ====================

  async function executeEnrichment(enrichConfig, projects) {
    reportProgress(projects.length, projects.length, 'Enriching with API data...');

    try {
      const response = await fetch(enrichConfig.apiUrl);
      if (!response.ok) { console.warn('Enrichment API failed'); return; }

      const allData = await response.json();

      // Build lookups
      const lookups = {};
      for (const key of (enrichConfig.lookupBy || ['slug', 'name'])) {
        lookups[key] = {};
        for (const item of allData) {
          if (item[key]) lookups[key][String(item[key]).toLowerCase()] = item;
        }
      }

      // Enrich each project
      for (const project of projects) {
        let apiData = null;
        for (const key of (enrichConfig.lookupBy || ['slug', 'name'])) {
          const val = project[key];
          if (val && lookups[key][String(val).toLowerCase()]) {
            apiData = lookups[key][String(val).toLowerCase()];
            break;
          }
        }

        if (apiData && enrichConfig.fieldMap) {
          const enriched = mapFields(apiData, enrichConfig.fieldMap, {});
          // Only fill empty fields (don't overwrite existing data)
          for (const [field, value] of Object.entries(enriched)) {
            if (!project[field] && value) {
              project[field] = value;
            }
          }
        }
      }

      reportProgress(projects.length, projects.length, 'Enrichment complete!');
    } catch (error) {
      console.warn('Enrichment failed:', error.message);
    }
  }

  // ==================== FALLBACK DATA ====================

  function applyFallbackData(fallbackConfig, projects) {
    for (const project of projects) {
      for (const [field, lookupTable] of Object.entries(fallbackConfig)) {
        if (!project[field] && lookupTable[project.name]) {
          project[field] = lookupTable[project.name];
        }
      }
    }
  }

  // ==================== PAGE GLOBAL BRIDGE ====================

  // Content scripts can't read page's window globals directly.
  // Inject a tiny script to read it and post back via postMessage.
  function readPageGlobal(varName, waitMs) {
    return new Promise((resolve, reject) => {
      const callbackId = '__ecoScraper_' + Date.now();

      function handler(event) {
        if (event.data && event.data.type === callbackId) {
          window.removeEventListener('message', handler);
          resolve(event.data.payload);
        }
      }
      window.addEventListener('message', handler);

      // Inject script into page context
      const script = document.createElement('script');
      script.textContent = `
        (async function() {
          let data = window.${varName};
          if (!data) {
            await new Promise(r => setTimeout(r, ${waitMs}));
            data = window.${varName};
          }
          window.postMessage({ type: '${callbackId}', payload: data }, '*');
        })();
      `;
      document.documentElement.appendChild(script);
      script.remove();

      // Timeout fallback
      setTimeout(() => {
        window.removeEventListener('message', handler);
        reject(new Error(`Global variable "${varName}" not found after ${waitMs}ms`));
      }, waitMs + 1000);
    });
  }

  // ==================== CHAIN DETECTION ====================

  function detectChainFromUrl(siteConfig) {
    if (!siteConfig.chainFromUrl) return null;

    const cfg = siteConfig.chainFromUrl;
    // Support multiple regex patterns (e.g., CoinGecko has /categories/ and /chains/)
    const patterns = Array.isArray(cfg) ? cfg : [cfg];

    for (const pattern of patterns) {
      const match = window.location.pathname.match(new RegExp(pattern.regex));
      if (match) {
        const value = match[pattern.group || 1];
        return pattern.decode ? decodeURIComponent(value) : value;
      }
    }
    return null;
  }

  // ==================== STRATEGY DISPATCH ====================

  const STRATEGY_EXECUTORS = {
    json_embedded: executeJsonEmbedded,
    dom_scroll: executeDomScroll,
    dom_detail: executeDomDetail,
    api_fetch: executeApiFetch,
  };

  function selectStrategy(siteConfig) {
    // Custom strategy selector function
    if (typeof siteConfig.selectStrategy === 'function') {
      return siteConfig.selectStrategy(window.location);
    }

    // Page type routing
    if (siteConfig.pageTypes) {
      for (const [pageType, config] of Object.entries(siteConfig.pageTypes)) {
        if (typeof config.urlTest === 'function' && config.urlTest(window.location)) {
          return config.strategy;
        }
        if (config.urlMatch && window.location.pathname.includes(config.urlMatch)) {
          return config.strategy;
        }
      }
    }

    // Default strategy
    return siteConfig.defaultStrategy || Object.keys(siteConfig.strategies)[0];
  }

  // ==================== MAIN ORCHESTRATOR ====================

  async function runScraper(siteConfig, chainOverride) {
    scrapedProjects = [];
    isScanning = true;
    activeSiteConfig = siteConfig;

    try {
      // 1. Determine chain
      const chain = chainOverride || detectChainFromUrl(siteConfig) || siteConfig.defaultChain || '';

      // 2. Determine strategy
      const strategyName = selectStrategy(siteConfig);
      const strategyConfig = siteConfig.strategies[strategyName];

      if (!strategyConfig) {
        throw new Error(`No strategy "${strategyName}" defined for ${siteConfig.name}`);
      }

      const context = { chain, chainOverride, siteConfig };
      console.log(`[Ecosystem Scraper] Running ${siteConfig.name} → strategy: ${strategyName}, chain: ${chain || 'auto'}`);

      // 3. Execute
      if (siteConfig.customScrape) {
        scrapedProjects = await siteConfig.customScrape({
          sendMessage, sleep, reportProgress, extractSocialLinks,
          scrollToLoadAll, mapFields, getByPath, readPageGlobal, isScanning: () => isScanning
        });
      } else {
        const executor = STRATEGY_EXECUTORS[strategyName];
        if (!executor) throw new Error(`Unknown strategy type: ${strategyName}`);
        scrapedProjects = await executor(strategyConfig, context);
      }

      // 4. Apply fallback data
      if (siteConfig.fallbackData) {
        applyFallbackData(siteConfig.fallbackData, scrapedProjects);
      }

      // 5. Enrich
      if (siteConfig.enrich) {
        await executeEnrichment(siteConfig.enrich, scrapedProjects);
      }

      // 6. Complete
      sendMessage('scrapeComplete', { data: scrapedProjects });

    } catch (error) {
      console.error(`[Ecosystem Scraper] Error:`, error);
      sendMessage('scrapeError', { error: error.message });
    }

    isScanning = false;
    activeSiteConfig = null;
  }

  // ==================== CONFIG MATCHING ====================

  function findMatchingConfig(url) {
    for (const config of siteConfigs) {
      for (const pattern of (config.matchPatterns || [])) {
        if (matchUrlPattern(url, pattern)) {
          return config;
        }
      }
    }
    return null;
  }

  // ==================== CONFIG LOADING ====================

  async function loadConfigs() {
    try {
      const registryUrl = chrome.runtime.getURL('config/sites/registry.json');
      const response = await fetch(registryUrl);
      const registry = await response.json();

      for (const filename of (registry.sites || [])) {
        try {
          const fileUrl = chrome.runtime.getURL(`config/sites/${filename}`);
          const fileResponse = await fetch(fileUrl);
          const code = await fileResponse.text();

          // Eval in content script context — safe since we control the source files
          window.EcoScraperSites = window.EcoScraperSites || [];
          const before = window.EcoScraperSites.length;
          // Use Function constructor to avoid strict-mode eval restrictions
          new Function(code)();
          if (window.EcoScraperSites.length > before) {
            siteConfigs.push(window.EcoScraperSites[window.EcoScraperSites.length - 1]);
          }
        } catch (err) {
          console.warn(`[Ecosystem Scraper] Failed to load config ${filename}:`, err.message);
        }
      }

      configsLoaded = true;
    } catch (err) {
      console.warn('[Ecosystem Scraper] Failed to load registry:', err.message);
      configsLoaded = true; // Mark loaded even on failure so message listener works
    }
  }

  // ==================== MESSAGE LISTENER ====================

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startScraping') {
      if (!isScanning) {
        const config = findMatchingConfig(window.location.href);
        if (!config) {
          sendResponse({ success: false, error: 'No scraper config for this site' });
          return true;
        }
        const chainOverride = message.chain ? message.chain.name : null;
        runScraper(config, chainOverride);
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
      const config = findMatchingConfig(window.location.href);
      sendResponse({
        isScanning,
        projectCount: scrapedProjects.length,
        siteId: config ? config.id : null,
        siteName: config ? config.name : null
      });
      return true;
    }

    if (message.action === 'getSiteConfig') {
      const config = findMatchingConfig(window.location.href);
      sendResponse({
        matched: !!config,
        siteId: config ? config.id : null,
        siteName: config ? config.name : null
      });
      return true;
    }
  });

  // ==================== BOOT ====================

  loadConfigs().then(() => {
    const config = findMatchingConfig(window.location.href);
    if (config) {
      console.log(`[Ecosystem Scraper] Engine loaded — matched: ${config.name} (${config.id})`);
    }
  });

})();
