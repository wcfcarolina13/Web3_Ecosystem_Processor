// AwesomeNEAR site config — Next.js embedded JSON with __NEXT_DATA__
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'awesomenear',
  name: 'AwesomeNEAR',
  matchPatterns: [
    'https://*.awesomenear.com/*',
    'https://awesomenear.com/*'
  ],

  defaultChain: 'NEAR',
  defaultStrategy: 'json_embedded',

  strategies: {
    json_embedded: {
      source: { type: 'element', selector: '#__NEXT_DATA__' },
      // AwesomeNEAR stores projects in __NEXT_DATA__.props.pageProps
      // The exact path may vary — try common Next.js patterns
      jsonPath: 'props.pageProps.projects',
      fieldMap: {
        name: 'title',
        slug: 'slug',
        description: 'oneliner',
        category: { field: 'category', transform: 'joinComma' },
        website: 'url',
        twitter: { field: 'twitter', transform: 'prefixAt' },
        telegram: 'telegram',
        discord: 'discord',
        github: 'github'
      },
      // Filter out dead/inactive projects if the field exists
      filter: function(item) {
        return item.status !== 'dead' && item.status !== 'inactive';
      },
      progressBatchSize: 20,
      uiYieldBatchSize: 50
    }
  }
});
