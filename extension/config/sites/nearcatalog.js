// NEARCatalog site config — Next.js streaming data (__next_f.push)
// NEARCatalog uses a non-standard Next.js streaming format where data
// is delivered via self.__next_f.push() calls in script tags.
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'nearcatalog',
  name: 'NEARCatalog',
  matchPatterns: [
    'https://*.nearcatalog.xyz/*',
    'https://nearcatalog.xyz/*'
  ],

  defaultChain: 'NEAR',

  // Custom scrape because __next_f streaming is non-standard
  customScrape: async function(engine) {
    var projects = [];

    engine.reportProgress(0, 100, 'Extracting NEARCatalog data...');

    // Strategy 1: Try __NEXT_DATA__ first (simpler pages may have it)
    var nextDataEl = document.querySelector('#__NEXT_DATA__');
    if (nextDataEl) {
      try {
        var nextData = JSON.parse(nextDataEl.textContent);
        var items = null;

        // Try common paths
        var paths = [
          'props.pageProps.projects',
          'props.pageProps.data',
          'props.pageProps'
        ];
        for (var p = 0; p < paths.length; p++) {
          var candidate = engine.getByPath(nextData, paths[p]);
          if (candidate && (Array.isArray(candidate) || typeof candidate === 'object')) {
            items = candidate;
            break;
          }
        }

        if (items) {
          return processItems(items, engine);
        }
      } catch (e) {
        // Fall through to streaming extraction
      }
    }

    // Strategy 2: Extract from __next_f streaming data
    var scripts = document.querySelectorAll('script');
    var jsonChunks = [];

    for (var i = 0; i < scripts.length; i++) {
      var text = scripts[i].textContent || '';
      // Match self.__next_f.push([1,"..."]) patterns
      var matches = text.match(/self\.__next_f\.push\(\s*\[\s*\d+\s*,\s*"(.+?)"\s*\]\s*\)/g);
      if (matches) {
        for (var j = 0; j < matches.length; j++) {
          // Extract the JSON string content from the push call
          var contentMatch = matches[j].match(/push\(\s*\[\s*\d+\s*,\s*"(.+?)"\s*\]\s*\)/);
          if (contentMatch) {
            try {
              // Unescape the string (it's double-escaped JSON)
              var decoded = JSON.parse('"' + contentMatch[1] + '"');
              jsonChunks.push(decoded);
            } catch (e) {
              // Not valid JSON, skip
            }
          }
        }
      }
    }

    // Try to find project data in the concatenated chunks
    var allText = jsonChunks.join('');

    // Look for JSON object patterns that look like project data
    // NEARCatalog typically has {slug: {profile: {name, tagline, tags, ...}}}
    var objectMatches = allText.match(/\{[^{}]*"profile"\s*:\s*\{[^}]*"name"[^}]*\}/g);
    if (!objectMatches || objectMatches.length === 0) {
      // Try finding a large JSON blob
      var braceStart = allText.indexOf('{"');
      if (braceStart >= 0) {
        try {
          // Try to parse from the first { to the end
          var remaining = allText.substring(braceStart);
          // Find balanced braces
          var depth = 0;
          var end = -1;
          for (var k = 0; k < remaining.length; k++) {
            if (remaining[k] === '{') depth++;
            else if (remaining[k] === '}') {
              depth--;
              if (depth === 0) { end = k; break; }
            }
          }
          if (end > 0) {
            var parsed = JSON.parse(remaining.substring(0, end + 1));
            return processItems(parsed, engine);
          }
        } catch (e) {
          // Fall through
        }
      }
    }

    // Strategy 3: Fall back to DOM scraping
    engine.reportProgress(0, 100, 'Falling back to DOM extraction...');
    await engine.sleep(1000);

    // NEARCatalog renders project cards with links
    var links = document.querySelectorAll('a[href*="/project/"], a[href*="/app/"]');
    if (links.length === 0) {
      // Try scrolling to load content
      await engine.scrollToLoadAll({ maxScrolls: 10, delay: 800 });
      links = document.querySelectorAll('a[href*="/project/"], a[href*="/app/"]');
    }

    var seen = {};
    var total = links.length;
    engine.reportProgress(0, total, 'Found ' + total + ' project links');

    for (var i = 0; i < links.length && engine.isScanning(); i++) {
      var link = links[i];
      var href = link.getAttribute('href') || '';
      var slugMatch = href.match(/\/(?:project|app)\/([^/?#]+)/);
      if (!slugMatch || seen[slugMatch[1]]) continue;

      var slug = slugMatch[1];
      seen[slug] = true;

      var name = '';
      // Try to get name from link text or child elements
      var nameEl = link.querySelector('h2, h3, h4, [class*="name"], [class*="title"]');
      if (nameEl) {
        name = nameEl.textContent.trim();
      } else {
        name = link.textContent.trim().split('\n')[0].trim();
      }

      // Clean up name (remove extra whitespace, limit length)
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

// Helper: process a map or array of project items
function processItems(items, engine) {
  var projects = [];
  var entries;

  if (Array.isArray(items)) {
    entries = items.map(function(item, idx) { return [String(idx), item]; });
  } else if (typeof items === 'object') {
    entries = Object.entries(items);
  } else {
    return projects;
  }

  var total = entries.length;
  engine.reportProgress(0, total, 'Processing ' + total + ' projects...');

  for (var i = 0; i < entries.length && engine.isScanning(); i++) {
    var slug = entries[i][0];
    var item = entries[i][1];

    // Handle nested profile structure: {slug: {profile: {...}}}
    var profile = item.profile || item;

    var name = profile.name || profile.title || slug;
    var description = profile.tagline || profile.oneliner || profile.description || '';
    var tags = profile.tags || profile.categories || {};
    var category = '';

    if (typeof tags === 'object' && !Array.isArray(tags)) {
      category = Object.keys(tags).join(', ');
    } else if (Array.isArray(tags)) {
      category = tags.join(', ');
    } else if (typeof tags === 'string') {
      category = tags;
    }

    var website = profile.website || profile.url || '';
    var twitter = profile.twitter || '';
    if (twitter && !twitter.startsWith('@')) twitter = '@' + twitter;

    projects.push({
      name: name,
      slug: slug,
      description: description.substring(0, 500),
      category: category,
      website: website,
      twitter: twitter,
      telegram: profile.telegram || '',
      discord: profile.discord || '',
      chain: 'NEAR',
      nearcatalogUrl: 'https://nearcatalog.xyz/project/' + slug
    });

    if (i % 20 === 0 || i === entries.length - 1) {
      engine.reportProgress(projects.length, total, 'Processing: ' + name);
    }
    if (i % 50 === 0) {
      // yield to UI
    }
  }

  return projects;
}
