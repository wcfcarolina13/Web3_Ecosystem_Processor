#!/bin/bash
# Initialize a new chain research directory with template CSV
#
# Usage:
#   ./scripts/init_chain.sh <chain> <focus>
#   ./scripts/init_chain.sh tron usdt
#   ./scripts/init_chain.sh starknet usdt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
TEMPLATE_CSV="$DATA_DIR/_template/ecosystem_research.csv"

# Usage check
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <chain> <focus>"
  echo ""
  echo "Examples:"
  echo "  $0 tron usdt"
  echo "  $0 starknet usdt"
  echo "  $0 solana usdt"
  echo ""
  echo "Creates: data/<chain>/<chain>_<focus>_ecosystem_research.csv"
  exit 1
fi

CHAIN="$1"
FOCUS="$2"
CHAIN_DIR="$DATA_DIR/$CHAIN"
CSV_FILE="$CHAIN_DIR/${CHAIN}_${FOCUS}_ecosystem_research.csv"

# Check template exists
if [[ ! -f "$TEMPLATE_CSV" ]]; then
  echo "❌ Template CSV not found: $TEMPLATE_CSV"
  echo "   Run from the project root directory."
  exit 1
fi

# Check if already exists
if [[ -f "$CSV_FILE" ]]; then
  echo "⚠️  CSV already exists: $CSV_FILE"
  echo "   Remove it first if you want to start fresh."
  exit 1
fi

# Create directory and copy template
mkdir -p "$CHAIN_DIR"
cp "$TEMPLATE_CSV" "$CSV_FILE"

echo "✅ Initialized chain research directory:"
echo "   Directory: $CHAIN_DIR"
echo "   CSV file:  $CSV_FILE"
echo ""
echo "Next steps:"
echo "  1. Add '$CHAIN' to config/chains.json (and extension/config/chains.json)"
echo "  2. Scrape data using the Chrome extension"
echo "  3. Run comparison: python scripts/compare.py --chain $CHAIN --source defillama --data <scraped.json>"
echo "  4. Run merge:      python scripts/merge.py --chain $CHAIN --source defillama"
