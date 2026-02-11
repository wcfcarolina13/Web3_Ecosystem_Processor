# Ecosystem Research - Claude Code Instructions

This project uses the **Ralph autonomous development methodology**.
Read RALPH_TASK.md, .ralph/guardrails.md, .ralph/progress.md, and .ralph/errors.log before every action.

## Project Context

Ecosystem research tools for The Grid -- scraping, comparing, merging, and enriching
Web3 project data from multiple sources (DefiLlama, DappRadar, CoinGecko, etc.)
and matching against The Grid's GraphQL API.

## Architecture

- `config/` -- chains.json and column definitions
- `extension/` -- Chrome Manifest V3 extension for scraping ecosystem directories
- `scripts/` -- CLI Python scripts for compare/merge + Ralph automation scripts
- `lib/` -- Shared Python modules (columns, matching, csv_utils, grid_client)
- `data/<chain>/` -- Per-chain research data (CSVs, reports)

## Key Rules

1. **Chain-agnostic**: No hardcoded chain names or data in scripts. Use --chain CLI arg + chains.json config.
2. **Grid is read-only**: Only query The Grid API. No mutations. Endpoint: https://beta.node.thegrid.id/graphql
3. **CSV column order matters**: Always use CORRECT_COLUMNS from lib/columns.py. Never redefine it inline.
4. **Data lives in data/<chain>/**: Each chain gets its own subdirectory under data/.
5. **No inline data arrays**: Scraped data goes to files, not Python constants.

## Test Command

```bash
python3 -c "from lib.columns import CORRECT_COLUMNS; from lib.matching import normalize_name; from lib.csv_utils import load_csv; from lib.grid_client import GridAPIClient; print('All imports OK')"
```

## Ralph Scripts

- `./scripts/init-ralph.sh` -- Initialize .ralph/ state
- `./scripts/ralph-once.sh` -- Run single iteration
- `./scripts/ralph-loop.sh` -- Run autonomous loop

## Data Sources

| Source | Method | Best For |
|--------|--------|----------|
| DefiLlama API | `api.llama.fi/protocols` | DeFi protocols (TVL, URLs, Twitter) |
| DappRadar | DOM scraping | Games and broader dapp coverage |
| CoinGecko | DOM scraping | Token-based projects |
| AptoFolio | Global variable | Aptos-specific community data |

## Grid API

- Endpoint: `https://beta.node.thegrid.id/graphql`
- Public access, no auth required
- Entity types: profileInfos, products, assets, entities
- Sort by `gridRank` for importance
- Use slugs (not IDs) for filtering
