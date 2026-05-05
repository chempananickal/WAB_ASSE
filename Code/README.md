# Python Ecosystem Analysis

This directory contains the analysis pipeline for the thesis study of bug-fix activity, cyclomatic complexity, and simplified SZZ-style bug-introducing commit attribution in widely used Python packages.

The pipeline is designed for reproducible batch runs. It selects packages, prepares repositories, mines recent history with Git, exports CSV and JSON result tables, and optionally renders plots from those results.

## What the pipeline does

At a high level, `analyze_python_ecosystem.py` performs these steps:

1. Query the Libraries.io PyPI ranking ordered by dependent count.
2. Walk down that ranking until `top_n` packages with resolvable GitHub source repositories are found.
3. Confirm selected package metadata against the corresponding PyPI project metadata.
4. Clone or update the selected repositories under `Code/repos/`.
5. Select recent source commits inside the configured lookback window.
6. Parse functions and compute cyclomatic complexity.
7. Identify bug-fix commits from commit-message heuristics.
8. Attribute likely bug-introducing commits with a simplified line-based SZZ pass.
9. Export result tables under `Code/output/latest/` by default.
10. Render plots and derived summaries from the generated tables when requested.

## Directory layout

- `analyze_python_ecosystem.py`: CLI entrypoint and run orchestration.
- `testcfg.toml`: current checked-in run profile.
- `.env.example`: example environment variable file for API keys and secrets.
- `requirements.txt`: Python dependencies.
- `helpers/analysis_core.py`: repository mining, parsing, complexity extraction, bug-fix event generation, and SZZ attribution.
- `helpers/discovery.py`: Libraries.io/PyPI package discovery and repository resolution.
- `helpers/reporting.py`: CSV export, plot generation, and raw JSON export.
- `helpers/common.py`: shared constants, schemas, source-file filters, and helpers.
- `helpers/models.py`: shared dataclasses.
- `helpers/progress.py`: logging and progress-bar event handling.
- `cache/`: cached API responses and per-package mining caches (generated during run).
- `repos/`: cloned source repositories (generated during run).
- `output/`: generated results (generated during run).

## Requirements

Before running the analysis, make sure you have:

- a Python environment with the packages in `Code/requirements.txt`
- Git on `PATH`
- a local Libraries.io API key

Libraries.io access is handled through `pybraries`. The key is loaded from `LIBRARIES_API_KEY` in the environment or from a local `.env` / `Code/.env` file, both of which are ignored by Git.

Example local `.env`:

```env
LIBRARIES_API_KEY=your-key-here
```

## Quick start

Example environment setup:

```bash
source C:/Users/rubin/miniforge3/Scripts/activate asse
pip install -r Code/requirements.txt
```

Run the current checked-in configuration:

```bash
python Code/analyze_python_ecosystem.py -c Code/testcfg.toml
```

Render plots and summaries only from existing outputs by setting `execution.mode = "plot"` in the config and rerunning the same command.

Run discovery only by setting `discovery.discovery_only = true`.

## Configuration

The pipeline is configured through a TOML file passed with `-c/--cfg`.

Current sections in `Code/testcfg.toml`:

- `[discovery]`: package-set size and the safety cap on how far discovery scans down the Libraries.io ranking.
- `[paths]`: output, cache, and repository directories.
- `[mining]`: lookback window, optional commit caps, test inclusion, and Python-only filtering.
- `[execution]`: worker count, compute vs plot mode, logging, cache refresh behavior, and bug-fix timeline granularity.
- `[matching.rename]`: thresholds for rename-aware function matching.

Important settings:

- `top_n`: number of packages selected for analysis.
- `candidate_pool`: maximum number of ranked packages inspected while filling those slots.
- `discovery_only`: stop after package selection.
- `years`: analysis window length.
- `max_szz_commits_per_repo`: optional cap for the SZZ phase; set to `0` to disable SZZ.
- `max_commits_per_repo`: optional cap on mined recent commits per repository.
- `include_tests`: include or exclude tests/examples.
- `python_only`: restrict mining to Python files.
- `mode`: `compute`, `plot`, or `both`.
- `refresh_mining_cache`: force recomputation instead of reusing cached mining outputs.

## Outputs

By default, outputs are written to `Code/output/latest/`.

Key files:

- `top_packages.csv`: selected packages and repository metadata.
- `function_metrics.csv`: function-level complexity and bug-fix touch counts.
- `package_summary.csv`: per-package aggregate statistics.
- `bugfix_event_metrics.csv`: bug-fix events with before/after complexity information.
- `szz_function_attributions.csv`: simplified SZZ attribution rows.
- `raw_function_histories.json`: grouped raw export keyed by function.
- `analysis_run_details.txt`: run configuration and selected-package summary.

Selected plots:

- `plots/complexity_bucket_bugfix_share.png`
- `plots/hotspot_concentration.png`
- `plots/repeat_bugfix_distribution.png`
- `plots/package_normalized_bugfix_density.png`
- `plots/bugfix_complexity_before_after.png`
- `plots/bugfix_complexity_changes.png`
- `plots/bugfix_commit_timeline.png`
- `plots/package_correlations.png`
- `plots/szz_fix_lag_distribution.png`
- `plots/szz_complexity_changes.png`

## Methodology summary

### Package selection

Packages are selected from the Libraries.io PyPI ranking of depended-upon packages. The pipeline walks down that ranking until it has enough packages with resolvable GitHub source repositories.

### Complexity measurement

Cyclomatic complexity is computed with `lizard`. Python files also use the AST path so qualified function names and line spans stay stable for later mining steps.

### Bug-fix identification

Bug-fix commits are identified with a commit-message heuristic based on terms such as `fix`, `bug`, `regression`, `hotfix`, and `patch`.

### SZZ attribution

The SZZ phase is intentionally conservative. It traces deleted lines in bug-fix commits back to blamed commits in the parent revision and uses configurable rename-aware matching for moved or renamed functions.

### Caching

API responses and per-package mining results are cached under `Code/cache/` so repeated runs can reuse earlier work.

## Notes

- This is an exploratory empirical analysis pipeline, not a gold-standard defect-labeling system.
- Package selection is a practical sample, not a complete crawl of the entire PyPI ecosystem.
- Large runs can take a long time because repository mining and SZZ attribution are Git-intensive.