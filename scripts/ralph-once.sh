#!/bin/bash
# Ralph for Claude Code: Single Iteration
#
# Runs a single Ralph iteration for testing or manual use.
# Useful for verifying setup before running the full loop.
#
# Usage:
#   ./ralph-once.sh              # Run in current directory
#   ./ralph-once.sh /path/to/project

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/ralph-common.sh"

WORKSPACE="${1:-.}"

if [[ "$WORKSPACE" == "." ]]; then
  WORKSPACE="$(pwd)"
else
  WORKSPACE="$(cd "$WORKSPACE" && pwd)"
fi

show_banner

if ! check_prerequisites "$WORKSPACE"; then
  exit 1
fi

# Get current iteration and increment
ITERATION=$(increment_iteration "$WORKSPACE")

echo "Running single iteration (#$ITERATION)..."
echo ""

# Build and display prompt
PROMPT=$(build_prompt "$WORKSPACE" "$ITERATION")

echo "═══════════════════════════════════════════════════════════════════"
echo "📝 Prompt for Claude Code:"
echo "═══════════════════════════════════════════════════════════════════"
echo "$PROMPT"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

echo "To run manually, copy the prompt above and paste into Claude Code."
echo ""
echo "Or run automatically:"
echo "  cd $WORKSPACE && claude \"$PROMPT\""
echo ""

# Ask if user wants to run it
read -p "Run Claude Code now? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  log_activity "$WORKSPACE" "Single iteration $ITERATION started"
  log_progress "$WORKSPACE" "**Single iteration $ITERATION started**"

  cd "$WORKSPACE"
  claude --print "$PROMPT"

  log_activity "$WORKSPACE" "Single iteration $ITERATION ended"
  log_progress "$WORKSPACE" "**Single iteration $ITERATION ended**"

  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "Iteration $ITERATION complete."
  echo ""

  # Show updated task status
  show_task_summary "$WORKSPACE"
fi
