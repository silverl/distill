---
status: done
priority: medium
workflow: null
---
# Wire CLI analyze command to call existing parsers

Connect the analyze subcommand to the existing parser modules (claude.py, codex.py, vermas.py) that were built in prior cycles. The CLI should: (1) Detect which source directories exist (.claude, .codex, .vermas), (2) Call the appropriate parser for each, (3) Print summary of what was found. This completes the core CLI flow. Run full test suite to verify integration. Signal done when CLI can analyze a real directory with session data.
