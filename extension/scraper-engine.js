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
  let configsReadyResolve;
  const configsReady = new Promise(r => { configsReadyResolve = r; });

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
    joinComma: (val) => Array.isArray(val) ? val.join('; ') : (val || ''),
    trim: (val) => (val || '').trim(),
    firstWord: (val) => (val || '').trim().split(/\s+/)[0] || '',
    stripTicker: (val) => (val || '').replace(/\s+\$?[A-Z]{2,10}$/, '').trim(),
    objectKeys: (val) => {
      if (val && typeof val === 'object' && !Array.isArray(val)) {
        return Object.values(val).join('; ');
      }
      return Array.isArray(val) ? val.join('; ') : (val || '');
    }
  };

  // Coerce any value to a CSV-safe string (arrays → semicolon-separated)
  function csvSafe(val) {
    if (val === null || val === undefined) return '';
    if (Array.isArray(val)) return val.join('; ');
    if (typeof val === 'object') return Object.values(val).join('; ');
    return String(val);
  }

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
        result[targetField] = csvSafe(getByPath(sourceItem, mapping));
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
        result[targetField] = csvSafe(val);
        continue;
      }

      // Function: custom extraction
      if (typeof mapping === 'function') {
        result[targetField] = csvSafe(mapping(sourceItem, context));
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

  // ==================== STRATEGY: GENERIC DISCOVERY ====================

  // Heuristic scraper — tries multiple extraction methods on any page.
  // Used as fallback when no specific site config matches.
  // Incorporates patterns from site-specific configs for robustness:
  //   - Scroll-to-load (from dom_scroll configs)
  //   - Multiple JSON sources (from Next.js, Nuxt, Gatsby patterns)
  //   - Table extraction (from DappRadar-style HTML tables)
  //   - Enhanced social link extraction per card (from detail configs)
  //   - Better container/card detection (from various ecosystem directories)

  async function executeGenericDiscovery(strategyConfig, context) {
    const allProjects = [];
    const seen = new Set();

    function addProject(p) {
      if (!p || !p.name || p.name.length < 2) return;
      const key = p.name.toLowerCase().trim();
      if (seen.has(key)) return;
      seen.add(key);
      p._source = 'generic';
      allProjects.push(p);
    }

    // --- Phase 0: Scroll to load lazy content ---
    // Many ecosystem directories lazy-load projects on scroll.
    // Do a moderate scroll pass first to reveal hidden content.
    reportProgress(0, 100, 'Loading page content (scrolling)...');
    try {
      let lastHeight = document.body.scrollHeight;
      let scrollCount = 0;
      let noChangeCount = 0;
      const maxScrolls = 10;  // Conservative limit for generic mode
      while (scrollCount < maxScrolls && noChangeCount < 3 && isScanning) {
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(500);
        const newHeight = document.body.scrollHeight;
        if (newHeight === lastHeight) {
          noChangeCount++;
        } else {
          noChangeCount = 0;
        }
        lastHeight = newHeight;
        scrollCount++;
      }
      window.scrollTo(0, 0);
      await sleep(300);
    } catch (e) { console.warn('[Generic] Scroll pass failed:', e.message); }

    // --- Heuristic 1: Embedded JSON (multiple framework patterns) ---
    reportProgress(0, 100, 'Trying embedded JSON...');
    try {
      // Try multiple JSON data sources common in modern frameworks:
      // 1. Next.js: #__NEXT_DATA__
      // 2. Nuxt.js: window.__NUXT__
      // 3. Generic: <script type="application/json">
      // 4. Structured data: <script type="application/ld+json">

      let jsonFound = false;

      // --- 1a. Next.js __NEXT_DATA__ ---
      const nextEl = document.querySelector('#__NEXT_DATA__');
      if (nextEl) {
        const data = JSON.parse(nextEl.textContent);
        const arrays = findProjectArrays(data);
        if (arrays.length > 0) {
          const best = arrays.sort((a, b) => b.score - a.score)[0];
          reportProgress(0, best.items.length, `Found ${best.items.length} items in Next.js data`);
          for (let i = 0; i < best.items.length && isScanning; i++) {
            addProject(extractProjectFromObject(best.items[i]));
            if (i % 20 === 0) reportProgress(allProjects.length, best.items.length, `JSON: ${allProjects.length} projects...`);
          }
          jsonFound = true;
        }
      }

      // --- 1b. Generic <script type="application/json"> elements ---
      if (!jsonFound) {
        const jsonScripts = document.querySelectorAll('script[type="application/json"]');
        for (const script of jsonScripts) {
          if (jsonFound) break;
          try {
            const data = JSON.parse(script.textContent);
            const arrays = findProjectArrays(data);
            if (arrays.length > 0) {
              const best = arrays.sort((a, b) => b.score - a.score)[0];
              if (best.score >= 10) {  // Higher threshold for generic JSON
                reportProgress(0, best.items.length, `Found ${best.items.length} items in embedded JSON`);
                for (let i = 0; i < best.items.length && isScanning; i++) {
                  addProject(extractProjectFromObject(best.items[i]));
                  if (i % 20 === 0) reportProgress(allProjects.length, best.items.length, `JSON: ${allProjects.length} projects...`);
                }
                jsonFound = true;
              }
            }
          } catch (parseErr) { /* skip non-JSON script blocks */ }
        }
      }

      // --- 1c. Map-style JSON objects (keyed by slug, like NEARCatalog) ---
      if (!jsonFound && nextEl) {
        try {
          const data = JSON.parse(nextEl.textContent);
          const maps = findProjectMaps(data);
          if (maps.length > 0) {
            const best = maps.sort((a, b) => b.score - a.score)[0];
            const items = Object.entries(best.map).map(([key, val]) => ({ _mapKey: key, ...val }));
            reportProgress(0, items.length, `Found ${items.length} items in JSON map`);
            for (let i = 0; i < items.length && isScanning; i++) {
              addProject(extractProjectFromObject(items[i]));
              if (i % 20 === 0) reportProgress(allProjects.length, items.length, `JSON map: ${allProjects.length} projects...`);
            }
          }
        } catch (e) { /* ignore map parsing errors */ }
      }
    } catch (e) { console.warn('[Generic] JSON heuristic failed:', e.message); }

    if (allProjects.length >= 20) {
      reportProgress(allProjects.length, allProjects.length, `Found ${allProjects.length} projects via embedded JSON`);
      return allProjects.slice(0, 500);
    }

    // --- Heuristic 2: Repeated Link Patterns (enhanced) ---
    if (isScanning) {
      reportProgress(allProjects.length, 100, 'Trying link pattern detection...');
      try {
        const linkGroups = findRepeatedLinkPatterns();
        for (const group of linkGroups) {
          const links = document.querySelectorAll(`a[href*="${group.pattern}"]`);
          const groupSeen = new Set();
          links.forEach(link => {
            const href = link.getAttribute('href') || '';
            const match = href.match(group.regex);
            if (!match || groupSeen.has(match[1])) return;
            groupSeen.add(match[1]);

            let name = '';
            let description = '';
            let category = '';
            let socials = { twitter: '', telegram: '', discord: '', github: '' };

            // Try: heading in parent card, link text
            const card = link.closest(
              '[class*="card"], [class*="item"], [class*="row"], [class*="project"], ' +
              '[class*="dapp"], [class*="protocol"], [class*="app-"], ' +
              'tr, li, article, section'
            );
            if (card) {
              const heading = card.querySelector(
                'h1, h2, h3, h4, h5, [class*="name"], [class*="title"], ' +
                '[class*="heading"], [data-testid*="name"]'
              );
              if (heading) name = heading.textContent.trim();

              // Extract description from card
              const desc = card.querySelector(
                'p, [class*="desc"], [class*="summary"], [class*="tagline"], ' +
                '[class*="about"], [class*="subtitle"]'
              );
              if (desc) description = desc.textContent.trim().substring(0, 300);

              // Extract category from card
              const catEl = card.querySelector(
                '[class*="category"], [class*="tag"], [class*="badge"], ' +
                '[class*="chip"], [class*="label"]'
              );
              if (catEl) category = catEl.textContent.trim();

              // Extract social links from card
              socials = extractSocialLinks(card);
            }
            if (!name || name.length < 2) name = link.textContent.trim().split('\n')[0].trim();

            // Clean: remove excess whitespace, cap length
            name = name.replace(/\s+/g, ' ').substring(0, 100);

            if (name && name.length > 1 && name.length < 80) {
              addProject({
                name: name,
                slug: match[1],
                website: '',
                twitter: socials.twitter,
                telegram: socials.telegram,
                description: description,
                category: category,
                chain: context.chain || ''
              });
            }
          });
        }
        if (allProjects.length > 0) {
          reportProgress(allProjects.length, allProjects.length, `Found ${allProjects.length} projects via link patterns`);
        }
      } catch (e) { console.warn('[Generic] Link pattern heuristic failed:', e.message); }
    }

    if (allProjects.length >= 20) {
      return allProjects.slice(0, 500);
    }

    // --- Heuristic 3: HTML Table Extraction ---
    // Many ecosystem directories use tables (like DappRadar rankings).
    if (isScanning) {
      reportProgress(allProjects.length, 100, 'Trying table extraction...');
      try {
        const tables = document.querySelectorAll('table');
        for (const table of tables) {
          const rows = table.querySelectorAll('tbody tr');
          if (rows.length < 5) continue;  // Skip small tables

          // Find column indices from header
          const headers = table.querySelectorAll('thead th, thead td');
          const headerTexts = Array.from(headers).map(h => h.textContent.trim().toLowerCase());

          // Look for a name column
          const nameIdx = headerTexts.findIndex(h =>
            /^(name|project|dapp|protocol|token|app)$/i.test(h) ||
            h.includes('name') || h.includes('project')
          );

          for (const row of rows) {
            if (!isScanning) break;
            const cells = row.querySelectorAll('td');
            if (cells.length < 2) continue;

            // Extract name: from identified column or first cell with a link
            let name = '';
            let slug = '';
            const nameCell = nameIdx >= 0 ? cells[nameIdx] : cells[0];

            const nameLink = nameCell.querySelector('a');
            if (nameLink) {
              name = nameLink.textContent.trim().replace(/\s+/g, ' ');
              const href = nameLink.getAttribute('href') || '';
              const slugMatch = href.match(/\/([^/?#]+)\/?$/);
              if (slugMatch) slug = slugMatch[1];
            } else {
              name = nameCell.textContent.trim().replace(/\s+/g, ' ');
            }

            name = name.substring(0, 100);
            if (!name || name.length < 2) continue;

            // Try to find category from other cells
            let category = '';
            const catIdx = headerTexts.findIndex(h =>
              h.includes('category') || h.includes('type') || h.includes('sector')
            );
            if (catIdx >= 0 && cells[catIdx]) {
              category = cells[catIdx].textContent.trim();
            }

            const socials = extractSocialLinks(row);

            addProject({
              name: name,
              slug: slug,
              category: category,
              twitter: socials.twitter,
              telegram: socials.telegram,
              description: '',
              website: '',
              chain: context.chain || ''
            });
          }
        }
        if (allProjects.length > 0) {
          reportProgress(allProjects.length, allProjects.length, `Found ${allProjects.length} projects via table extraction`);
        }
      } catch (e) { console.warn('[Generic] Table heuristic failed:', e.message); }
    }

    if (allProjects.length >= 20) {
      return allProjects.slice(0, 500);
    }

    // --- Heuristic 4: Card/Grid Element Extraction (enhanced) ---
    if (isScanning) {
      reportProgress(allProjects.length, 100, 'Trying card element extraction...');
      try {
        // Expanded container selectors for Web3 ecosystem directories
        const containers = document.querySelectorAll(
          '[class*="grid"], [class*="list"], [class*="projects"], [class*="directory"], ' +
          '[class*="catalog"], [class*="results"], [class*="cards"], ' +
          '[class*="dapps"], [class*="protocols"], [class*="ecosystem"], ' +
          '[class*="apps"], [class*="tokens"], [class*="items"], ' +
          '[class*="collection"], [class*="gallery"], ' +
          '[role="list"], main ul, main ol, [data-testid*="list"]'
        );

        for (const container of containers) {
          const children = container.querySelectorAll(
            ':scope > *, :scope > li > *, :scope > div > *, ' +
            ':scope > article, :scope > a'
          );
          if (children.length < 5) continue;

          children.forEach(el => {
            // Expanded heading selectors
            const heading = el.querySelector(
              'h1, h2, h3, h4, h5, h6, ' +
              '[class*="name"], [class*="title"], [class*="heading"], ' +
              '[data-testid*="name"], [data-testid*="title"]'
            );
            if (!heading) return;

            const name = heading.textContent.trim().replace(/\s+/g, ' ').substring(0, 100);
            if (!name || name.length < 2) return;

            // Description from multiple patterns
            const desc = el.querySelector(
              'p, [class*="desc"], [class*="summary"], [class*="tagline"], ' +
              '[class*="about"], [class*="subtitle"], [class*="bio"]'
            );

            // Category from badges/tags
            const catEl = el.querySelector(
              '[class*="category"], [class*="tag"]:not(a), [class*="badge"], ' +
              '[class*="chip"], [class*="label"]:not(label), [class*="type"]'
            );

            // Website URL: try multiple patterns
            let website = '';
            const websiteLink = el.querySelector(
              'a[href*="http"]:not([href*="twitter"]):not([href*="x.com"])' +
              ':not([href*="t.me"]):not([href*="discord"]):not([href*="github"])'
            );
            if (websiteLink) {
              website = websiteLink.getAttribute('href');
            }
            // Also check data attributes
            if (!website) {
              website = el.getAttribute('data-url') || el.getAttribute('data-website') || '';
            }

            const socials = extractSocialLinks(el);

            addProject({
              name: name,
              description: desc ? desc.textContent.trim().substring(0, 300) : '',
              website: website,
              twitter: socials.twitter,
              telegram: socials.telegram,
              discord: socials.discord,
              github: socials.github,
              category: catEl ? catEl.textContent.trim().substring(0, 100) : '',
              chain: context.chain || ''
            });
          });
        }
        if (allProjects.length > 0) {
          reportProgress(allProjects.length, allProjects.length, `Found ${allProjects.length} projects via card extraction`);
        }
      } catch (e) { console.warn('[Generic] Card heuristic failed:', e.message); }
    }

    if (allProjects.length === 0) {
      reportProgress(0, 0, 'No project data found on this page.');
    }

    return allProjects.slice(0, 500);
  }

  // --- Generic helpers ---

  // Recursively find arrays in a nested object that look like project lists
  function findProjectArrays(obj, depth, maxDepth) {
    depth = depth || 0;
    maxDepth = maxDepth || 5;
    const results = [];
    if (depth > maxDepth) return results;

    if (Array.isArray(obj)) {
      if (obj.length >= 5) {
        const score = scoreArrayAsProjects(obj);
        if (score > 0) results.push({ items: obj, score: score });
      }
      return results;
    }

    if (obj && typeof obj === 'object') {
      for (const key of Object.keys(obj)) {
        try {
          const sub = findProjectArrays(obj[key], depth + 1, maxDepth);
          results.push(...sub);
        } catch (e) { /* circular ref or similar */ }
      }
    }
    return results;
  }

  // Recursively find map-style objects (keyed by slug) that contain project data
  // Pattern: {slug1: {name: '...', profile: {...}}, slug2: {...}} (e.g., NEARCatalog)
  function findProjectMaps(obj, depth, maxDepth) {
    depth = depth || 0;
    maxDepth = maxDepth || 5;
    const results = [];
    if (depth > maxDepth || !obj || typeof obj !== 'object' || Array.isArray(obj)) return results;

    // Check if this object itself is a project map
    const keys = Object.keys(obj);
    if (keys.length >= 5) {
      let projectLike = 0;
      const sampleKeys = keys.slice(0, 10);
      for (const key of sampleKeys) {
        const val = obj[key];
        if (val && typeof val === 'object' && !Array.isArray(val)) {
          // Check for project-like subkeys
          const subkeys = Object.keys(val);
          const hasName = subkeys.some(k => /^(name|title|label)$/i.test(k));
          const hasProfile = subkeys.some(k => k === 'profile' || k === 'info' || k === 'meta');
          if (hasName || hasProfile) projectLike++;
        }
      }
      if (projectLike >= 3) {
        results.push({ map: obj, score: projectLike * keys.length });
      }
    }

    // Recurse into children
    for (const key of keys) {
      try {
        const sub = findProjectMaps(obj[key], depth + 1, maxDepth);
        results.push(...sub);
      } catch (e) { /* circular ref or similar */ }
    }
    return results;
  }

  // Score how "project-like" an array of objects is (0 = not at all, higher = better)
  function scoreArrayAsProjects(arr) {
    if (!arr || arr.length < 3) return 0;
    // Sample up to 10 items
    const sample = arr.slice(0, 10);
    let score = 0;
    const nameFields = ['name', 'title', 'projectName', 'label'];
    const bonusFields = ['description', 'website', 'url', 'twitter', 'category', 'categories', 'slug', 'tagline', 'tags'];

    for (const item of sample) {
      if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
      const keys = Object.keys(item);

      // Must have a name-like field
      const hasName = nameFields.some(f => item[f] && typeof item[f] === 'string' && item[f].length > 1);
      if (hasName) {
        score += 2;
        // Bonus for additional project-like fields
        score += bonusFields.filter(f => item[f]).length;
      }
    }
    return score;
  }

  // Extract a project object from a generic JSON object with common field names
  function extractProjectFromObject(item) {
    if (!item || typeof item !== 'object') return null;

    // Handle nested profile pattern (e.g., NEARCatalog: {profile: {name, ...}})
    // Also handle linktree pattern for social links
    let data = item;
    const profile = item.profile || item.info || item.meta;
    if (profile && typeof profile === 'object') {
      // Merge profile data with top-level data (profile takes priority for names)
      data = { ...item, ...profile };
    }

    const name = data.name || data.title || data.projectName || data.label || item._mapKey || '';
    if (!name || typeof name !== 'string' || name.length < 2) return null;

    // Twitter: handle URLs (https://twitter.com/handle) and bare handles
    let twitter = data.twitter || data.twitterHandle || data.x || '';
    if (typeof twitter === 'string') {
      const twitterMatch = twitter.match(/(?:twitter\.com|x\.com)\/([^/?#]+)/);
      if (twitterMatch) {
        twitter = '@' + twitterMatch[1];
      } else if (twitter && !twitter.startsWith('@') && !twitter.startsWith('http')) {
        twitter = '@' + twitter;
      }
    }

    // Check linktree-style nested social links
    const linktree = data.linktree || data.links || data.social || data.socials || {};
    if (typeof linktree === 'object' && !Array.isArray(linktree)) {
      if (!twitter) {
        const lt = linktree.twitter || linktree.x || '';
        if (lt) {
          const m = String(lt).match(/(?:twitter\.com|x\.com)\/([^/?#]+)/);
          twitter = m ? '@' + m[1] : (lt.startsWith('@') ? lt : '@' + lt);
        }
      }
    }

    let category = data.category || data.categories || data.tags || data.type || '';
    if (Array.isArray(category)) category = category.join('; ');
    if (typeof category === 'object') {
      // Handle {key: value} tag objects (NEARCatalog style)
      category = Object.values(category).flat().join('; ');
    }

    let telegram = data.telegram || '';
    if (!telegram && typeof linktree === 'object') {
      telegram = linktree.telegram || '';
    }

    let discord = data.discord || '';
    if (!discord && typeof linktree === 'object') {
      discord = linktree.discord || '';
    }

    let github = data.github || '';
    if (!github && typeof linktree === 'object') {
      github = linktree.github || '';
    }

    return {
      name: String(name).substring(0, 100),
      slug: data.slug || data.id || item._mapKey || String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      description: String(data.description || data.tagline || data.summary || data.oneliner || '').substring(0, 500),
      category: String(category || ''),
      website: data.website || data.url || data.homepage || data.dapp || '',
      twitter: String(twitter || ''),
      telegram: String(telegram || ''),
      discord: String(discord || ''),
      github: String(github || ''),
      chain: csvSafe(data.chain || data.network || data.chains || '')
    };
  }

  // Find URL patterns that repeat in <a> elements (e.g., /project/xxx appears 20+ times)
  function findRepeatedLinkPatterns() {
    const patternCounts = {};
    const links = document.querySelectorAll('a[href]');

    // Expanded slug-bearing path keywords (from Web3 ecosystem sites)
    const slugKeywords = [
      'project', 'app', 'dapp', 'protocol', 'coin', 'token', 'nft',
      'game', 'tool', 'ecosystem', 'defi', 'dao', 'marketplace',
      'wallet', 'bridge', 'exchange', 'lending', 'staking', 'yield',
      'validator', 'explorer', 'launchpad', 'aggregator',
      'p', 'd', 'c', 'page'  // Short URL aliases
    ];
    const slugRegex = new RegExp(
      '\\/(' + slugKeywords.join('|') + ')s?\\/([^/?#]+)', 'i'
    );

    for (const link of links) {
      const href = link.getAttribute('href');
      if (!href || href.startsWith('#') || href.startsWith('javascript')) continue;

      const match = href.match(slugRegex);
      if (match) {
        const pattern = '/' + match[1].toLowerCase() + (href.includes(match[1] + 's/') ? 's/' : '/');
        if (!patternCounts[pattern]) patternCounts[pattern] = 0;
        patternCounts[pattern]++;
      }
    }

    // Return patterns that appear 5+ times, sorted by count descending
    return Object.entries(patternCounts)
      .filter(([_, count]) => count >= 5)
      .sort((a, b) => b[1] - a[1])
      .map(([pattern]) => ({
        pattern: pattern,
        regex: new RegExp(pattern.replace(/\//g, '\\/') + '([^/?#]+)')
      }));
  }

  // ==================== STRATEGY DISPATCH ====================

  const STRATEGY_EXECUTORS = {
    json_embedded: executeJsonEmbedded,
    dom_scroll: executeDomScroll,
    dom_detail: executeDomDetail,
    api_fetch: executeApiFetch,
    generic_discovery: executeGenericDiscovery,
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
    if (siteConfig.defaultStrategy) return siteConfig.defaultStrategy;
    if (siteConfig.strategies) return Object.keys(siteConfig.strategies)[0];
    return null;
  }

  // ==================== MAIN ORCHESTRATOR ====================

  async function runScraper(siteConfig, chainOverride) {
    scrapedProjects = [];
    isScanning = true;
    activeSiteConfig = siteConfig;

    try {
      // 1. Determine chain
      const chain = chainOverride || detectChainFromUrl(siteConfig) || siteConfig.defaultChain || '';

      // 2. Execute — customScrape bypasses the strategy system entirely
      if (siteConfig.customScrape) {
        console.log(`[Ecosystem Scraper] Running ${siteConfig.name} → customScrape, chain: ${chain || 'auto'}`);
        scrapedProjects = await siteConfig.customScrape({
          sendMessage, sleep, reportProgress, extractSocialLinks,
          scrollToLoadAll, mapFields, getByPath, readPageGlobal, isScanning: () => isScanning
        });
      } else {
        const strategyName = selectStrategy(siteConfig);
        const strategyConfig = siteConfig.strategies[strategyName];
        if (!strategyConfig) {
          throw new Error(`No strategy "${strategyName}" defined for ${siteConfig.name}`);
        }
        const context = { chain, chainOverride, siteConfig };
        console.log(`[Ecosystem Scraper] Running ${siteConfig.name} → strategy: ${strategyName}, chain: ${chain || 'auto'}`);
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
    // Try specific site configs first
    for (const config of siteConfigs) {
      if (!config.matchPatterns || config.matchPatterns.length === 0) continue;
      for (const pattern of config.matchPatterns) {
        if (matchUrlPattern(url, pattern)) {
          return config;
        }
      }
    }
    // Fall back to generic config (empty matchPatterns, id === 'generic')
    return siteConfigs.find(c => c.id === 'generic') || null;
  }

  // ==================== CONFIG LOADING ====================

  // Site configs are injected by Chrome as content scripts (listed in manifest.json
  // before scraper-engine.js). Each config file pushes to window.EcoScraperSites.
  // This function simply reads from that array — no eval or fetch needed.
  function loadConfigs() {
    try {
      const configs = window.EcoScraperSites || [];
      for (const config of configs) {
        siteConfigs.push(config);
      }
      console.log(`[Ecosystem Scraper] Loaded ${siteConfigs.length} site configs`);
    } catch (err) {
      console.warn('[Ecosystem Scraper] Failed to load configs:', err.message);
    }
    configsLoaded = true;
    configsReadyResolve();
  }

  // ==================== MESSAGE LISTENER ====================

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startScraping') {
      // Wait for configs before matching
      configsReady.then(() => {
        if (!isScanning) {
          const config = findMatchingConfig(window.location.href);
          if (!config) {
            sendResponse({ success: false, error: 'No scraper config for this site' });
            return;
          }
          const chainOverride = message.chain ? message.chain.name : null;
          runScraper(config, chainOverride);
          sendResponse({ success: true });
        } else {
          sendResponse({ success: false, error: 'Already scanning' });
        }
      });
      return true; // Keep sendResponse channel open for async
    }

    if (message.action === 'stopScraping') {
      isScanning = false;
      sendResponse({ success: true });
      return true;
    }

    if (message.action === 'getStatus') {
      configsReady.then(() => {
        const config = findMatchingConfig(window.location.href);
        sendResponse({
          isScanning,
          projectCount: scrapedProjects.length,
          siteId: config ? config.id : null,
          siteName: config ? config.name : null
        });
      });
      return true;
    }

    if (message.action === 'getSiteConfig') {
      // Wait for configs to load before responding
      configsReady.then(() => {
        const config = findMatchingConfig(window.location.href);
        sendResponse({
          matched: !!config,
          siteId: config ? config.id : null,
          siteName: config ? config.name : null
        });
      });
      return true; // Keep sendResponse channel open for async
    }

    // --- Save URL for later (bookmark unconfigured sites) ---

    if (message.action === 'saveUrl') {
      chrome.storage.local.get({ savedUrls: [] }, (result) => {
        const urls = result.savedUrls;
        // Avoid duplicates
        if (!urls.some(u => u.url === message.url)) {
          urls.push({
            url: message.url,
            title: message.title || '',
            savedAt: new Date().toISOString(),
            note: message.note || ''
          });
          chrome.storage.local.set({ savedUrls: urls }, () => {
            sendResponse({ success: true, count: urls.length });
          });
        } else {
          sendResponse({ success: false, error: 'URL already saved' });
        }
      });
      return true; // async sendResponse
    }

    if (message.action === 'getSavedUrls') {
      chrome.storage.local.get({ savedUrls: [] }, (result) => {
        sendResponse({ urls: result.savedUrls });
      });
      return true;
    }

    if (message.action === 'removeSavedUrl') {
      chrome.storage.local.get({ savedUrls: [] }, (result) => {
        const urls = result.savedUrls.filter(u => u.url !== message.url);
        chrome.storage.local.set({ savedUrls: urls }, () => {
          sendResponse({ success: true, count: urls.length });
        });
      });
      return true;
    }
  });

  // ==================== BOOT ====================

  loadConfigs();
  const bootConfig = findMatchingConfig(window.location.href);
  if (bootConfig) {
    console.log(`[Ecosystem Scraper] Engine loaded — matched: ${bootConfig.name} (${bootConfig.id})`);
  }

})();
