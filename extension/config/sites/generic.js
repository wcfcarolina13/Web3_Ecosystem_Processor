// Generic fallback scraper — attempts to extract project data from ANY page
// using heuristics (embedded JSON, repeated link patterns, card elements).
// This config never matches via URL patterns; it's only used as a fallback
// when no specific site config matches.
//
// NOTE: The popup.js Source column uses the page hostname (not "Generic Scraper")
// so researchers always see the actual data source website.
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'generic',
  name: 'Generic Scraper',
  matchPatterns: [],  // Never matches explicitly — selected by findMatchingConfig fallback
  defaultStrategy: 'generic_discovery',
  strategies: {
    generic_discovery: {
      // No config needed — the executor uses heuristics, not config-driven extraction
    }
  }
});
