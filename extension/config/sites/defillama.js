// DefiLlama site config — chain pages (__NEXT_DATA__) + API fallback + enrichment
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'defillama',
  name: 'DefiLlama',
  matchPatterns: [
    'https://*.defillama.com/*',
    'https://defillama.com/*',
    'https://api.llama.fi/*'
  ],

  chainFromUrl: { regex: '\\/chain\\/([^/]+)', group: 1, decode: true },

  // Strategy selection: use page data when on a matching chain page, else API
  selectStrategy: function(loc) {
    const urlChain = loc.pathname.match(/\/chain\/([^/]+)/);
    const hasNextData = !!document.getElementById('__NEXT_DATA__');
    return (urlChain && hasNextData) ? 'json_embedded' : 'api_fetch';
  },

  strategies: {
    json_embedded: {
      source: { type: 'element', selector: '#__NEXT_DATA__' },
      jsonPath: 'props.pageProps.protocols',
      fieldMap: {
        name: 'name',
        category: 'category',
        chain: '$chain',
        slug: 'slug',
        // tvl needs special handling — nested or flat
        tvl: function(item) {
          return item.tvl?.default?.tvl || item.tvl || 0;
        }
      },
      progressBatchSize: 10,
      uiYieldBatchSize: 20
    },

    api_fetch: {
      url: 'https://api.llama.fi/protocols',
      responsePath: null,
      chainFilter: { field: 'chains', matchType: 'array_includes' },
      fieldMap: {
        name: 'name',
        description: 'description',
        category: 'category',
        website: 'url',
        twitter: { field: 'twitter', transform: 'prefixAt' },
        chain: '$chain',
        slug: 'slug',
        logo: 'logo'
      },
      progressBatchSize: 20,
      uiYieldBatchSize: 50
    }
  },

  // After json_embedded, enrich with API data for website/twitter/description
  enrich: {
    apiUrl: 'https://api.llama.fi/protocols',
    lookupBy: ['slug', 'name'],
    fieldMap: {
      website: 'url',
      twitter: { field: 'twitter', transform: 'prefixAt' },
      description: 'description',
      logo: 'logo'
    }
  }
});
