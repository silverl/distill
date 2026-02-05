---
status: done
priority: medium
workflow: null
---
# Wire CLI to Parser Discovery Stub

Connect CLI to existing parsers or create stubs: (1) In cli.py, import from parsers/ directory (2) Add logic to discover which session sources exist in --dir (.claude/, .codex/, .vermas/) (3) Print discovered sources: 'Found sources: .claude, .vermas' (4) If no parsers exist yet, create stub modules that return empty lists. This completes the 'Usable CLI' KPI requirement.
