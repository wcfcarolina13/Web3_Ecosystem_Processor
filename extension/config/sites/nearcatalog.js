// NEARCatalog site config — uses the indexer REST API for full catalog
// Homepage only shows ~72 curated projects. The API returns all ~350.
// API: https://indexer.nearcatalog.org/wp-json/nearcatalog/v1/projects
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'nearcatalog',
  name: 'NEARCatalog',
  matchPatterns: [
    'https://*.nearcatalog.xyz/*',
    'https://nearcatalog.xyz/*'
  ],

  defaultChain: 'NEAR',

  customScrape: async function(engine) {
    engine.reportProgress(0, 100, 'Fetching full project catalog from API...');

    // Strategy 1: REST API (returns ALL projects)
    try {
      var resp = await fetch('https://indexer.nearcatalog.org/wp-json/nearcatalog/v1/projects');
      if (resp.ok) {
        var data = await resp.json();
        var projects = processNearcatalogItems(data, engine);
        if (projects.length > 0) {
          engine.reportProgress(projects.length, projects.length,
            'Done — ' + projects.length + ' projects from API');
          return projects;
        }
      }
    } catch (e) {
      console.warn('[NEARCatalog] API fetch failed, falling back to page data:', e.message);
    }

    // Strategy 2: Parse RSC streaming data from __next_f.push() on the page
    engine.reportProgress(0, 100, 'API unavailable — parsing page data...');
    try {
      var scripts = document.querySelectorAll('script');
      var jsonChunks = [];

      for (var i = 0; i < scripts.length; i++) {
        var text = scripts[i].textContent || '';
        // Match self.__next_f.push([1,"..."]) — use greedy match for large payloads
        var pushRegex = /self\.__next_f\.push\(\s*\[\s*1\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]\s*\)/g;
        var match;
        while ((match = pushRegex.exec(text)) !== null) {
          try {
            var decoded = JSON.parse('"' + match[1] + '"');
            jsonChunks.push(decoded);
          } catch (e) { /* skip malformed chunks */ }
        }
      }

      // Concatenate and find project data blobs
      var allText = jsonChunks.join('');
      // Look for large JSON objects with project-like structure
      var jsonStart = -1;
      for (var k = 0; k < allText.length; k++) {
        if (allText[k] === '{' && allText[k + 1] === '"') {
          jsonStart = k;
          break;
        }
      }

      if (jsonStart >= 0) {
        // Find the largest balanced JSON object
        var remaining = allText.substring(jsonStart);
        var bestEnd = -1;
        var depth = 0;
        for (var k = 0; k < remaining.length; k++) {
          if (remaining[k] === '{') depth++;
          else if (remaining[k] === '}') {
            depth--;
            if (depth === 0) { bestEnd = k; break; }
          }
        }
        if (bestEnd > 100) { // Must be substantial
          var parsed = JSON.parse(remaining.substring(0, bestEnd + 1));
          // Check if it looks like project data (objects with profile subkey)
          var keys = Object.keys(parsed);
          if (keys.length > 5 && parsed[keys[0]] && parsed[keys[0]].profile) {
            var projects = processNearcatalogItems(parsed, engine);
            if (projects.length > 0) {
              engine.reportProgress(projects.length, projects.length,
                'Done — ' + projects.length + ' projects from page data');
              return projects;
            }
          }
        }
      }
    } catch (e) {
      console.warn('[NEARCatalog] RSC parse failed:', e.message);
    }

    // Strategy 3: DOM fallback — project links
    engine.reportProgress(0, 100, 'Falling back to DOM extraction...');
    await engine.sleep(1000);

    var links = document.querySelectorAll('a[href*="/project/"]');
    if (links.length === 0) {
      await engine.scrollToLoadAll({ maxScrolls: 10, delay: 800 });
      links = document.querySelectorAll('a[href*="/project/"]');
    }

    var seen = {};
    var projects = [];
    var total = links.length;
    engine.reportProgress(0, total, 'Found ' + total + ' project links');

    for (var i = 0; i < links.length && engine.isScanning(); i++) {
      var href = links[i].getAttribute('href') || '';
      var slugMatch = href.match(/\/project\/([^/?#]+)/);
      if (!slugMatch || seen[slugMatch[1]]) continue;

      var slug = slugMatch[1];
      seen[slug] = true;

      var nameEl = links[i].querySelector('h2, h3, h4, [class*="name"], [class*="title"]');
      var name = nameEl ? nameEl.textContent.trim() : links[i].textContent.trim().split('\n')[0].trim();
      name = name.replace(/\s+/g, ' ').substring(0, 100);

      if (name && name.length > 1) {
        projects.push({
          name: name,
          slug: slug,
          description: '',
          category: '',
          website: '',
          twitter: '',
          chain: 'NEAR',
          nearcatalogUrl: 'https://nearcatalog.xyz/project/' + slug
        });
      }

      if (i % 10 === 0) {
        engine.reportProgress(projects.length, total, 'Processed: ' + (name || slug));
      }
    }

    return projects;
  }
});

// Process the NEARCatalog API/page data — object keyed by slug
// Each value: { slug, profile: { name, tagline, tags, image, phase, lnc } }
function processNearcatalogItems(data, engine) {
  var projects = [];
  if (!data || typeof data !== 'object') return projects;

  var entries = Object.entries(data);
  var total = entries.length;
  engine.reportProgress(0, total, 'Processing ' + total + ' projects...');

  for (var i = 0; i < entries.length && engine.isScanning(); i++) {
    var slug = entries[i][0];
    var item = entries[i][1];
    if (!item || typeof item !== 'object') continue;

    var profile = item.profile || item;
    var name = profile.name || profile.title || slug;
    var description = profile.tagline || profile.oneliner || profile.description || '';

    // Tags can be {slug: "Label"} or ["tag1", "tag2"] or "tag"
    var tags = profile.tags || profile.categories || {};
    var category = '';
    if (typeof tags === 'object' && !Array.isArray(tags)) {
      category = Object.values(tags).join(', ');
    } else if (Array.isArray(tags)) {
      category = tags.join(', ');
    } else if (typeof tags === 'string') {
      category = tags;
    }

    // Social links — API has linktree on detail pages, but not on /projects
    // Pull what we can from profile
    var linktree = profile.linktree || {};
    var website = linktree.website || profile.website || profile.url || '';
    var twitter = linktree.twitter || profile.twitter || '';
    if (twitter && !twitter.startsWith('http') && !twitter.startsWith('@')) {
      twitter = '@' + twitter;
    }

    projects.push({
      name: name,
      slug: slug,
      description: description.substring(0, 500),
      category: category,
      website: website,
      twitter: twitter,
      telegram: linktree.telegram || profile.telegram || '',
      discord: linktree.discord || profile.discord || '',
      github: linktree.github || profile.github || '',
      chain: 'NEAR',
      nearcatalogUrl: 'https://nearcatalog.xyz/project/' + slug
    });

    if (i % 50 === 0 || i === entries.length - 1) {
      engine.reportProgress(projects.length, total, 'Processing: ' + name);
    }
  }

  return projects;
}
