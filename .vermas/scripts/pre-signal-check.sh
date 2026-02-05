#!/bin/bash
# pre-signal-check.sh - Run before signal_workflow(done)
#
# This script enforces the "fresh verification before signaling" rule
# learned from Cycle 2, where 0% KPIs reflected signaling failure
# (work existed but signals never fired because verification was skipped).
#
# Cycle 4 addition: Now verifies deliverables are tracked in git.
# This closes the verification gap that caused 4 consecutive failures
# where code existed in worktrees but was never committed.
#
# Cycle 12 addition: Detects artifact-only commits (no src/ changes).
# This prevents marking tasks "done" when only workflow artifacts were committed.
#
# Usage: .vermas/scripts/pre-signal-check.sh [deliverable1] [deliverable2] ...
# Exit codes:
#   0 = Ready to signal done
#   1 = Verification failed, do NOT signal

set -e

# Parse flags
ALLOW_NO_DELIVERABLES=false
ALLOW_ARTIFACT_ONLY=false
DELIVERABLES=()

for arg in "$@"; do
    if [ "$arg" = "--allow-no-deliverables" ]; then
        ALLOW_NO_DELIVERABLES=true
    elif [ "$arg" = "--allow-artifact-only" ]; then
        ALLOW_ARTIFACT_ONLY=true
    else
        DELIVERABLES+=("$arg")
    fi
done

DELIVERABLE_COUNT=${#DELIVERABLES[@]}

# Fail-safe: require deliverables unless explicitly opted out
if [ $DELIVERABLE_COUNT -eq 0 ] && [ "$ALLOW_NO_DELIVERABLES" = false ]; then
    echo "ERROR: No deliverables specified."
    echo ""
    echo "Every task should have deliverables to verify. This prevents"
    echo "signaling 'done' when code exists but was never committed."
    echo ""
    echo "Usage: pre-signal-check.sh <deliverable1> [deliverable2] ..."
    echo "       pre-signal-check.sh --allow-no-deliverables  # For docs-only changes"
    echo "       pre-signal-check.sh --allow-artifact-only    # For workflow-only changes"
    echo ""
    echo "Examples:"
    echo "  pre-signal-check.sh src/module.py tests/test_module.py"
    echo "  pre-signal-check.sh --allow-no-deliverables  # Only if no code changes"
    echo "  pre-signal-check.sh --allow-artifact-only src/config.py  # Workflow artifacts OK"
    exit 1
fi

if [ $DELIVERABLE_COUNT -gt 0 ]; then
    TOTAL_STEPS=4
else
    TOTAL_STEPS=2
fi

echo "=== Pre-Signal Verification ==="
echo ""

# 1. Run tests
echo "[1/$TOTAL_STEPS] Running pytest..."
if ! uv run pytest tests/ -q; then
    echo ""
    echo "FAIL: Tests not passing"
    echo "Fix failing tests before signaling done."
    exit 1
fi
echo "Tests: PASS"
echo ""

# 2. Check git status
echo "[2/$TOTAL_STEPS] Checking git status..."
if [ -n "$(git status --porcelain)" ]; then
    echo ""
    echo "FAIL: Uncommitted changes detected"
    echo ""
    git status --short
    echo ""
    echo "Commit or stash changes before signaling done."
    exit 1
fi
echo "Git status: CLEAN"
echo ""

# 3. Verify deliverables are tracked (if provided)
if [ $DELIVERABLE_COUNT -gt 0 ]; then
    echo "[3/$TOTAL_STEPS] Verifying deliverables are tracked in git..."
    for file in "${DELIVERABLES[@]}"; do
        if ! git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
            echo ""
            echo "FAIL: $file is NOT tracked in git"
            echo ""
            echo "This file exists but was never committed."
            echo "Run: git add $file && git commit -m 'Add $file'"
            exit 1
        fi
        echo "  ✓ $file"
    done
    echo "Deliverables: $DELIVERABLE_COUNT file(s) TRACKED"
    echo ""
fi

# 4. Check for artifact-only commits (if deliverables provided)
# This catches the pattern from Cycle 12 where tasks were marked "done"
# but only workflow artifacts (.vermas/*) were committed, not actual code.
if [ $DELIVERABLE_COUNT -gt 0 ] && [ "$ALLOW_ARTIFACT_ONLY" = false ]; then
    echo "[4/$TOTAL_STEPS] Checking for source code changes..."

    # Get the base branch (usually main)
    BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")

    # Check if there are any changes to src/ or tests/ compared to base
    SRC_DIFF=$(git diff "$BASE_BRANCH" -- src/ tests/ 2>/dev/null | head -1)

    if [ -z "$SRC_DIFF" ]; then
        echo ""
        echo "WARNING: No changes to src/ or tests/ compared to $BASE_BRANCH"
        echo ""
        echo "This appears to be an artifact-only commit. The task produced"
        echo "workflow files (.vermas/*, etc.) but no actual source code."
        echo ""
        echo "If this is intentional (e.g., docs-only or config changes):"
        echo "  pre-signal-check.sh --allow-artifact-only <deliverables>"
        echo ""
        echo "Otherwise, this task may not have produced real value."
        echo "Review what was actually delivered before signaling done."
        echo ""
        exit 1
    fi
    echo "Source changes: DETECTED"
    echo ""
fi

echo "=== PASS: Ready to signal done ==="
exit 0
