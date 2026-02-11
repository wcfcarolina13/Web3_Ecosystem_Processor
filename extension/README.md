# Ecosystem Scraper Chrome Extension

A Chrome extension for scraping project data from blockchain ecosystem directories like AptoFolio, DefiLlama, DappRadar, and CoinGecko.

## Features

- **Multiple site support**: Works with 4 major ecosystem directories
- **Smart extraction**: Uses the best method for each site (API, global vars, or DOM scraping)
- **Social link extraction**: Finds Twitter/X, Discord, Telegram, and website links
- **CSV export**: Outputs data in the Ecosystem Research Guidelines format
- **JSON export**: Raw data export for custom processing
- **Progress tracking**: Real-time progress indicator during scraping

## Supported Sites

| Site | Status | Method | Notes |
|------|--------|--------|-------|
| AptoFolio | ✅ Complete | Global variable | Uses `window.aptofolioData` + lookup tables |
| DefiLlama | ✅ Complete | Public API | Fetches from `api.llama.fi/protocols` |
| DappRadar | ✅ Complete | DOM scraping | Handles infinite scroll |
| CoinGecko | ✅ Complete | DOM scraping | Extracts from category pages |

## Installation

### Developer Mode (Recommended)

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" in the top right
3. Click "Load unpacked"
4. Select the `ecosystem-scraper-extension` folder
5. The extension icon should appear in your toolbar

## Usage

### Basic Usage

1. Navigate to a supported site:
   - AptoFolio: `https://www.aptofolio.com/`
   - DefiLlama: `https://defillama.com/chain/[ChainName]` (e.g., `/chain/Aptos`)
   - DappRadar: `https://dappradar.com/rankings/protocol/[chain]` (e.g., `/protocol/aptos`)
   - CoinGecko: `https://www.coingecko.com/en/categories/[chain]-ecosystem`

2. Click the Ecosystem Scraper extension icon
3. Click "Start Scraping"
4. Wait for the scraping to complete (progress shown in popup)
5. Export data using one of the options:
   - **Copy as CSV**: Copies CSV to clipboard
   - **Download CSV**: Downloads a CSV file
   - **Copy as JSON**: Copies raw JSON data

### Site-Specific Tips

#### AptoFolio
- Works instantly using the global `aptofolioData` variable
- Social links are fetched from a built-in lookup table (90+ handles)
- Falls back to DOM scraping if global data is unavailable

#### DefiLlama
- Fetches data from their public API (includes URL, Twitter, TVL)
- Works on any page - chain pages auto-filter by that chain
- Returns 90+ Aptos protocols with complete metadata

#### DappRadar
- Navigate to a rankings page (e.g., `/rankings/protocol/aptos`)
- Automatically scrolls to load all dapps
- For detailed social links, visit individual dapp pages

#### CoinGecko
- Navigate to a category/ecosystem page
- Extracts coins from the listings table
- Visit individual coin pages for complete social links

## CSV Output Format

The exported CSV matches the Ecosystem Research Guidelines format:

| Column | Description |
|--------|-------------|
| Name | Project name |
| Notes | Project description |
| Best URL | Primary website |
| Best social | Twitter/X handle |
| Secondary URL | Discord or other link |
| AI Research | TRUE |
| AI Notes & Sources | Category |
| Chain | Blockchain |

## Technical Details

### Scraping Strategies by Site

1. **AptoFolio** - Global Variable + Lookup Table
   - Reads from `window.aptofolioData` (95 projects)
   - Social links stored in React closures, so we use a lookup table

2. **DefiLlama** - Public API
   - Fetches from `api.llama.fi/protocols`
   - Complete data including URLs, Twitter, TVL, chains
   - No DOM scraping needed

3. **DappRadar** - DOM Scraping with Infinite Scroll
   - Scrolls page to load all dapps
   - Extracts links from rankings table
   - Can visit detail pages for social links

4. **CoinGecko** - DOM Scraping
   - Extracts from category/ecosystem pages
   - Handles pagination and lazy loading
   - Can visit coin pages for full details

### Project Structure

```
ecosystem-scraper-extension/
├── manifest.json          # Extension manifest (v3)
├── popup.html             # Extension popup UI
├── popup.js               # Popup logic
├── background.js          # Service worker
├── README.md              # This file
├── content-scripts/
│   ├── aptofolio.js       # AptoFolio scraper
│   ├── defillama.js       # DefiLlama scraper
│   ├── dappradar.js       # DappRadar scraper
│   └── coingecko.js       # CoinGecko scraper
└── icons/
    └── icon.svg           # Extension icon
```

### Adding Support for New Sites

1. Create a new content script in `content-scripts/`
2. Implement the standard message handlers:
   - `startScraping` - Begin scraping
   - `stopScraping` - Stop scraping
   - `getStatus` - Return current status
3. Send progress updates via `sendMessage('scrapeProgress', {...})`
4. Send completion via `sendMessage('scrapeComplete', {data: [...]})`
5. Add the site to `manifest.json` host_permissions and content_scripts
6. Test thoroughly!

## Troubleshooting

### "Could not connect to page"
- Refresh the target page
- Make sure you're on a supported site
- Check that the extension has the required permissions

### Data missing or incomplete
- Some sites have rate limiting - wait and try again
- For social links, try visiting individual project pages
- Check browser console for errors (F12 > Console)

### Extension not loading
- Go to `chrome://extensions/`
- Make sure the extension is enabled
- Click "Reload" to refresh the extension

## Key Learnings for Scraping

From building this extension, here are patterns for scraping complex sites:

1. **Check for global variables first** - `window.*Data`, `__NEXT_DATA__`, `__INITIAL_STATE__`
2. **Look for public APIs** - Many sites have undocumented APIs
3. **React closures hide data** - Social links often in closures, not DOM
4. **Chrome extensions avoid bot detection** - Run as real user context
5. **DOM patterns** - MUI uses `Mui*-root`, Next.js has `__NEXT_DATA__`

## License

MIT License - Feel free to use and modify for your ecosystem research needs.

## Contributing

Contributions welcome! Please open an issue or PR for:
- New site support
- Bug fixes
- Feature requests
