# Progress Log

> Updated by the agent after significant work.

## Summary

- Iterations completed: 1 (manual session)
- Current status: All 22 criteria COMPLETE
- RALPH COMPLETE

## How This Works

Progress is tracked in THIS FILE, not in LLM context.
When context is rotated (fresh agent), the new agent reads this file.
This is how Ralph maintains continuity across iterations.

## Session History

### Session 1 — 2026-02-11/12 (Manual)

**Accomplished:**
- **Chrome Extension v2.0**: Universal config-driven scraper engine with 7 site configs
  - DefiLlama, DappRadar, CoinGecko, AptoFolio, AwesomeNEAR, NEARCatalog, Generic fallback
  - Fixed CSP eval issues (static content_scripts), async race conditions, strategy selection for customScrape
  - CSV sanitization (newlines, HTML entities, commas→semicolons) in both JS and Python
  - Generic fallback scraper with embedded JSON, link pattern, and card element heuristics
  - Save URL bookmarking for sites where generic scraping fails
- **NEAR Ecosystem Research (888 projects)**:
  - Scraped from NEARCatalog (349), AwesomeNEAR (498 slugs), DefiLlama (43 DeFi protocols)
  - Social enrichment: cross-referenced all sources to fill website/X/Telegram/Discord
    - 94% website coverage (838/888), 93% X handle coverage (829/888)
  - Grid matching: 187 valid matches (after clearing 16 false positives)
  - Asset enrichment: 28 DeFi protocols with USDT/USDC token holdings data
- **All Phase 3-6 criteria complete**: Extension generalized, Python modularized, Grid client built, data organized

**Criteria completed**: All 22 (Phases 3, 4, 5, 6)

### Session 2 — 2026-02-12 (Manual)

**Accomplished:**
- **Column rename**: "Evidence URLs" → "Evidence & Source URLs" across all scripts, extension, templates, docs
- **Grid asset enrichment** (`enrich_grid_assets.py`): New script queries Grid API for product→asset relationships on 187 matched rows. 140 rows enriched (75% hit rate)
- **CoinGecko batch enrichment** (`enrich_coingecko.py`): Complete rewrite using `/coins/list?include_platform=true` — single API call fetches 18,933 coins, O(1) lookups per CSV row. 40 rows enriched with SOL/STRK/ADA platform deployments. Runtime: ~3 seconds (was ~2.5 hours)
- **DefiLlama chains extraction**: Enhanced `enrich_assets.py` to extract `chains` array from protocol data for chain-presence detection (zero extra API cost)
- **Shared support module** (`lib/grid_client/support.py`): Extracted TARGET_ASSET_GRID_MAP, extract_supported_tickers(), check_target_support() for reuse across scripts
- **Notes cleanup** (`clean_notes.py`): Stripped "CATEGORIES from SOURCE - " prefixes, emojis, and marketing fluff from 884/887 notes. Preserved enrichment findings after " | " separators
- **popup.js fix**: Notes generation now uses only `item.description` (categories + source already have own columns)

**Final NEAR CSV stats (888 rows)**:
- Grid asset data: 140 rows enriched
- CoinGecko platform data: 40 rows enriched
- Suspect USDT = TRUE: 169 rows
- General Stablecoin Adoption = TRUE: 100 rows
- Notes cleaned: 884 rows (0 still have old prefix pattern)

### Session 3 — 2026-02-12 (Manual)

**Accomplished:**
- **CSV deduplication** (`dedup_csv.py`): Normalized name + website domain grouping. 888 → 791 rows. 69 exact + 28 fuzzy dupes removed. Fuzzy merges annotated with "(fuzzy dedup: merged from X; Y)". Different-domain projects kept separate (e.g., AuroraSwap ≠ Aurora).
- **Unified enrichment runner** (`enrich_all.py`): Single command orchestrates dedup → Grid → DefiLlama → CoinGecko → notes cleanup. Supports --skip, --only, --dry-run.
- **Incremental mode**: All 3 enrichment scripts skip already-enriched rows + write in-place for pipeline composability.
- **CoinGecko fuzzy matching**: Added separator-aware name lookup + fuzzy fallback (0.90 threshold). Fuzzy matches write ONLY to Notes as `[UNVERIFIED]` hints — isolated from high-confidence Evidence/asset columns. 1 new exact match, 2 fuzzy hints.

### Session 4 — 2026-02-12 (Manual)

**Accomplished:**
- **Source column fix**: Replaced "Generic Scraper" with actual source website hostname in both the extension (`popup.js`) and existing CSV data. 9 NEAR rows fixed (→ "wallet.near.org"). New `fix_source_column.py` script added as "sources" step in `enrich_all.py` pipeline.
- **Dedup source annotation**: `dedup_csv.py` now annotates Notes with merged source info for ALL dedup merges (not just fuzzy). Format: "(dedup: merged N rows | sources: X; Y)" for exact merges, "(fuzzy dedup: merged from A; B | sources: X; Y)" for fuzzy.
- **Generic scraper v2**: Major enhancements to the generic discovery scraper:
  - Scroll-to-load before extraction (up to 10 scrolls)
  - Multiple JSON sources: __NEXT_DATA__ + `<script type="application/json">` + map-style objects
  - HTML table extraction with column header analysis
  - Enhanced link pattern detection with expanded Web3 slug keywords
  - Richer card extraction: description, category, social links per card
  - Better project field extraction: nested profiles, linktree socials, Twitter URL→handle normalization

### Session 5 — 2026-02-12 (Manual)

**Accomplished:**
- **Website keyword scan** (`enrich_website_keywords.py`): Scans homepage HTML for asset/stablecoin keywords. 712 sites scanned, 198 keyword hits (27.8%). Integrated as pipeline step 5. Writes `[UNVERIFIED website-scan]` to Notes and `website-scan: scanned` to Evidence.
- **Web dashboard** (`dashboard/`): Flask + Chart.js local dashboard with 7 stat cards, 6 interactive charts, filterable project table. Zero new pip installs (Flask already available). Runs at localhost:5050 via `python scripts/dashboard.py --chain near`.
- **Hint promotion engine** (`promote_hints.py`): Converts website-scan findings into boolean research columns. 3 strategies: USDT keywords → Suspect USDT (+19), USDC/stablecoin → General Stablecoin (+32), Web3 completeness. Integrated as pipeline step 6.

**NEAR CSV stats (791 rows):**
- Suspect USDT = TRUE: 147 rows (was 128)
- General Stablecoin Adoption = TRUE: 107 rows (was 75)
- Web3 but no stablecoin: 629 rows (was 670)
- Grid matched: 150 rows (19%)
- Evidence coverage: 750 rows (94.8%)

**Pipeline now 8 steps:** dedup → grid → defillama → coingecko → website → promote → notes → sources

### Session 6 — 2026-02-12 (Manual)

**Accomplished:**
- **Grid Match Gap Closer** (`expand_grid_matches.py`): Multi-strategy batch expansion that downloads all 2,986 Grid profiles + 6,206 products, builds normalized-name and domain indexes, matches locally. 5 false-positive guard layers (EXCLUDED_DOMAINS, MIN_NORMALIZED_LEN, URL cross-validation, word overlap, suffix-strip awareness). 9 new matches found (5 batch-name, 4 batch-url). Integrated as pipeline step 2 (expand-grid).
- **Pipeline Hardening** (5 improvements):
  1. **Atomic CSV writes**: `write_csv()` now uses tempfile + `os.fsync()` + `os.replace()` — never truncates on crash
  2. **Auto-backup**: `backup_csv()` creates timestamped or named .bak files; pre-pipeline backup as safety net
  3. **Column validation**: `load_csv()` validates 5 REQUIRED_COLUMNS by default, raises `CSVColumnError` early
  4. **Structured logging**: `lib/logging_config.py` with `get_logger()`/`configure_logging()`, pipeline writes `data/<chain>/pipeline.log`
  5. **Pipeline checkpoints**: Per-step checkpoints (deleted on success), `--stop-on-error`, `--rollback-on-error` flags

**NEAR CSV stats (791 rows):**
- Grid matched: 159 rows (20.1%, was 150)
- Suspect USDT = TRUE: 151 rows (was 147)
- General Stablecoin Adoption = TRUE: 107 rows
- Pipeline: 9 steps (dedup → expand-grid → grid → defillama → coingecko → website → promote → notes → sources)

### Session 7 — 2026-02-12 (Manual)

**Accomplished:**
- **Pipeline Web UI** (`/pipeline` page): Full browser-based interface for the enrichment pipeline
  - Upload CSV with column validation (rejects missing REQUIRED_COLUMNS)
  - Configure steps via checkboxes, run pipeline with one click
  - Live progress tracking: AJAX polls every 2s, shows per-step status (pending/running/completed/failed/skipped)
  - Download enriched CSV directly from the browser
  - Only one pipeline can run at a time (mutex enforcement, 409 on concurrent start)
- **New files (4)**:
  - `dashboard/pipeline_manager.py`: Thread-safe background job executor with PipelineJob/StepResult dataclasses
  - `dashboard/pipeline_api.py`: Flask blueprint with 6 routes (page, upload, start, status, download, chains)
  - `dashboard/templates/pipeline.html`: Upload + run controls + live step progress UI
  - `docs/RENDER_PLAN.md`: Saved Render cloud deployment plan for future budget approval
- **Modified files (4)**:
  - `scripts/enrich_all.py`: `load_chain_config()` now raises ValueError (not sys.exit) for web UI compatibility
  - `dashboard/__init__.py`: Registered pipeline blueprint + 16MB upload limit
  - `dashboard/templates/base.html`: Added Pipeline nav link
  - `dashboard/static/style.css`: Pipeline page styles with step state animations

### Session 8 — 2026-02-12 (Manual)

**Accomplished:**
- **Server-side scraping + Add Chain + User Guide**:
  - `dashboard/scraper.py`: DefiLlama API discovery (`discover_defillama()`, `merge_discovered_rows()`)
  - `dashboard/scraper_manager.py`: Thread-safe background discovery executor (mirrors PipelineManager)
  - `dashboard/pipeline_api.py`: 5 new API routes — add chain, discover sources/start/status, download extension ZIP
  - `dashboard/templates/pipeline.html`: Panel 0 (Add Chain) + Panel 1 (Discover Projects) with progress bar
  - `dashboard/templates/guide.html`: 9-section user guide with extension install, security docs, column reference
  - `dashboard/app.py`: `/guide` route
  - Mutual exclusion between pipeline and discovery jobs (prevents concurrent CSV modification)
- **Stale data detection** (`scripts/check_websites.py`):
  - HTTP HEAD health checks with GET fallback (handles 405), 5 classifications: alive/dead/timeout/dns_fail/error
  - Incremental: `health-check: <status> (<code>)` markers in Evidence, `--recheck-dead` flag
  - Integrated as pipeline step 8 (`stale`), dashboard Section 8 (Website Health doughnut chart + dead projects list)
  - Health filter on Projects table (alive/dead/unchecked badges)
- **UX: Ecosystem selector scoping**:
  - Chain dropdown now only visible on Dashboard and Projects (ecosystem-specific pages)
  - Pipeline and Guide are neutral — no global chain dropdown, no chain in footer
  - Pipeline retains its own per-panel chain selectors for each operation

**Pipeline now 10 steps:** dedup → expand-grid → grid → defillama → coingecko → website → promote → stale → notes → sources

### Session 9 — 2026-02-13 (Manual)

**Accomplished:**
- **Import Wizard** (`/import` page): 5-step wizard for merging external researcher CSVs
  - Step 1: Upload CSV or paste from clipboard (auto-detect delimiter)
  - Step 2: Auto-map columns (3-tier: exact → alias → fuzzy). Computed columns (e.g., Final Status) detected as read-only
  - Step 3: Ecosystem split + duplicate detection (name fuzzy match + URL normalization)
  - Step 4: Side-by-side diff preview with per-column merge strategy (append/keep ours/keep theirs/skip)
  - Step 5: Commit with auto-backup, per-chain download, combined download
  - Grid match resolution: primary vs secondary match columns, best match wins
- **New files (3)**:
  - `lib/import_engine.py`: Pure logic module — 13 functions for parsing, column mapping, ecosystem splitting, duplicate detection, merging
  - `dashboard/import_session.py`: In-memory session manager with threading locks and 30-min TTL
  - `dashboard/import_api.py`: Flask blueprint with 7 routes (page, parse, map, analyze, preview, commit, download-combined)
- **Modified files (5)**: `dashboard/__init__.py`, `dashboard/templates/base.html`, `dashboard/static/style.css`, `dashboard/templates/import.html` (new), `dashboard/templates/guide.html`

### Session 10 — 2026-02-13 (Manual)

**Accomplished:**
- **Column rename: "Chain" → "Ecosystem/Chain"**: Updated across 8 files (columns.py, import_engine.py, csv_utils.py, compare.py, popup.js, import.html, guide.html). Backward-compat fallback in `load_csv()` silently renames old "Chain" headers at read time — existing CSVs continue to work.
- **Auto-add ecosystems during import**: When unmatched ecosystems are detected in Step 3, they're automatically added to `chains.json` with minimal config (id, name, default target_assets=USDT/USDC, empty sources). Data directories created. No more Pipeline page detour. Tested: Kava, Polkadot, Tezos all auto-added correctly.
- **Combined download**: New `GET /api/import/download-combined/<session_id>` endpoint generates a single merged CSV with all ecosystems. "Download Combined CSV" button appears in Step 5 when 2+ chains committed.

**Commits:**
- `639480d` — feat: add Import Wizard for merging external researcher data
- `3c4c8f7` — feat: rename Chain to Ecosystem/Chain, auto-add ecosystems, combined download

### Session 11 — 2026-02-13 (Manual)

**Accomplished:**
- **Grid enrichment compatibility fixes** for imported researcher data:
  - **expand_grid_matches.py skip logic fix**: Only skip rows with positive Grid statuses (Active, Found, ✅). Rows with "❌ Not found" are now correctly treated as unmatched and re-processed. Added `POSITIVE_GRID_STATUSES` set.
  - **Root ID query**: New `GET_ROOT_BY_ID_WITH_SUPPORT_QUERY` in Grid client for looking up roots by ID. New `get_root_by_id_with_support()` method.
  - **Admin URL handling in enrich_grid_assets.py**: Detects admin-style URLs (`admin.thegrid.id/?rootId=...`), extracts Root ID, and queries by ID instead of URL. Falls back to URL search for normal URLs.
  - **Root ID normalization in import_engine.py**: Post-merge step extracts Root ID from admin URLs into the Root ID column. `_normalize_admin_urls()` helper function.
- **Dynamic Projects table**:
  - View toggle (Summary/Full) in the table header
  - Summary view: existing 10-column curated view (default)
  - Full view: ALL CSV columns rendered dynamically, horizontally scrollable, sticky first column
  - New `get_project_table_full()` and `get_all_columns()` in data_service.py
  - Works with non-standard CSV schemas (Aptos 34-column format)
  - Notes, Root ID, Matched via, and all other columns now visible

**Commits:**
- `ee596f9` — feat: fix Grid enrichment compatibility with imported data + dynamic Projects table
- `6b4ead8` — data: add imported ecosystem data (Kava, Liquid Network, Tezos, Polkadot, Kaia)

### Session 12 — 2026-02-13 (Manual)

**Accomplished:**
- **View toggle fix**: Inactive button was missing `btn-secondary` class — both buttons rendered as identical filled blue. Added class + tooltips explaining each view.
- **Boolean checkbox rendering**: Full view now renders boolean columns (9 cols) as green checkmarks (TRUE), muted dashes (FALSE), or empty (not evaluated) instead of raw text. Matches The Grid's checkbox style.
- **USDC-only stablecoin bug**: `enrich_assets.py` incorrectly set "Suspect USDT = TRUE" when only USDC was found (used `has_any_stablecoin` which includes USDC). Fixed with three-way logic: USDT → suspect USDT, USDC-only → General Stablecoin (not USDT), neither → Web3.
- **Explicit negative evidence**: Both `enrich_assets.py` and `promote_hints.py` now note "USDC support found, no evidence of USDT support" when USDC is detected without USDT.

**Commits:**
- `5c445ec` — fix: view toggle visibility, boolean checkboxes, USDC-only stablecoin bug

### Session 13 — 2026-02-13 (Manual)

**Accomplished:**
- **Dynamic stablecoin catalog** (`build_stablecoin_catalog.py`): Fetches CoinGecko's stablecoins category (250 coins), filters by $1M market cap floor, excludes USDT/USDC (hardcoded), and caches 220 stablecoins to `config/stablecoin_catalog.json`. Auto-refreshes if >7 days stale.
- **Website scanner expansion** (`enrich_website_keywords.py`): Now loads dynamic stablecoins from catalog and scans for DAI, TUSD, FRAX, PYUSD, and 200+ others alongside USDT/USDC. Dynamic stablecoins bypass the `target_assets` gate (always scanned). `--refresh-catalog` CLI flag forces re-fetch.
- **Promotion logic** (`promote_hints.py`): Generalized `SCAN_PATTERNS` regex to handle any ticker. `parse_scan_note()` now detects `has_other_stablecoin` and `other_stablecoin_symbols`. Strategy 2 triggers on any stablecoin, producing notes like "DAI, PYUSD support found, no evidence of USDT support". Strategy 3 (web3-only) correctly blocks when dynamic stablecoins present.
- **Pipeline integration** (`enrich_all.py`): `run_step_website()` auto-refreshes catalog before scanning.
- **Key invariant preserved**: USDT remains a separate flag. Dynamic stablecoins feed ONLY into "General Stablecoin Adoption."

**Commits:**
- `3f6f1c2` — feat: dynamic CoinGecko stablecoin catalog for website keyword scanning

