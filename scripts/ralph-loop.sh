#!/bin/bash
# Ralph for Claude Code: The Loop
#
# Runs claude CLI in a loop with context rotation awareness.
# State persists in .ralph/ directory and git commits.
#
# Usage:
#   ./ralph-loop.sh                    # Start from current directory
#   ./ralph-loop.sh /path/to/project   # Start from specific project
#   ./ralph-loop.sh -n 10              # Max 10 iterations
#   ./ralph-loop.sh --branch feat/foo  # Create and work on branch
#   ./ralph-loop.sh -y                 # Skip confirmation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/ralph-common.sh"

# =============================================================================
# FLAG PARSING
# =============================================================================

show_help() {
  cat << 'EOF'
Ralph for Claude Code: The Loop

Usage:
  ./ralph-loop.sh [options] [workspace]

Options:
  -n, --iterations N     Max iterations (default: 20)
  --branch NAME          Create and work on a new branch
  --pr                   Open PR when complete (requires --branch)
  -y, --yes              Skip confirmation prompt
  -h, --help             Show this help

Examples:
  ./ralph-loop.sh                       # Interactive mode
  ./ralph-loop.sh -n 10                 # 10 iterations max
  ./ralph-loop.sh --branch feature/api  # Work on branch
  ./ralph-loop.sh --branch fix/bug --pr # Create PR when done
EOF
}

WORKSPACE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--iterations)
      MAX_ITERATIONS="$2"
      shift 2
      ;;
    --branch)
      USE_BRANCH="$2"
      shift 2
      ;;
    --pr)
      OPEN_PR=true
      shift
      ;;
    -y|--yes)
      SKIP_CONFIRM=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    -*)
      echo "Unknown option: $1"
      echo "Use -h for help."
      exit 1
      ;;
    *)
      WORKSPACE="$1"
      shift
      ;;
  esac
done

# =============================================================================
# ITERATION RUNNER
# =============================================================================

run_iteration() {
  local workspace="$1"
  local iteration="$2"

  local prompt=$(build_prompt "$workspace" "$iteration")

  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "🐛 Ralph Iteration $iteration"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""
  echo "Workspace: $workspace"
  echo "Monitor:   tail -f $workspace/.ralph/activity.log"
  echo ""

  log_activity "$workspace" "Session $iteration started"
  log_progress "$workspace" "**Session $iteration started**"

  cd "$workspace"

  # Run claude with the prompt
  # Using --print to get output, --dangerously-skip-permissions for automation
  local output
  local exit_code=0

  # Create a temp file to capture output
  local temp_output=$(mktemp)

  # Run Claude Code with the prompt
  # Note: Adjust flags based on your claude CLI version
  if claude --print --dangerously-skip-permissions "$prompt" > "$temp_output" 2>&1; then
    exit_code=0
  else
    exit_code=$?
  fi

  output=$(cat "$temp_output")
  rm -f "$temp_output"

  # Check for completion signals in output
  if echo "$output" | grep -q "RALPH COMPLETE"; then
    log_activity "$workspace" "Session $iteration ended - COMPLETE signal"
    echo "COMPLETE"
    return
  fi

  if echo "$output" | grep -q "RALPH GUTTER"; then
    log_activity "$workspace" "Session $iteration ended - GUTTER signal"
    echo "GUTTER"
    return
  fi

  log_activity "$workspace" "Session $iteration ended normally"
  echo ""
}

# =============================================================================
# MAIN LOOP
# =============================================================================

run_ralph_loop() {
  local workspace="$1"

  # Commit any uncommitted work first
  cd "$workspace"
  if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    echo "📦 Committing uncommitted changes..."
    git add -A
    git commit -m "ralph: checkpoint before loop" || true
  fi

  # Create branch if requested
  if [[ -n "$USE_BRANCH" ]]; then
    echo "🌿 Creating branch: $USE_BRANCH"
    git checkout -b "$USE_BRANCH" 2>/dev/null || git checkout "$USE_BRANCH"
  fi

  echo ""
  echo "🚀 Starting Ralph loop..."
  echo ""

  local iteration=1

  while [[ $iteration -le $MAX_ITERATIONS ]]; do
    # Run iteration
    local signal
    signal=$(run_iteration "$workspace" "$iteration")

    # Check task completion via checkbox counting
    local task_status
    task_status=$(check_task_complete "$workspace")

    if [[ "$task_status" == "COMPLETE" ]]; then
      log_progress "$workspace" "**Session $iteration ended** - ✅ TASK COMPLETE"
      echo ""
      echo "═══════════════════════════════════════════════════════════════════"
      echo "🎉 RALPH COMPLETE! All criteria satisfied."
      echo "═══════════════════════════════════════════════════════════════════"
      echo ""
      echo "Completed in $iteration iteration(s)."

      # Open PR if requested
      if [[ "$OPEN_PR" == "true" ]] && [[ -n "$USE_BRANCH" ]]; then
        echo ""
        echo "📝 Opening pull request..."
        git push -u origin "$USE_BRANCH" 2>/dev/null || git push
        if command -v gh &> /dev/null; then
          gh pr create --fill || echo "⚠️  Could not create PR. Create manually."
        fi
      fi

      return 0
    fi

    # Handle signals
    case "$signal" in
      "COMPLETE")
        if [[ "$task_status" == "COMPLETE" ]]; then
          log_progress "$workspace" "**Session $iteration ended** - ✅ COMPLETE (verified)"
          echo ""
          echo "🎉 RALPH COMPLETE!"
          return 0
        else
          log_progress "$workspace" "**Session $iteration ended** - Agent signaled complete but criteria remain"
          echo "⚠️  Agent signaled completion but unchecked criteria remain. Continuing..."
          iteration=$((iteration + 1))
        fi
        ;;
      "GUTTER")
        log_progress "$workspace" "**Session $iteration ended** - 🚨 GUTTER"
        echo ""
        echo "🚨 Gutter detected. Agent is stuck."
        echo "   Check .ralph/errors.log and .ralph/guardrails.md"
        echo "   Consider: manually fix the issue, add a guardrail, restart"
        return 1
        ;;
      *)
        # Agent finished naturally
        if [[ "$task_status" == INCOMPLETE:* ]]; then
          local remaining=${task_status#INCOMPLETE:}
          log_progress "$workspace" "**Session $iteration ended** - $remaining criteria remaining"
          echo "📋 Agent finished. $remaining criteria remaining. Next iteration..."
          iteration=$((iteration + 1))
        else
          iteration=$((iteration + 1))
        fi
        ;;
    esac

    sleep 2
  done

  log_progress "$workspace" "**Loop ended** - ⚠️ Max iterations reached"
  echo ""
  echo "⚠️  Max iterations ($MAX_ITERATIONS) reached."
  return 1
}

# =============================================================================
# MAIN
# =============================================================================

main() {
  if [[ -z "$WORKSPACE" ]]; then
    WORKSPACE="$(pwd)"
  elif [[ "$WORKSPACE" == "." ]]; then
    WORKSPACE="$(pwd)"
  else
    WORKSPACE="$(cd "$WORKSPACE" && pwd)"
  fi

  show_banner

  if ! check_prerequisites "$WORKSPACE"; then
    exit 1
  fi

  if [[ "$OPEN_PR" == "true" ]] && [[ -z "$USE_BRANCH" ]]; then
    echo "❌ --pr requires --branch"
    exit 1
  fi

  show_task_summary "$WORKSPACE"
  echo ""
  echo "Max iterations: $MAX_ITERATIONS"
  [[ -n "$USE_BRANCH" ]] && echo "Branch: $USE_BRANCH"
  [[ "$OPEN_PR" == "true" ]] && echo "Open PR: Yes"
  echo ""

  # Check if already complete
  local task_status=$(check_task_complete "$WORKSPACE")
  if [[ "$task_status" == "COMPLETE" ]]; then
    echo "🎉 Task already complete! All criteria are checked."
    exit 0
  fi

  if [[ "$SKIP_CONFIRM" != "true" ]]; then
    echo "This will run Claude Code in a loop to complete the task."
    echo "Each iteration starts fresh but reads state from .ralph/ files."
    echo ""
    read -p "Start Ralph loop? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "Aborted."
      exit 0
    fi
  fi

  run_ralph_loop "$WORKSPACE"
  exit $?
}

main
