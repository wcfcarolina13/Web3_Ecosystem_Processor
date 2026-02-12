// DappRadar site config — rankings page (scroll + links) + detail page
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'dappradar',
  name: 'DappRadar',
  matchPatterns: [
    'https://*.dappradar.com/*',
    'https://dappradar.com/*'
  ],

  chainFromUrl: { regex: '\\/protocol\\/([^/]+)', group: 1, decode: true },

  pageTypes: {
    rankings: {
      urlMatch: '/rankings',
      strategy: 'dom_scroll'
    },
    detail: {
      urlMatch: '/dapp/',
      strategy: 'dom_detail'
    }
  },

  strategies: {
    dom_scroll: {
      scroll: {
        maxScrolls: 20,
        delay: 800,
        countSelector: 'a[href*="/dapp/"]',
        noChangeThreshold: 3
      },
      itemSelector: 'a[href*="/dapp/"]',
      slugFromHref: '\\/dapp\\/([^/]+)',
      nameExtraction: 'textContent',
      nameMaxLength: 100,
      deduplicate: true,
      staticFields: {
        description: '',
        category: '',
        website: '',
        twitter: '',
        discord: ''
      },
      extraFields: {
        dappradarUrl: function(slug) { return 'https://dappradar.com/dapp/' + slug; }
      }
    },

    dom_detail: {
      waitMs: 1000,
      fields: {
        slug: { fromUrl: '\\/dapp\\/([^/]+)' },
        name: { selector: 'h1', extract: 'textContent' },
        description: { selector: 'p', extract: 'textContent', minLength: 20, maxLength: 500 },
        category: { selector: '[class*="badge"], [class*="category"], [class*="tag"]', extract: 'textContent', maxLength: 30 },
        website: {
          selector: 'a[target="_blank"][href*="http"]:not([href*="dappradar"]):not([href*="twitter"]):not([href*="x.com"]):not([href*="t.me"]):not([href*="discord"]):not([href*="github"])',
          extract: 'href'
        }
      },
      socialLinks: true,
      chainSelector: '[class*="chain"] img, [alt*="chain"], [title*="chain"]'
    }
  }
});
