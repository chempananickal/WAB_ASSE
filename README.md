# WAB_ASSE

This repository contains a Typst-based thesis project and the Python analysis pipeline used to mine Python package repositories for complexity, bug-fix activity, and SZZ-style bug-introducing commit attributions.

## Repository layout

- `main.typ`: thesis entry point.
- `exposee.typ`: exposé entry point.
- `template.typ` and `info.typ`: shared document metadata and layout helpers.
- `Chapters/`: thesis and exposé content files.
- `Code/`: the analysis pipeline, configuration, generated outputs, and repository/cache directories.
- `references.bib`: bibliography shared by the Typst documents.

## Analysis pipeline

The Python analysis pipeline lives under `Code/`.

- Entry point: `python Code/analyze_python_ecosystem.py -c Code/testcfg.toml`
- Main configuration: `Code/testcfg.toml`
- Selected package list: `Code/output/latest/top_packages.csv`
- Aggregated outputs: `Code/output/latest/`

The current package-selection workflow is:

1. Query the Libraries.io PyPI ranking ordered by dependent count.
2. Walk down that ranking until `top_n` packages with resolvable GitHub source repositories have been found.
3. Use PyPI project metadata to confirm the selected release version, summary, and repository fallback information.

## Local setup

The analysis code expects a Python environment with the dependencies listed in `Code/requirements.txt`.

Libraries.io access is handled through `pybraries` and requires a local API key.

1. Create a local `.env` file in the repository root or in `Code/`.
2. Add `LIBRARIES_API_KEY=...` to that file.
3. Keep that file untracked; `.gitignore` already excludes it.

## Running the analysis

Typical commands:

- `python Code/analyze_python_ecosystem.py -c Code/testcfg.toml`
- `python Code/analyze_python_ecosystem.py --help`

Important configuration knobs in `Code/testcfg.toml`:

- `discovery.top_n`: number of packages selected for analysis.
- `discovery.candidate_pool`: safety cap on how far down the Libraries.io ranking discovery will inspect.
- `discovery.discovery_only`: stop after package selection and output generation.
- `mining.years`: analysis window length.
- `mining.include_tests`: whether test/example files are included.
- `mining.python_only`: whether to restrict mining to Python files.
- `execution.mode`: compute, plot, or both.

## Building the documents

Compile the Typst documents with:

- `typst compile main.typ main.pdf`
- `typst compile exposee.typ exposee.pdf`

The workspace also includes VS Code tasks for watching the generated PDFs.
