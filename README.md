# Ecosystem Research

Tools for discovering, cataloging, and enriching Web3 project data for [The Grid](https://thegrid.id).

Given a blockchain ecosystem, the pipeline scrapes project directories, enriches with social/contact data, matches against The Grid's entity database, and detects asset support gaps (e.g., projects using USDT that aren't yet tracked in The Grid).

## Pipeline Stages

The research workflow has five stages. Each stage reads the CSV from the previous stage and writes an enriched version.

### Stage 1: Scraping

**Tool:** Chrome extension (`extension/`)

Scrape ecosystem directories to build an initial project catalog. The extension supports multiple sites per chain, each with a tailored scraping strategy.

| Site | Strategy | Notes |
|------|----------|-------|
| DefiLlama | `json_embedded` + `api_fetch` | Chain pages embed `__NEXT_DATA__`, with API fallback + enrichment for website/Twitter |
| DappRadar | `dom_scroll` | Scroll-to-load rankings table, DOM extraction |
| CoinGecko | `dom_scroll` | Category ecosystem pages with card-based layout |
| AptoFolio | `json_embedded` | Aptos-specific; project data in a global JS variable |
| NEARCatalog | `customScrape` | REST API for full catalog (~350 projects), RSC parse fallback, DOM fallback |
| AwesomeNEAR | `customScrape` | Sitemap + category pages for slug collection, batch page fetch for details |
| *(any site)* | `generic` | Tries embedded JSON, link patterns, then card elements |

**Tricky sites:**

- **AwesomeNEAR**: The `/projects` page only loads ~48 projects and infinite scroll is broken. The scraper collects all slugs from the sitemap XML + category subpages, then batch-fetches individual project pages to extract `__NEXT_DATA__` (website, socials, descriptions). Yields 490+ projects vs 48 from the page alone.

- **NEARCatalog**: The homepage shows ~72 curated projects. The API at `indexer.nearcatalog.org` returns all ~350. Social links (website, Twitter, Telegram, Discord, GitHub) are in a `linktree` object inside each project's `profile` -- but the list endpoint only includes basic data. Detail pages (`/project/{slug}`) contain the full linktree, stored as escaped JSON in React Server Component (RSC) streaming payloads (`self.__next_f.push([1,"..."])`). Batch-fetching detail pages with concurrent requests is necessary for complete social coverage.

- **DefiLlama**: Chain pages (`/chain/Near`) embed protocol data in `__NEXT_DATA__` but without website/Twitter fields. The extension's `enrich` config automatically fetches the full API (`api.llama.fi/protocols`) to backfill those fields by matching on slug or name.

### Stage 2: Social Enrichment

**Tool:** Python scripts or manual in-process enrichment

Cross-reference multiple data sources to fill gaps in website URLs, X/Twitter handles, Telegram, Discord, and GitHub links. For NEAR, this involved:

1. Matching CSV rows against the NEARCatalog API by slug
2. Batch-fetching ~270 NEARCatalog detail pages for linktree data
3. Merging DefiLlama API data for DeFi protocols
4. Attempting AwesomeNEAR cross-reference for remaining gaps

Result: website coverage from ~65% to 94%, X handle coverage from ~63% to 93%.

### Stage 3: Grid Matching

**Tool:** `scripts/grid_match.py`

Match each project against The Grid's GraphQL API to find existing entity profiles.

```bash
python3 scripts/grid_match.py --chain near --dry-run
python3 scripts/grid_match.py --chain near --limit 20
python3 scripts/grid_match.py --chain near
```

**Matching strategy:**
1. **Name search** (primary): Normalize the project name (strip suffixes like "Protocol", "Finance", "DEX"), search Grid by name, score results with word-boundary matching (threshold: 0.8)
2. **URL search** (fallback): If name matching fails, search by the project's website URL

**Outputs:**
- `*_grid_matched.csv` -- enriched with Profile Name, Root ID, Matched URL, Matched via, The Grid Status
- `*_gap_report.csv` -- projects not in Grid or missing target asset support

**False positive handling:** Name/URL matching can produce false positives (e.g., "Spin" matching "Degen Spin", "Gate.io" matching "CoinGate"). After running, review matches and clear Grid columns for false positives with a note. The NEAR run produced ~15 false positives out of 203 matches.

### Stage 4: Asset Enrichment

**Tool:** `scripts/enrich_assets.py`

Check each project for target asset support (USDT, USDC, SOL, STRK, ADA) using DefiLlama's per-protocol token holdings data.

```bash
python3 scripts/enrich_assets.py --chain near --assets USDT,USDC,SOL,STRK,ADA
python3 scripts/enrich_assets.py --chain near --assets USDT,USDC --dry-run
```

**How it works:**
1. Fetch DefiLlama protocol index filtered to the target chain
2. Match CSV rows against the index by name/URL
3. For matched protocols, fetch `/protocol/{slug}` detail endpoint
4. Extract `chainTvls[chain].tokensInUsd` for token holdings
5. Detect target assets using aliases (e.g., USDT.e, axlUSDT, bridged USDT all count as USDT)

**Populated columns:** `Suspect USDT support?`, `Web3 but no stablecoin`, `General Stablecoin Adoption`, `Evidence URLs`, `Notes`

### Stage 5: Gap Analysis

**Built into** `grid_match.py`

Compare Grid's asset support records against DefiLlama evidence. If a project has DefiLlama evidence of USDT usage but Grid doesn't list USDT as "Supported by" that product, it's flagged as a gap. These gaps represent opportunities to update The Grid's asset coverage.

## Project Structure

```
config/
  chains.json              Chain definitions, target assets, source URLs
extension/
  manifest.json            Chrome MV3 extension manifest
  popup.html / popup.js    Extension popup UI (site detection, chain selector, CSV export)
  scraper-engine.js        Universal scraping engine (~800 lines, 5 strategies)
  config/sites/            Per-site scraper configurations (7 configs)
scripts/
  compare.py               Compare scraped data against existing CSV
  merge.py                 Merge new projects into master CSV
  grid_match.py            Match projects against Grid API
  enrich_assets.py         DefiLlama token holdings enrichment
  enrich_coingecko.py      CoinGecko-based enrichment
  transform_csv_columns.py Reformat CSV columns to standard order
lib/
  columns.py               Canonical 26-column definition (CORRECT_COLUMNS)
  matching.py              Name normalization and fuzzy matching
  csv_utils.py             CSV I/O with sanitization (commas, newlines, entities)
  grid_client/
    client.py              GridAPIClient (GraphQL queries)
    queries.py             GraphQL query templates
    matcher.py             Grid entity matching logic
    models.py              Data models for Grid entities
    cli.py                 CLI interface for Grid client
data/
  _template/               Template files for new chains
  aptos/                   Aptos research data
  near/                    NEAR research data
```

## Quick Start

### 1. Install the Chrome Extension

1. Open `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" and select the `extension/` folder
4. Navigate to a supported ecosystem directory
5. Click the extension icon, select the chain, and click "Start Scan"

### 2. Run the Pipeline

```bash
# Compare scraped data against existing CSV
python3 scripts/compare.py --chain near --source defillama --data data/near/defillama_scraped.json

# Merge new discoveries into the research CSV
python3 scripts/merge.py --chain near --source defillama

# Match against The Grid (dry-run first)
python3 scripts/grid_match.py --chain near --dry-run --limit 20

# Run asset enrichment
python3 scripts/enrich_assets.py --chain near --assets USDT,USDC,SOL,STRK,ADA

# Query The Grid API directly
python3 -m lib.grid_client search_products "NEAR" --limit 10
```

### 3. Verify Setup

```bash
python3 -c "from lib.columns import CORRECT_COLUMNS; from lib.matching import normalize_name; from lib.csv_utils import load_csv; from lib.grid_client import GridAPIClient; print('All imports OK')"
```

## Adding a New Chain

1. **Add to `config/chains.json`:**
   ```json
   {
     "id": "tron",
     "name": "Tron",
     "target_assets": ["USDT", "USDC"],
     "sources": {
       "defillama": { "chain_slug": "Tron", "url": "https://defillama.com/chain/Tron" },
       "dappradar": { "protocol_slug": "tron", "url": "https://dappradar.com/rankings/protocol/tron" }
     }
   }
   ```

2. **Create data directory:** `mkdir -p data/tron`

3. **Scrape:** Use the Chrome extension on each source URL. Select "Tron" as the chain in the popup.

4. **Compare + Merge:**
   ```bash
   python3 scripts/compare.py --chain tron --source defillama --data data/tron/defillama_raw.csv
   python3 scripts/merge.py --chain tron --source defillama
   ```

5. **Grid match + Enrich:**
   ```bash
   python3 scripts/grid_match.py --chain tron
   python3 scripts/enrich_assets.py --chain tron
   ```

6. **(Optional) Add a site-specific scraper config** in `extension/config/sites/` if a chain has its own ecosystem directory (like NEARCatalog for NEAR or AptoFolio for Aptos). Register it in `manifest.json` under `content_scripts`.

## CSV Column Standard

All research CSVs use 26 columns in a fixed order (defined in `lib/columns.py`):

| Column | Populated By | Description |
|--------|-------------|-------------|
| Project Name | Scraper | Project display name |
| Suspect USDT support? | enrich_assets.py | TRUE if DefiLlama shows USDT holdings |
| Skip | Manual | Flag to skip during processing |
| Added | Manual | Date added to Grid |
| Web3 but no stablecoin | enrich_assets.py | DeFi protocol with no stablecoin detected |
| General Stablecoin Adoption | enrich_assets.py | Has USDC but not USDT |
| To be Added | Manual | Queued for Grid addition |
| Processed? | Manual | Research completion flag |
| In Admin | Manual | Added to Grid admin |
| TG/TON appstore | Manual | Telegram-only projects |
| Final Status | Manual | Final research disposition |
| Website | Scraper + Enrichment | Primary website URL |
| X Link | Scraper + Enrichment | Full Twitter/X profile URL |
| X Handle | Scraper + Enrichment | @handle format |
| Telegram | Scraper + Enrichment | Telegram group/channel link |
| Category | Scraper | DeFi, NFT, Gaming, Infrastructure, etc. |
| Release Date | Manual | Project launch date |
| Product Status | Manual | Active, Beta, Deprecated, etc. |
| The Grid Status | grid_match.py | Grid profile status (Active, Inactive, etc.) |
| Profile Name | grid_match.py | Matched Grid profile name |
| Root ID | grid_match.py | Grid root entity ID |
| Matched URL | grid_match.py | Grid root URL |
| Matched via | grid_match.py | Match method: "name" or "url" |
| Chain | Scraper | Blockchain network |
| Source | Scraper | Data source (defillama, dappradar, etc.) |
| Notes | Various | Free-text notes, gap flags |
| Evidence URLs | enrich_assets.py | DefiLlama protocol URLs as evidence |

## Grid API

- **Endpoint:** `https://beta.node.thegrid.id/graphql`
- **Access:** Public, no authentication required
- **Key entity types:** profileInfos, products, assets, entities
- **Usage:** Read-only queries. Sort by `gridRank` for importance. Use slugs for filtering.

## Ralph

This project uses the Ralph autonomous development methodology for iterative task execution. See `RALPH_TASK.md` for current task state.

```bash
./scripts/init-ralph.sh    # Initialize Ralph state
./scripts/ralph-once.sh    # Run single iteration
./scripts/ralph-loop.sh    # Run autonomous loop
```
