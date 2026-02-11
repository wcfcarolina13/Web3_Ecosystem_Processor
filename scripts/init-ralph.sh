#!/bin/bash
# Ralph for Claude Code: Initialize or Reset State
#
# Creates/resets the .ralph/ directory with fresh state files.
# Useful when starting a new task or recovering from errors.
#
# Usage:
#   ./init-ralph.sh              # Initialize current directory
#   ./init-ralph.sh /path/to/project
#   ./init-ralph.sh --reset      # Reset existing state

set -euo pipefail

WORKSPACE="${1:-.}"
RESET_MODE=false

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset)
      RESET_MODE=true
      shift
      ;;
    *)
      WORKSPACE="$1"
      shift
      ;;
  esac
done

if [[ "$WORKSPACE" == "." ]]; then
  WORKSPACE="$(pwd)"
elif [[ "$WORKSPACE" != /* ]]; then
  WORKSPACE="$(pwd)/$WORKSPACE"
fi

RALPH_DIR="$WORKSPACE/.ralph"

echo "═══════════════════════════════════════════════════════════════════"
echo "🐛 Ralph State Initializer"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Workspace: $WORKSPACE"
echo ""

# Check if .ralph exists
if [[ -d "$RALPH_DIR" ]]; then
  if [[ "$RESET_MODE" == "true" ]]; then
    echo "⚠️  Resetting existing .ralph/ state..."
    rm -rf "$RALPH_DIR"
  else
    echo "⚠️  .ralph/ already exists."
    read -p "Reset state? This will clear all progress. [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "Aborted. Use --reset to force."
      exit 0
    fi
    rm -rf "$RALPH_DIR"
  fi
fi

echo "📁 Creating .ralph/ directory..."
mkdir -p "$RALPH_DIR"

# Create guardrails.md
cat > "$RALPH_DIR/guardrails.md" << 'EOF'
# Ralph Guardrails (Signs)

> Lessons learned from past failures. READ THESE BEFORE ACTING.

## Core Signs

### Sign: Read Before Writing
- **Trigger**: Before modifying any file
- **Instruction**: Always read the existing file first to understand context
- **Added after**: Core principle

### Sign: Test After Changes
- **Trigger**: After any code change
- **Instruction**: Run tests to verify nothing broke
- **Added after**: Core principle

### Sign: Commit Checkpoints
- **Trigger**: Before risky changes
- **Instruction**: Commit current working state first
- **Added after**: Core principle

### Sign: One Task Focus
- **Trigger**: When context grows large
- **Instruction**: Focus on single criterion, complete it, commit, move on
- **Added after**: Core principle

### Sign: Update Progress
- **Trigger**: After completing any criterion
- **Instruction**: Update .ralph/progress.md AND check off the criterion in RALPH_TASK.md
- **Added after**: Core principle

---

## Learned Signs

<!-- Add new signs below as you learn from failures -->

EOF

# Create progress.md
cat > "$RALPH_DIR/progress.md" << 'EOF'
# Progress Log

> Updated by the agent after significant work.

## Summary

- Iterations completed: 0
- Current status: Initialized

## How This Works

Progress is tracked in THIS FILE, not in LLM context.
When context is rotated (fresh agent), the new agent reads this file.
This is how Ralph maintains continuity across iterations.

## Session History

EOF

# Create errors.log
cat > "$RALPH_DIR/errors.log" << 'EOF'
# Error Log

> Failures detected during sessions. Use to update guardrails.

EOF

# Create activity.log
cat > "$RALPH_DIR/activity.log" << 'EOF'
# Activity Log

> Real-time activity logging from sessions.

EOF

# Create iteration counter
echo "0" > "$RALPH_DIR/.iteration"

echo "✓ Created guardrails.md"
echo "✓ Created progress.md"
echo "✓ Created errors.log"
echo "✓ Created activity.log"
echo "✓ Created .iteration counter"
echo ""

# Check for RALPH_TASK.md
if [[ ! -f "$WORKSPACE/RALPH_TASK.md" ]]; then
  echo "📝 Creating RALPH_TASK.md template..."
  cat > "$WORKSPACE/RALPH_TASK.md" << 'EOF'
---
task: Your task description here
test_command: "npm test"
---

# Task: [Your Task Title]

Brief description of what needs to be built.

## Requirements

- Requirement 1
- Requirement 2
- Requirement 3

## Success Criteria

1. [ ] First criterion to complete
2. [ ] Second criterion to complete
3. [ ] Third criterion to complete
4. [ ] All tests pass
5. [ ] Code is committed

## Notes

Add any additional context, constraints, or examples here.

---

## Ralph Instructions

1. Work on the next incomplete criterion (marked [ ])
2. Check off completed criteria (change [ ] to [x])
3. Run tests after changes
4. Commit your changes frequently
5. Update .ralph/progress.md with what you accomplished
6. When ALL criteria are [x], say: "RALPH COMPLETE"
7. If stuck 3+ times on same issue, say: "RALPH GUTTER"
EOF
  echo "✓ Created RALPH_TASK.md template - EDIT THIS FILE with your actual task"
else
  echo "✓ RALPH_TASK.md already exists"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "✅ Ralph initialized!"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Edit RALPH_TASK.md with your actual task and criteria"
echo "  2. Run: ./scripts/ralph-once.sh    # Test single iteration"
echo "  3. Run: ./scripts/ralph-loop.sh    # Start autonomous loop"
echo ""
