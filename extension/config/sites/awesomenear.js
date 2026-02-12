// AwesomeNEAR site config — sitemap + batch page scraping for full catalog
// The /projects page only loads ~48 projects and scroll-to-load is broken.
// Strategy: collect all slugs from sitemap + category pages, then batch-fetch
// individual project pages to extract rich __NEXT_DATA__ (website, socials, etc.)
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'awesomenear',
  name: 'AwesomeNEAR',
  matchPatterns: [
    'https://*.awesomenear.com/*',
    'https://awesomenear.com/*'
  ],

  defaultChain: 'NEAR',

  customScrape: async function(engine) {
    var BATCH_SIZE = 10;
    var BATCH_DELAY = 300;
    var BASE = 'https://awesomenear.com';

    engine.reportProgress(0, 100, 'Collecting project slugs...');

    // Phase 1: Gather all known slugs from multiple sources
    var slugSet = {};

    // Source A: __NEXT_DATA__ on the current page (if we're on /projects or home)
    try {
      var ndEl = document.querySelector('#__NEXT_DATA__');
      if (ndEl) {
        var nd = JSON.parse(ndEl.textContent);
        var pageProjects = nd.props && nd.props.pageProps && nd.props.pageProps.projects;
        if (Array.isArray(pageProjects)) {
          pageProjects.forEach(function(p) { if (p.slug) slugSet[p.slug] = true; });
        }
      }
    } catch (e) { /* ignore */ }
    engine.reportProgress(0, 100, 'Page data: ' + Object.keys(slugSet).length + ' slugs');

    // Source B: Category pages — each returns 48 projects (different subsets)
    var categories = ['aurora', 'infrastructure', 'dapps', 'nft', 'utilities', 'ecosystem'];
    for (var ci = 0; ci < categories.length; ci++) {
      try {
        var catResp = await fetch(BASE + '/projects/' + categories[ci]);
        if (!catResp.ok) continue;
        var catHtml = await catResp.text();
        var catMatch = catHtml.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
        if (catMatch) {
          var catNd = JSON.parse(catMatch[1]);
          var catProjects = catNd.props && catNd.props.pageProps && catNd.props.pageProps.projects;
          if (Array.isArray(catProjects)) {
            catProjects.forEach(function(p) { if (p.slug) slugSet[p.slug] = true; });
          }
        }
      } catch (e) { /* skip failed categories */ }
      engine.reportProgress(0, 100, 'Categories ' + (ci + 1) + '/' + categories.length + ': ' + Object.keys(slugSet).length + ' slugs');
    }

    // Source C: Sitemap — has the most comprehensive list
    try {
      var smResp = await fetch(BASE + '/page-sitemap.xml');
      if (smResp.ok) {
        var smXml = await smResp.text();
        var locMatches = smXml.match(/<loc>https:\/\/awesomenear\.com\/([^<]+)<\/loc>/g) || [];
        locMatches.forEach(function(m) {
          var slug = m.replace(/<\/?loc>/g, '').replace('https://awesomenear.com/', '');
          // Filter out non-project pages
          if (slug && !slug.includes('/') && slug !== 'projects' && slug !== 'privacy-policy' &&
              slug !== 'terms-and-conditions' && slug !== 'about' && slug !== 'contact') {
            slugSet[slug] = true;
          }
        });
      }
    } catch (e) { /* sitemap unavailable */ }

    var allSlugs = Object.keys(slugSet);
    engine.reportProgress(0, allSlugs.length, 'Found ' + allSlugs.length + ' unique project slugs. Fetching details...');

    if (allSlugs.length === 0) {
      engine.reportProgress(0, 0, 'No project slugs found.');
      return [];
    }

    // Phase 2: Batch-fetch individual project pages for rich data
    var projects = [];
    var errors = 0;

    for (var i = 0; i < allSlugs.length && engine.isScanning(); i += BATCH_SIZE) {
      var batch = allSlugs.slice(i, i + BATCH_SIZE);
      var batchResults = await Promise.all(batch.map(function(slug) {
        return fetch(BASE + '/' + slug)
          .then(function(r) { return r.ok ? r.text() : null; })
          .then(function(html) {
            if (!html) return null;
            var m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
            if (!m) return null;
            try {
              var pageNd = JSON.parse(m[1]);
              return pageNd.props && pageNd.props.pageProps && pageNd.props.pageProps.project;
            } catch (e) { return null; }
          })
          .catch(function() { return null; });
      }));

      batchResults.forEach(function(p) {
        if (!p || !p.title) { errors++; return; }

        var twitter = p.twitter || '';
        // AwesomeNEAR stores full URLs for socials
        var twitterHandle = '';
        if (twitter) {
          var twMatch = twitter.match(/(?:twitter\.com|x\.com)\/([^/?#]+)/);
          twitterHandle = twMatch ? '@' + twMatch[1] : twitter;
        }

        projects.push({
          name: p.title,
          slug: p.slug || '',
          description: (p.oneliner || '').substring(0, 500),
          category: Array.isArray(p.categories) ? p.categories.join('; ') : (p.categories || ''),
          website: p.website || p.dapp || '',
          twitter: twitterHandle,
          telegram: p.telegram || '',
          discord: p.discord || '',
          github: p.github || '',
          chain: 'NEAR'
        });
      });

      engine.reportProgress(
        Math.min(i + BATCH_SIZE, allSlugs.length), allSlugs.length,
        'Fetched ' + projects.length + ' projects (' + errors + ' skipped)'
      );

      // Rate-limit between batches
      if (i + BATCH_SIZE < allSlugs.length) {
        await engine.sleep(BATCH_DELAY);
      }
    }

    engine.reportProgress(projects.length, projects.length,
      'Done — ' + projects.length + ' projects from ' + allSlugs.length + ' slugs');
    return projects;
  }
});
