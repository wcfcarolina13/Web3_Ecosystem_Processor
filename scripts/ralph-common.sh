#!/bin/bash
# Ralph for Claude Code: Common utilities
#
# Shared functions for ralph loop scripts.
# Adapted from ralph-wiggum-cursor for Claude Code CLI.

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================

# Token thresholds (Claude Code doesn't expose token counts directly,
# so we estimate based on file sizes and conversation length)
WARN_THRESHOLD="${WARN_THRESHOLD:-70000}"
ROTATE_THRESHOLD="${ROTATE_THRESHOLD:-80000}"

# Iteration limits
MAX_ITERATIONS="${MAX_ITERATIONS:-20}"

# Feature flags
USE_BRANCH="${USE_BRANCH:-}"
OPEN_PR="${OPEN_PR:-false}"
SKIP_CONFIRM="${SKIP_CONFIRM:-false}"

# =============================================================================
# BASIC HELPERS
# =============================================================================

# Cross-platform sed -i
sedi() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

# Get current iteration
get_iteration() {
  local workspace="${1:-.}"
  local state_file="$workspace/.ralph/.iteration"

  if [[ -f "$state_file" ]]; then
    cat "$state_file"
  else
    echo "0"
  fi
}

# Set iteration number
set_iteration() {
  local workspace="${1:-.}"
  local iteration="$2"
  local ralph_dir="$workspace/.ralph"

  mkdir -p "$ralph_dir"
  echo "$iteration" > "$ralph_dir/.iteration"
}

# Increment iteration
increment_iteration() {
  local workspace="${1:-.}"
  local current=$(get_iteration "$workspace")
  local next=$((current + 1))
  set_iteration "$workspace" "$next"
  echo "$next"
}

# =============================================================================
# LOGGING
# =============================================================================

log_activity() {
  local workspace="${1:-.}"
  local message="$2"
  local ralph_dir="$workspace/.ralph"
  local timestamp=$(date '+%H:%M:%S')

  mkdir -p "$ralph_dir"
  echo "[$timestamp] $message" >> "$ralph_dir/activity.log"
}

log_error() {
  local workspace="${1:-.}"
  local message="$2"
  local ralph_dir="$workspace/.ralph"
  local timestamp=$(date '+%H:%M:%S')

  mkdir -p "$ralph_dir"
  echo "[$timestamp] $message" >> "$ralph_dir/errors.log"
}

log_progress() {
  local workspace="$1"
  local message="$2"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  local progress_file="$workspace/.ralph/progress.md"

  echo "" >> "$progress_file"
  echo "### $timestamp" >> "$progress_file"
  echo "$message" >> "$progress_file"
}

# =============================================================================
# TASK MANAGEMENT
# =============================================================================

# Check if task is complete (all checkboxes checked)
check_task_complete() {
  local workspace="$1"
  local task_file="$workspace/RALPH_TASK.md"

  if [[ ! -f "$task_file" ]]; then
    echo "NO_TASK_FILE"
    return
  fi

  # Count unchecked checkbox list items
  local unchecked
  unchecked=$(grep -cE '^[[:space:]]*([-*]|[0-9]+\.)[[:space:]]+\[ \]' "$task_file" 2>/dev/null) || unchecked=0

  if [[ "$unchecked" -eq 0 ]]; then
    echo "COMPLETE"
  else
    echo "INCOMPLETE:$unchecked"
  fi
}

# Count criteria (returns done:total)
count_criteria() {
  local workspace="${1:-.}"
  local task_file="$workspace/RALPH_TASK.md"

  if [[ ! -f "$task_file" ]]; then
    echo "0:0"
    return
  fi

  local total done_count
  total=$(grep -cE '^[[:space:]]*([-*]|[0-9]+\.)[[:space:]]+\[(x| )\]' "$task_file" 2>/dev/null) || total=0
  done_count=$(grep -cE '^[[:space:]]*([-*]|[0-9]+\.)[[:space:]]+\[x\]' "$task_file" 2>/dev/null) || done_count=0

  echo "$done_count:$total"
}

# =============================================================================
# PROMPT BUILDING
# =============================================================================

# Build the Ralph prompt for Claude Code
build_prompt() {
  local workspace="$1"
  local iteration="$2"

  cat << EOF
# Ralph Iteration $iteration

You are an autonomous development agent using the Ralph methodology.

## FIRST: Read State Files

Before doing anything:
1. Read \`RALPH_TASK.md\` - your task and completion criteria
2. Read \`.ralph/guardrails.md\` - lessons from past failures (FOLLOW THESE)
3. Read \`.ralph/progress.md\` - what's been accomplished
4. Read \`.ralph/errors.log\` - recent failures to avoid

## Working Directory

You are already in a git repository. Work HERE, not in a subdirectory:
- Do NOT run \`git init\` - the repo already exists
- Do NOT run scaffolding that creates nested directories
- All code should live at the repo root or in subdirectories you create manually

## Git Protocol

Ralph's strength is state-in-git, not LLM memory. Commit early and often:
1. After completing each criterion, commit your changes with descriptive message
2. After any significant code change: commit with descriptive message
3. Before any risky refactor: commit current state as checkpoint

Your commits ARE your memory across iterations.

## Task Execution

1. Work on the next unchecked criterion in RALPH_TASK.md (look for \`[ ]\`)
2. Run tests after changes (check RALPH_TASK.md for test_command)
3. Mark completed criteria: Edit RALPH_TASK.md and change \`[ ]\` to \`[x]\`
4. Update \`.ralph/progress.md\` with what you accomplished
5. When ALL criteria show \`[x]\`: say "RALPH COMPLETE - all criteria satisfied"
6. If stuck 3+ times on same issue: say "RALPH GUTTER - need fresh context"

## Learning from Failures

When something fails:
1. Check \`.ralph/errors.log\` for failure history
2. Figure out the root cause
3. Add a Sign to \`.ralph/guardrails.md\`:

\`\`\`markdown
### Sign: [Descriptive Name]
- **Trigger**: When this situation occurs
- **Instruction**: What to do instead
- **Added after**: Iteration $iteration - what happened
\`\`\`

Begin by reading the state files.
EOF
}

# =============================================================================
# PREREQUISITES
# =============================================================================

check_prerequisites() {
  local workspace="$1"
  local task_file="$workspace/RALPH_TASK.md"

  # Check for task file
  if [[ ! -f "$task_file" ]]; then
    echo "❌ No RALPH_TASK.md found in $workspace"
    return 1
  fi

  # Check for claude CLI
  if ! command -v claude &> /dev/null; then
    echo "❌ claude CLI not found"
    echo "   Install Claude Code: https://claude.ai/download"
    return 1
  fi

  # Check for git repo
  if ! git -C "$workspace" rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Not a git repository"
    echo "   Ralph requires git for state persistence."
    return 1
  fi

  return 0
}

# =============================================================================
# DISPLAY HELPERS
# =============================================================================

show_banner() {
  echo "═══════════════════════════════════════════════════════════════════"
  echo "🐛 Ralph for Claude Code: Autonomous Development Loop"
  echo "═══════════════════════════════════════════════════════════════════"
  echo ""
}

show_task_summary() {
  local workspace="$1"
  local task_file="$workspace/RALPH_TASK.md"

  echo "📋 Task Summary:"
  echo "─────────────────────────────────────────────────────────────────"
  head -30 "$task_file"
  echo "─────────────────────────────────────────────────────────────────"
  echo ""

  local total_criteria done_criteria remaining
  total_criteria=$(grep -cE '^[[:space:]]*([-*]|[0-9]+\.)[[:space:]]+\[(x| )\]' "$task_file" 2>/dev/null) || total_criteria=0
  done_criteria=$(grep -cE '^[[:space:]]*([-*]|[0-9]+\.)[[:space:]]+\[x\]' "$task_file" 2>/dev/null) || done_criteria=0
  remaining=$((total_criteria - done_criteria))

  echo "Progress: $done_criteria / $total_criteria criteria complete ($remaining remaining)"
}
