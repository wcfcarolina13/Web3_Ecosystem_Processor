# Data Directory

Per-chain research data for ecosystem research projects.

## Structure

```
data/
├── _template/
│   └── ecosystem_research.csv    # Header-only template (27 standard columns)
├── aptos/
│   ├── aptos_usdt_ecosystem_research.csv   # Main research spreadsheet
│   ├── comparison_report.txt                # DefiLlama comparison results
│   ├── new_projects_to_add.csv              # New projects from comparison
│   └── dappradar_new_projects.csv           # New projects from DappRadar
├── <chain>/
│   └── <chain>_<focus>_ecosystem_research.csv
└── README.md
```

## Conventions

### Directory naming
- One directory per chain, named with the lowercase chain ID (e.g., `aptos`, `tron`, `starknet`)
- Use `_template/` for the header-only template CSV

### File naming
- Main CSV: `<chain>_<focus>_ecosystem_research.csv` (e.g., `aptos_usdt_ecosystem_research.csv`)
- The `<focus>` is typically the stablecoin or research objective (e.g., `usdt`)
- Comparison reports: `comparison_report_<source>.txt`
- New projects: `new_projects_<source>.csv`

### Column standard
- All CSVs must use the 27 standard columns defined in `lib/columns.py`
- Use `scripts/transform_csv_columns.py` to fix column mismatches
- Use `data/_template/ecosystem_research.csv` as a reference

### Initializing a new chain
```bash
./scripts/init_chain.sh <chain> <focus>
# Example: ./scripts/init_chain.sh tron usdt
```

This creates `data/<chain>/<chain>_<focus>_ecosystem_research.csv` with the correct headers.
