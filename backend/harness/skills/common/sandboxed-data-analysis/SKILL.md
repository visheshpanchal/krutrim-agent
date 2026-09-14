---
name: sandboxed-data-analysis
description: How to run computations (returns, moving averages, volatility, backtests) using the sandboxed execute tool. Use whenever a claim needs arithmetic on a series of numbers rather than a lookup.
license: MIT
---

# Sandboxed Data Analysis

## When to Use

Any time you're about to compute something numeric from a series of values (returns, averages, correlations, simple backtests) — don't do the arithmetic in your head, run it.

## How to Use

1. Write the data you're working with to `/workspace/<name>.csv` (via `write_file`) or generate it inline in a script.
2. Use `execute` to run a Python script — `python3 -c "..."`, or write a `.py` file into `/workspace/` and run it. Assume only the Python standard library (`csv`, `statistics`, `math`, `json`); if you want `pandas`/`numpy`, `import` them inside a `try` and fall back to the stdlib when the import fails.
3. Keep the script self-contained: read its inputs from files you already wrote to `/workspace/`, not from the network. Use the `web_fetch`/`web_search` tools to gather data, then feed the results in as files.
4. Read results back with `read_file` or print them directly as `execute` output.
5. Report exactly what was computed (formula, inputs, time window) alongside the number — a bare number without provenance isn't useful in the final report.
