# Python Ecosystem Analysis

This directory contains the analysis pipeline used for the paper's empirical study of widely depended-upon Python packages. The pipeline discovers packages from PyPI and deps.dev, mines their source repositories with Git, measures function-level cyclomatic complexity, and relates that complexity to bug-fix activity and simplified SZZ-style attribution.

The project is built for reproducibility rather than interactivity. It can either compute fresh results, render plots and summaries from preexisting CSV outputs, or do both in one run.

## Research scope

The analysis is designed to answer three questions:

1. Which Python packages are most central when ranked by reverse dependencies rather than downloads?
2. Are more complex functions associated with more bug-fix activity?
3. When simplified SZZ attribution finds likely bug-introducing commits, do those commits tend to increase complexity?

## What the pipeline does

At a high level, `analyze_python_ecosystem.py` performs the following steps:

1. Collect a candidate pool of packages.
2. Rerank that pool by `directDependentCount`.
3. Resolve each selected package's source repository.
4. Clone or update the repositories under `Code/repos/`.
5. Select recent source commits inside the requested time window.
6. Measure function-level cyclomatic complexity.
7. Count how often bug-fix commits touch each function.
8. Run a simplified line-based SZZ pass over bug-fix deletions.
9. Export CSV tables under `Code/output/latest/` by default.
10. Render plots and summary artifacts either immediately or later from those saved tables.

## Repository layout

- `analysis.toml`: default commented TOML configuration for discovery, paths, mining, execution, and rename matching.
- `analyze_python_ecosystem.py`: CLI entrypoint and phase orchestration.
- `helpers/analysis_core.py`: Git mining, parsing, SZZ attribution, caching, and repository analysis.
- `helpers/discovery.py`: package discovery, reverse-dependency lookup, and repository resolution.
- `helpers/reporting.py`: CSV export and plot generation.
- `helpers/common.py`: shared constants, schemas, filesystem helpers, and source filters.
- `helpers/models.py`: dataclasses used across the pipeline.
- `helpers/progress.py`: logging and progress-bar event handling.
- `requirements.txt`: direct Python dependencies.
- `cache/`: cached discovery responses and per-package mining results.
- `repos/`: cloned source repositories.
- `output/`: generated CSVs and plots.

## Requirements

Before running the analysis, make sure the following are available:

- A Python environment with the packages in `Code/requirements.txt`.
- Git on `PATH`, because repository mining is implemented directly on top of Git CLI commands.
- Network access for cold runs, since package metadata and reverse-dependency counts are fetched from PyPI and deps.dev.


## Quick start

*First, set up the environment and install dependencies:*

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
pip install -r Code/requirements.txt
```

The CLI now has a single runtime option besides help: `-c/--cfg`, which points to a TOML config file. If you do not pass it, the checked-in `Code/analysis.toml` is used.

Run a discovery-only pass by setting `discovery_only = true` in `Code/analysis.toml`, then running:

```bash
python Code/analyze_python_ecosystem.py
```

Run the full default analysis with the checked-in config:

```bash
python Code/analyze_python_ecosystem.py
```

Use a different config file when you want a separate run profile:

```bash
python Code/analyze_python_ecosystem.py --cfg Code/analysis.toml
```

For example, to regenerate plots and summaries from an existing output directory without rerunning mining, set `execution.mode = "plot"` in a config file and run:

```bash
python Code/analyze_python_ecosystem.py --cfg Code/analysis.toml
```

Likewise, faster bounded analysis, Python-only runs, cache refreshes, and SZZ disabling are now configuration edits rather than ad hoc CLI flags. The defaults and commented optional keys in `Code/analysis.toml` are intended to be the primary run documentation.

## Configuration reference

The TOML config is grouped by concern:

- `[discovery]`: package selection and whether to stop after discovery.
- `[paths]`: output, cache, and repository locations.
- `[mining]`: lookback window, optional commit caps, test inclusion, and Python-only filtering.
- `[execution]`: worker count, compute versus plot mode, logging, cache refresh behavior, and bug-fix timeline granularity.
- `[matching.rename]`: thresholds that decide when a function move or rename is still trusted as the same logical function.

Relative paths in `[paths]` resolve from the directory containing the config file.

## CLI reference

The CLI intentionally exposes only two switches:

| Option | Meaning |
| --- | --- |
| `-c`, `--cfg` | Path to the TOML configuration file. Defaults to `Code/analysis.toml`. |
| `-h`, `--help` | Show CLI help. |

Run `python Code/analyze_python_ecosystem.py --help` for the minimal CLI help text.

## Example workflow

Disable SZZ entirely by setting the following in the config:

```toml
[mining]
max_szz_commits_per_repo = 0
```

Render plots and summaries only:

```toml
[execution]
mode = "plot"
```

Show the bug-fix timeline by quarter instead of month or year:

```toml
[execution]
bugfix_timeline_granularity = "quarter"
```

Restrict the analysis to Python files only:

```toml
[mining]
python_only = true
```

Refresh cached mining results:

```toml
[execution]
refresh_mining_cache = true
```

Use a faster bounded run while iterating:

```toml
[mining]
max_szz_commits_per_repo = 50
max_commits_per_repo = 250

[execution]
workers = 4
mode = "compute"
```

## Outputs

By default, results are written to `Code/output/latest/`.

### CSV files

- `top_packages.csv`: selected packages and discovery metadata.
- `function_metrics.csv`: function-level complexity and bug-fix touch counts.
- `package_summary.csv`: per-package aggregates and correlation statistics.
- `bugfix_event_metrics.csv`: one row per bugfix-touched function with complexity before and after the bug-fix commit.
- `complexity_bucket_summary.csv`: complexity buckets and bug-fix shares.
- `hotspot_concentration_summary.csv`: cumulative bug-fix share captured by the most complex functions.
- `repeat_bugfix_distribution_summary.csv`: recurrence tail showing how often already-bugfixed functions are fixed again.
- `package_normalized_bugfix_density_summary.csv`: package-level bug-fix and introducing-commit rates normalized by analyzed function count.
- `bugfix_complexity_change_summary.csv`: summary counts for how bug-fix commits changed function complexity.
- `szz_function_attributions.csv`: function-level SZZ attribution rows.
- `szz_fix_lag_summary.csv`: per-package summaries of the time lag between attributed introducing commits and their fixing commits.
- `szz_summary.csv`: summary counts for the SZZ complexity-change categories.
- `analysis_summary.md`: Markdown summary of the current result set.
- `raw_function_histories.json`: grouped raw results keyed by function, including bug-fix events, SZZ attributions, and commit messages.

### Plots

- `plots/top_packages.png`: reverse-dependency ranking of selected packages.
- `plots/complexity_bucket_bugfix_share.png`: bug-fix share by complexity bucket.
- `plots/hotspot_concentration.png`: cumulative share of bug-fix activity captured by the most complex functions.
- `plots/repeat_bugfix_distribution.png`: recurrence profile for functions that are bugfixed more than once.
- `plots/package_normalized_bugfix_density.png`: normalized per-package bug-fix burden comparison.
- `plots/bugfix_complexity_before_after.png`: complexity before versus after bug-fix commits for touched functions.
- `plots/bugfix_complexity_changes.png`: categorical view of how bug-fix commits changed function complexity.
- `plots/bugfix_commit_timeline.png`: bug-fix commit counts over time, grouped by month, quarter, or year depending on config.
- `plots/package_correlations.png`: package-level correlation view.
- `plots/szz_fix_lag_distribution.png`: distribution of time-to-fix for attributed bug-introducing commits.
- `plots/szz_complexity_changes.png`: SZZ complexity-change summary, generated only when SZZ attributions exist.

## Methodology notes

### Package ranking

The ranking target is ecosystem centrality, not download popularity. The pipeline therefore uses reverse-dependency information from deps.dev rather than relying on PyPI download counts.

### Complexity measurement

Cyclomatic complexity is measured with `lizard` for all supported source files so the metric is consistent across languages. Python files additionally use the built-in AST to preserve qualified function names, method boundaries, and line spans. Complexity-bucket plots use clean round-number bucket widths chosen near a 10-bucket target, anchored to the highest complexity reached by bugfixed functions when that information exists. Rarer higher-complexity non-bugfixed outliers are folded into the final bucket so the plot stays focused on the range where bug-fix activity actually appears.

### Bug-fix identification

Bug-fix commits are identified with a commit-message heuristic using tokens such as `fix`, `bugfix`, `regression`, and `hotfix`. This keeps the rule explicit, cheap to audit, and easy to describe in the paper.

### SZZ attribution

The SZZ stage is intentionally conservative. It traces deleted lines in bug-fix commits back to blamed commits in the parent revision, and it includes a rename-aware fallback for moved files and structurally matched renamed functions. The same configurable rename matcher also drives the bug-fix before/after complexity comparison. By default, a renamed function is accepted when either at least 60% of its span still overlaps, there is any overlap with at most 6 lines of total boundary drift, or a stronger overlap-and-name score clears 0.99 with at most 3 lines of drift. These thresholds live under `[matching.rename]` in `analysis.toml`. It does not attempt issue-link mining or more aggressive semantic reconstruction.

### Caching and repositories

Per-package mining results are cached under `Code/cache/mining/` using the repository state, selected commit window, and analysis parameters. Repositories are kept as full clones under `Code/repos/`; partial clones were avoided because deferred blob hydration interfered with commit-diff materialization during mining. Because the plotting stage can be rerun independently by setting `execution.mode = "plot"`, the saved CSV outputs under `Code/output/` are the contract between compute and reporting.

## Limitations

- The candidate set is a practical sample, not the full PyPI universe.
- The bug-fix classifier is heuristic and depends on commit-message quality.
- The SZZ stage is suitable for exploratory empirical analysis, not for constructing a gold-standard defect dataset.
- Rename-aware matching is conservative and threshold-based; large refactors can still break longitudinal function identity, but the acceptance thresholds are configurable in `[matching.rename]`.
- When `--max-commits` is used, results describe the bounded recent-commit sample rather than the full history inside the requested time window.
- Running many workers can improve throughput, but it also increases memory, disk, and Git process pressure.

## Using the outputs in the paper

The generated outputs support several empirical views:

1. Ecosystem concentration among high-impact Python packages.
2. Whether bug-fix activity is concentrated in a relatively small set of complex hotspot functions.
3. How often already-bugfixed functions become repeat maintenance hotspots.
4. How bug-fix burden differs across packages after normalizing for analyzed size.
5. Whether attributed bug-introducing commits tend to coincide with higher complexity and how long those attributed bugs remain latent before they are fixed.