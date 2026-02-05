---
status: done
priority: high
---
# cli-incremental-build

The CLI has failed 4 times because we kept attempting the full skeleton at once. This plan takes a radically incremental approach: (1) verify project structure first - this isolates dependency/configuration issues, (2) create the absolute minimum CLI that proves Click wiring works, (3) add one subcommand with minimal args, (4) finally wire to existing parsers. Each task is independently testable and small enough to debug if it fails. The existing session-insights squad and workflow are appropriate - the issue was task granularity, not infrastructure.
