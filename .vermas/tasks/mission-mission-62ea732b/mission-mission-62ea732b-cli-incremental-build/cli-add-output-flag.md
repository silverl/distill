---
status: done
priority: medium
workflow: null
---
# Add --output Flag to Analyze Subcommand

Extend the analyze subcommand to accept --output flag: (1) Add --output argument with default='./insights/' (2) Create output directory if it doesn't exist (3) Print confirmation: 'Output will be written to: {output}'. Test with: session-insights analyze --dir . --output vault/
