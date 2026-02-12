// CoinGecko site config — ecosystem/category page (scroll) + coin detail
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'coingecko',
  name: 'CoinGecko',
  matchPatterns: [
    'https://*.coingecko.com/*',
    'https://coingecko.com/*'
  ],

  chainFromUrl: [
    { regex: '\\/categories\\/([^/]+)', group: 1, decode: true },
    { regex: '\\/chains\\/([^/]+)', group: 1, decode: true }
  ],

  pageTypes: {
    ecosystem: {
      urlTest: function(loc) {
        return loc.pathname.includes('/categories/') ||
               loc.pathname.includes('/chains/') ||
               loc.pathname.includes('/ecosystem');
      },
      strategy: 'dom_scroll'
    },
    coin: {
      urlTest: function(loc) { return /\/coins\/[^/]+$/.test(loc.pathname); },
      strategy: 'dom_detail'
    }
  },

  strategies: {
    dom_scroll: {
      scroll: {
        maxScrolls: 15,
        delay: 600,
        countSelector: 'a[href*="/coins/"]',
        noChangeThreshold: 3
      },
      itemSelector: 'a[href*="/coins/"]',
      slugFromHref: '\\/coins\\/([^/?#]+)',
      nameExtraction: 'textContent',
      nameFallbackSelector: '[class*="name"], td:nth-child(2), span',
      nameTransform: 'stripTicker',
      nameMaxLength: 100,
      deduplicate: true,
      staticFields: {
        description: '',
        website: '',
        twitter: '',
        discord: ''
      },
      extraFields: {
        coingeckoUrl: function(slug) { return 'https://www.coingecko.com/en/coins/' + slug; },
        category: function(slug) {
          // Derive chain name from URL category slug
          var cat = window.location.pathname.match(/\/categories\/([^/]+)/);
          return cat ? cat[1] : 'Cryptocurrency';
        }
      }
    },

    dom_detail: {
      waitMs: 1000,
      fields: {
        slug: { fromUrl: '\\/coins\\/([^/]+)' },
        name: { selector: 'h1, [class*="coin-name"]', extract: 'textContent', firstWord: true },
        description: { selector: '[class*="description"], [itemprop="description"]', extract: 'textContent', maxLength: 500 },
        category: { selector: '[class*="badge"], [class*="tag"], [class*="category"]', extract: 'textContent', maxLength: 30 },
        website: {
          selector: 'a[href][rel="nofollow"][target="_blank"]:not([href*="twitter"]):not([href*="x.com"]):not([href*="t.me"]):not([href*="discord"]):not([href*="github"])',
          extract: 'href'
        }
      },
      socialLinks: true,
      chainSelector: '[class*="blockchain"], [class*="chain"], [class*="network"]'
    }
  }
});
