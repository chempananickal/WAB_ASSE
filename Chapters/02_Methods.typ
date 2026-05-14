#let methods_content = [
  = Methods

  == Package Selection

  Initially, the study aimed to focus on the ten most downloaded packages on @pypi. However, on further investigation, it was found that download count alone was not a reliable indicator of whether the package is truly a "lynchpin" package within the ecosystem. For example, the most downloaded package as of the time of writing was *boto3*, which is exclusively used by @aws. The download count is inflated by the widespread use of @aws services. However, it is not general purpose and is completely irrelevant to the majority of Python developers.

  To better capture the intended population of important packages, the selection process was adjusted to consider the top-ranked packages in the Libraries.io ranking of the most depended-upon PyPI projects @libraries_io. This ranking is based on the number of other packages that depend on a given package (reverse dependencies), which is a more direct measure of its centrality and importance within the ecosystem. Starting from the top of that ranking, packages were considered in order until ten projects with resolvable GitHub source repositories had been identified. The selected release version and basic package metadata were then verified against the corresponding PyPI project metadata @pypicite.

  #let selected_package = csv("../Code/output/latest/selected_package_overview.csv", row-type: dictionary)
  #let selected_package_cells = (
    selected_package
      .map(row => (
        [#row.at("package")],
        [#row.at("version")],
        [#row.at("commit_code")],
        // [#row.at("functions_analyzed")],
      ))
      .flatten()
  )

  #figure(
    table(
      columns: 3,
      inset: 6pt,
      align: (left, left, left),
      table.header(
        [*Package*], [*Version*], [*Commit*],
        // [*Functions analyzed*]
      ),
      ..selected_package_cells,
    ),
    caption: [The selected packages and their number of analyzed functions.],
  ) <selected-package-table>

  The final sample spans scientific computing (numpy, scipy, pandas), testing infrastructure (pytest, pytest-cov), validation (pydantic), plotting (matplotlib), command-line tooling (click), code formatting (black), and HTTP infrastructure (requests).For each package, its GitHub repository was cloned, and commits were mined for a five-year window between 05. May 2021 and 05. May 2026. Across these repositories, the analysis covered 47,151 functions in total.

  #pdf.attach(
    "../Code/output/latest/analysis_run_details.txt",
    description: "Details as pertaining to the analysis run.",
  )

  == Complexity Analysis

  Many of the selected packages are written in multiple programming languages aside from Python (for example, parts of numpy are written in C and Fortran). Therefore, a cross-language cyclomatic complexity analysis tool was required for a comprehensive assessment. Lizard, a Python module which can compute the cyclomatic complexity of source code in over 25 programming languages @lizard, was therefore chosen for this purpose.

  == SZZ Attribution

  Due to the limited scope of this study, Github Issues were not used to identify bug-fixing commits. Instead, bug-fixing commits are identified heuristically by matching commit messages against a set of keywords: _fix_, _fixes_, _fixed_, _bug_, _bugfix_, _regression_, _hotfix_, _patched_, and _defect_ (case-insensitive).

  To approximate likely bug-introducing commits, the study applies a simplified @szz procedure @szzcite. For each identified bug-fixing commit, deleted lines from supported source files are collected from the diff against the parent revision and grouped by the function they belonged to. `git blame --line-porcelain` is then run on those contiguous deleted-line ranges against the parent revision to find which commits originally introduced them. Blamed commits that coincide with the bug-fixing commit itself, or that are null commits, are excluded. The remaining blamed revisions are treated as candidate bug-introducing commits.

  To estimate the effect of each bug-introducing commit on function complexity, the function is located in both the version before and after the blamed commit. The primary matching strategy is by exact function name. If the function is only found on one side (for example because it was moved or renamed), a structural fallback is used. Candidate functions of the same kind are scored based on how much their line spans overlap, how similar their names are according to `SequenceMatcher` from Python's `difflib` standard library module, and how far their boundaries have shifted.

  A candidate is accepted if the overlap ratio reaches at least 60%, or if there is any overlap at all and the boundary shift is within 6 lines, or if the names are nearly identical and the boundary shift is within 3 lines. If no match can be established on either side, the entry is excluded from the complexity-delta analysis. This is consistent with the broader warning that mining GitHub repositories requires careful treatment of noisy metadata and workflow-specific artifacts @mining_github.

  Only files with an extension recognized by Lizard were included in the analysis. Documentation files (`.md`, `.rst`, `.txt`, `.asciidoc`, etc.) and anything under a `doc` or `docs` directory were excluded, as were test files (`test_*.py`, `*_test.py`), test directories (`test/`, `tests/`, `testing/`), build and environment artifacts (`build/`, `dist/`, `.git/`, etc.), and example and benchmark directories (`example/`, `examples/`, `benchmarks/`, etc.).
]
