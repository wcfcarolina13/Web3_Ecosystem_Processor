# Ecosystem Research

Tools for discovering, cataloging, and enriching Web3 project data for [The Grid](https://thegrid.id).

## Overview

This project provides a pipeline for ecosystem research across any blockchain network:

1. **Scrape** project data from ecosystem directories (DefiLlama, DappRadar, CoinGecko, etc.) using the Chrome extension
2. **Compare** scraped data against existing research CSVs to find duplicates and new projects
3. **Merge** new discoveries into the master research sheet
4. **Enrich** with data from The Grid's GraphQL API

## Structure

```
config/          Chain definitions and column specs
extension/       Chrome Manifest V3 scraper extension
scripts/         CLI scripts for compare/merge + Ralph automation
lib/             Shared Python modules (matching, CSV, Grid client)
data/<chain>/    Per-chain research data (CSVs, reports)
```

## Quick Start

```bash
# Initialize a new chain research project
./scripts/init_chain.sh tron usdt

# Compare scraped data against existing CSV
python3 scripts/compare.py --chain aptos --source defillama --data data/aptos/defillama_scraped.json

# Merge new projects into the master CSV
python3 scripts/merge.py --chain aptos --source defillama

# Query The Grid API
python3 -m lib.grid_client search_products "Aptos" --limit 10
```

## Chrome Extension

Load the `extension/` folder as an unpacked Chrome extension. See `extension/README.md` for details.

## Ralph

This project uses the [Ralph methodology](../Ralph/) for autonomous iterative development. See `RALPH_TASK.md` for current task state.

```bash
./scripts/init-ralph.sh    # Initialize Ralph state
./scripts/ralph-once.sh    # Run single iteration
./scripts/ralph-loop.sh    # Run autonomous loop
```
