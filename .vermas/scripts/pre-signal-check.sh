#!/bin/bash
# pre-signal-check.sh - Run before signal_workflow(done)
#
# This script enforces the "fresh verification before signaling" rule
# learned from Cycle 2, where 0% KPIs reflected signaling failure
# (work existed but signals never fired because verification was skipped).
#
# Usage: .vermas/scripts/pre-signal-check.sh
# Exit codes:
#   0 = Ready to signal done
#   1 = Verification failed, do NOT signal

set -e

echo "=== Pre-Signal Verification ==="
echo ""

# 1. Run tests
echo "[1/2] Running pytest..."
if ! uv run pytest tests/ -q; then
    echo ""
    echo "FAIL: Tests not passing"
    echo "Fix failing tests before signaling done."
    exit 1
fi
echo "Tests: PASS"
echo ""

# 2. Check git status
echo "[2/2] Checking git status..."
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

echo "=== PASS: Ready to signal done ==="
exit 0
