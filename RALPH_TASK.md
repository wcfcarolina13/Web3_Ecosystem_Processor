---
task: Ecosystem Research Refactoring
test_command: "cd /Users/roti/gemini_projects/Grid\\ Projects/Ecosystem\\ Research && python3 -c \"from lib.columns import CORRECT_COLUMNS; from lib.matching import normalize_name; from lib.csv_utils import load_csv; from lib.grid_client import GridAPIClient; print('All imports OK')\""
---

# Task: Refactor Ecosystem Research to be Chain-Agnostic

Refactor the ecosystem research tools from Aptos-hardcoded to chain-agnostic,
with modular Python scripts, improved Grid client, and configurable extension.

## Success Criteria

### Phase 3: Extension Generalization
1. [ ] chains.json config created with Aptos as first chain
2. [ ] popup.html has chain selector dropdown
3. [ ] popup.js reads chains.json and populates dropdown
4. [ ] CSV export includes selected chain in Chain column
5. [ ] DefiLlama content script accepts chain from popup context

### Phase 4: Python Script Modularization
6. [ ] lib/columns.py extracts CORRECT_COLUMNS from scripts
7. [ ] lib/matching.py extracts normalize_name, similarity, find_match
8. [ ] lib/csv_utils.py extracts CSV read/write/sanitize utilities
9. [ ] scripts/compare.py replaces both compare scripts (chain-agnostic)
10. [ ] scripts/merge.py replaces both merge scripts (chain-agnostic)
11. [ ] No hardcoded data arrays in any script
12. [ ] All scripts accept --chain CLI argument

### Phase 5: Grid Client
13. [ ] lib/grid_client/client.py with GridAPIClient class (requests, retry, session)
14. [ ] lib/grid_client/queries.py with parameterized GraphQL queries
15. [ ] lib/grid_client/matcher.py with entity matching and confidence scoring
16. [ ] lib/grid_client/models.py with GridMatch/GridMultiMatch dataclasses
17. [ ] lib/grid_client/cli.py with argparse CLI
18. [ ] Old tools/grid_client.py removed

### Phase 6: Data Organization
19. [ ] data/aptos/ contains moved Aptos research files
20. [ ] data/_template/ has empty CSV template with correct headers
21. [ ] data/README.md documents data directory conventions
22. [ ] All scripts resolve data paths from --chain argument

## Notes

- Grid API is read-only; no write operations
- Grid endpoint: https://beta.node.thegrid.id/graphql (public, no auth)
- Advanced Grid client reference: /Users/roti/gemini_projects/News-Summarizer-new/daily_audio_briefing/grid_api.py
- aptofolio.js is inherently Aptos-specific (global var from aptofolio.com) -- leave as-is

---

## Ralph Instructions

1. Work on the next incomplete criterion (marked [ ])
2. Check off completed criteria (change [ ] to [x])
3. Run tests after changes
4. Commit your changes frequently
5. Update .ralph/progress.md with what you accomplished
6. When ALL criteria are [x], say: "RALPH COMPLETE"
7. If stuck 3+ times on same issue, say: "RALPH GUTTER"
