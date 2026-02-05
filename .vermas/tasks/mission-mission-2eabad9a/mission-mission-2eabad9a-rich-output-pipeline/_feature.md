---
status: done
priority: high
---
# rich-output-pipeline

Three prior cycles completed 37 tasks but KPIs stalled at 55% because the core data pipeline (model → formatter) was never fixed. The root cause is clear: parsers work but data is lost before formatting due to duplicate BaseSession models and a formatter that ignores extracted fields. This plan attacks the bottleneck directly: (1) unify the data model so parsed data flows through, (2) update the formatter to render rich content for both session types — this is the single highest-impact change for note_content_richness, (3) implement the analyze subcommand which was explicitly called out as highest-leverage in prior evaluation, (4) add integration tests that measure content richness automatically. Tasks are ordered with proper dependencies since formatter changes depend on the unified model. Using the 'session-insights' squad which is the mature squad for this mission. Prior cycles succeeded with parser work but never addressed the formatter — this plan focuses entirely on the output quality gap.
