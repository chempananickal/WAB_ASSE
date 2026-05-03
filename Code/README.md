# Python Ecosystem Analysis

This directory contains a reproducible analysis pipeline for the term-paper question:

1. Which Python packages are the most depended upon?
2. Is higher cyclomatic complexity associated with more bug-fix activity at the function level?
3. Do bug-introducing commits, as approximated with a simplified SZZ pass, tend to increase complexity?

## What the script does

`analyze_python_ecosystem.py` performs the full workflow:

1. Downloads a large candidate set of popular PyPI projects.
2. Resolves each candidate's default release and reverse dependency counts.
3. Reranks candidates by direct dependent count.
4. Resolves each selected package's source repository.
5. Clones or updates the repositories.
6. Mines the last `N` years of supported source commits with PyDriller.
7. Measures function-level cyclomatic complexity.
8. Counts how often bug-fix commits touch each function.
9. Runs a simplified line-based SZZ attribution pass.
10. Exports CSV files, plots, and a Markdown summary.

## Code layout

The entrypoint stays in `analyze_python_ecosystem.py` and now focuses on CLI parsing plus phase orchestration.

Most implementation details live under `Code/helpers/`:

- `analysis_core.py`: source parsing, Git access, caching, and repository mining.
- `common.py`: shared constants, file-scope filters, dataframe schemas, and small filesystem helpers.
- `discovery.py`: PyPI and deps.dev discovery, HTTP caching, and repository resolution.
- `models.py`: dataclasses shared across the pipeline.
- `progress.py`: compact logging and progress-bar event handling.
- `reporting.py`: CSV export, plots, and summary rendering.

## Why this uses more than the PyPI JSON API

PyPI exposes first-party project metadata, but it does not expose a public reverse dependency leaderboard. The pipeline therefore combines:

- PyPI project metadata for package summaries and project URLs.
- deps.dev package graph endpoints for reverse dependency counts and repository resolution.

That tradeoff is documented explicitly because "most downloaded" and "most depended upon" are different rankings, and only the latter answers the research question.

## Installation

Activate the prepared environment first:

```bash
source C:/Users/rubin/miniforge3/Scripts/activate asse
```

Install the direct Python dependencies listed in `requirements.txt`:

```bash
pip install -r Code/requirements.txt
```

## Typical usage

Run a quick discovery-only pass:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 200 --discovery-only
```

Run the full two-year analysis:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2
```

Run the full analysis but skip the SZZ phase:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2 --skip-szz
```

Run the same analysis in a Python-only mode when you want to exclude non-Python files for testing:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2 --python-only
```

Limit the number of bug-fix commits that enter the SZZ phase when iterating on performance:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2 --max-szz-commits-per-repo 50
```

Bound the mining run to the most recent Python commits per repository when you want a faster initial analysis:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2 --max-commits-per-repo 250 --max-szz-commits-per-repo 50
```

Use multiple worker processes to mine packages in parallel:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2 --max-commits-per-repo 250 --max-szz-commits-per-repo 50 --workers 4
```

Reuse cached per-package mining results on repeated runs with the same effective commit window and analysis parameters:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2 --max-commits-per-repo 250 --skip-szz --workers 4
```

Force a cache refresh when you want to recompute those per-package mining results:

```bash
python Code/analyze_python_ecosystem.py --top-n 10 --candidate-pool 250 --years 2 --max-commits-per-repo 250 --skip-szz --workers 4 --refresh-mining-cache
```

## Important methodological notes

- Reverse dependency ranking is computed from `directDependentCount` on the default package version.
- Bug-fix commits are identified with a message heuristic using tokens such as `fix`, `bugfix`, `regression`, and `hotfix`.
- Cyclomatic complexity is estimated with a mixed parser approach: Python files use the built-in AST and other supported source files use `lizard`.
- `--python-only` restricts discovery, mining, and complexity analysis to `.py` files while leaving the default mixed-language behavior unchanged.
- The SZZ phase is intentionally simple and transparent:
  - it traces deleted lines in bug-fix commits back to blamed commits in the parent revision;
  - it does not attempt rename-aware or issue-link-aware disambiguation;
  - it does not rely on a built-in PyDriller SZZ implementation, because PyDriller does not provide one.

## Outputs

The default output directory is `Code/output/latest/`.

Expected artifacts include:

- `top_packages.csv`
- `function_metrics.csv`
- `package_summary.csv`
- `complexity_bucket_summary.csv`
- `szz_function_attributions.csv`
- `szz_summary.csv`
- `analysis_summary.md`
- `plots/*.png`

## Limitations

- The discovery stage reranks a large practical candidate pool rather than scanning the full PyPI index, because no public first-party endpoint exposes global reverse dependency counts.
- Function identity is path-and-qualified-name based, so aggressive refactors can reduce longitudinal matching quality.
- The SZZ phase is a heuristic suitable for exploratory analysis, not a gold-standard defect dataset.
- When `--max-commits-per-repo` is used, the empirical results describe the bounded recent-commit sample inside the requested time window rather than the full two-year history.
- `--workers` parallelizes package mining, which usually helps on multi-core machines but can increase memory and disk pressure when several repositories are mined at once.
- Per-package mining results are cached under `Code/cache/mining/` using the repo HEAD, selected commit window, and analysis parameters; use `--refresh-mining-cache` to bypass that cache.
- Supported source analysis currently covers Python plus any source-file extension recognized by the installed `lizard` version.

## Suggested paper framing

The exported outputs support at least three empirical angles:

1. Package ecosystem concentration: which libraries dominate the dependency graph.
2. Complexity-risk relationship: whether more complex functions attract more bug-fix activity.
3. Complexity introduction hypothesis: whether attributed bug-introducing commits disproportionately increase complexity.