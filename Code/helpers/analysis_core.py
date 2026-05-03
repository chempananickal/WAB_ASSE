from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import subprocess
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import lizard
import pandas as pd
from pydriller import Repository
from scipy.stats import pearsonr, spearmanr

from .common import (
    EXCLUDED_PATH_PARTS,
    FUNCTION_METRIC_COLUMNS,
    LIZARD_SOURCE_EXTENSIONS,
    MINING_CACHE_VERSION,
    PACKAGE_SUMMARY_COLUMNS,
    PYTHON_SOURCE_EXTENSIONS,
    SUBPROCESS_TEXT_KWARGS,
    SZZ_COLUMNS,
    empty_function_metrics_frame,
    empty_package_summary_frame,
    empty_szz_frame,
    ensure_directory,
    selected_source_extensions,
    selected_source_globs,
)
from .discovery import normalize_pypi_name
from .models import BugfixDeletionRecord, PackageRecord, ParsedFunction
from .progress import emit_log, emit_progress

BUGFIX_PATTERN = re.compile(
    r"\b(fix(?:e[sd])?|bug(?:fix(?:es)?)?|regression|hotfix|patch(?:ed)?|defect)\b",
    re.IGNORECASE,
)
PROGRESS_UPDATE_BATCH_SIZE = 1


class ComplexityCounter(ast.NodeVisitor):
    """Count cyclomatic complexity using a small AST-based heuristic."""

    def __init__(self) -> None:
        self.score = 1

    def visit_If(self, node: ast.If) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.score += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.score += 1 + len(node.ifs)
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        for case in node.cases:
            pattern = case.pattern
            if not isinstance(pattern, ast.MatchAs) or pattern.pattern is not None:
                self.score += 1
        self.generic_visit(node)


class FunctionCollector(ast.NodeVisitor):
    """Collect functions and methods from a Python AST."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.scope: list[str] = []
        self.class_stack = 0
        self.functions: list[ParsedFunction] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.class_stack += 1
        self.generic_visit(node)
        self.class_stack -= 1
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = ".".join([*self.scope, node.name]) if self.scope else node.name
        counter = ComplexityCounter()
        counter.visit(node)
        kind = "method" if self.class_stack else "function"
        self.functions.append(
            ParsedFunction(
                file_path=self.file_path,
                qualname=qualname,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                complexity=counter.score,
                kind=kind,
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()


def parse_python_functions(source: str, file_path: str) -> list[ParsedFunction]:
    """Parse Python functions and methods from source text."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    collector = FunctionCollector(file_path=file_path)
    collector.visit(tree)
    return collector.functions


def parse_c_family_functions(source: str, file_path: str) -> list[ParsedFunction]:
    """Parse non-Python functions using lizard."""

    try:
        analysis = lizard.analyze_file.analyze_source_code(file_path, source)
    except Exception:
        return []

    functions: list[ParsedFunction] = []
    for item in analysis.function_list:
        qualname = re.sub(r"\s+", " ", item.long_name or item.name).strip()
        functions.append(
            ParsedFunction(
                file_path=file_path,
                qualname=qualname,
                start_line=int(item.start_line),
                end_line=int(item.end_line),
                complexity=int(item.cyclomatic_complexity),
                kind="method" if "::" in qualname else "function",
            )
        )
    return functions


def parse_source_functions(source: str, file_path: str) -> list[ParsedFunction]:
    """Parse supported source files into function descriptors."""

    extension = Path(file_path).suffix.lower()
    if extension in PYTHON_SOURCE_EXTENSIONS:
        return parse_python_functions(source, file_path)
    if extension in LIZARD_SOURCE_EXTENSIONS:
        return parse_c_family_functions(source, file_path)
    return []


def function_by_qualname(
    functions: Sequence[ParsedFunction], qualname: str
) -> ParsedFunction | None:
    """Look up a parsed function by its qualified name."""

    exact = next((item for item in functions if item.qualname == qualname), None)
    if exact is not None:
        return exact

    leaf = qualname.split(".")[-1]
    return next((item for item in functions if item.qualname.split(".")[-1] == leaf), None)


def functions_for_lines(
    functions: Sequence[ParsedFunction], line_numbers: Iterable[int]
) -> dict[str, ParsedFunction]:
    """Map changed line numbers to the functions that contain them."""

    hits: dict[str, ParsedFunction] = {}
    for line_number in line_numbers:
        for function in functions:
            if function.start_line <= line_number <= function.end_line:
                hits[function.qualname] = function
                break
    return hits


def should_analyze_path(path: str | None, include_tests: bool, python_only: bool = False) -> bool:
    """Decide whether a supported source file should be included in the analysis."""

    if not path or Path(path).suffix.lower() not in selected_source_extensions(python_only):
        return False

    path_parts = {part.lower() for part in Path(path).parts}
    file_name = Path(path).name.lower()
    if not include_tests:
        if path_parts & EXCLUDED_PATH_PARTS:
            return False
        if file_name.startswith("test_") or file_name.endswith("_test.py"):
            return False
    return True


def run_git(repo_path: Path, *args: str) -> str:
    """Run a Git command inside a repository."""

    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        check=False,
        **SUBPROCESS_TEXT_KWARGS,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def git_show_file(repo_path: Path, revision: str, file_path: str) -> str | None:
    """Read a file from a Git revision."""

    result = subprocess.run(
        ["git", "show", f"{revision}:{file_path}"],
        cwd=repo_path,
        capture_output=True,
        check=False,
        **SUBPROCESS_TEXT_KWARGS,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def ensure_repository(repo_url: str, repos_dir: Path) -> Path:
    """Clone or update a Git repository."""

    ensure_directory(repos_dir)
    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    target = repos_dir / repo_name

    if target.exists():
        run_git(target, "fetch", "--all", "--tags", "--prune")
        default_branch = (
            run_git(target, "remote", "show", "origin").split("HEAD branch: ")[-1].splitlines()[0]
        )
        run_git(target, "checkout", default_branch)
        run_git(target, "pull", "--ff-only", "origin", default_branch)
        return target

    subprocess.run(
        ["git", "clone", "--filter=blob:none", repo_url, str(target)],
        check=True,
    )
    return target


def recent_source_commit_hashes(
    repo_path: Path, since_date: Any, max_commits: int | None, python_only: bool = False
) -> list[str]:
    """Return the most recent supported-source commit hashes within the window."""

    output = run_git(
        repo_path,
        "rev-list",
        f"--since={since_date.isoformat()}",
        "--no-merges",
        "HEAD",
        "--",
        *selected_source_globs(python_only),
    )
    hashes = [line.strip() for line in output.splitlines() if line.strip()]
    return hashes[:max_commits] if max_commits is not None else hashes


def build_mining_cache_key(
    package: PackageRecord,
    repo_path: Path,
    repo_head: str,
    include_tests: bool,
    python_only: bool,
    skip_szz: bool,
    max_szz_commits_per_repo: int | None,
    max_commits_per_repo: int | None,
    commit_hashes: Sequence[str],
) -> tuple[str, dict[str, Any]]:
    """Build a stable cache key for one package mining configuration."""

    commit_digest = hashlib.sha256("\n".join(commit_hashes).encode("utf-8")).hexdigest()
    payload = {
        "cache_version": MINING_CACHE_VERSION,
        "package": package.name,
        "repo_path": repo_path.as_posix(),
        "repo_head": repo_head,
        "include_tests": include_tests,
        "python_only": python_only,
        "skip_szz": skip_szz,
        "max_szz_commits_per_repo": max_szz_commits_per_repo,
        "max_commits_per_repo": max_commits_per_repo,
        "commit_count": len(commit_hashes),
        "commit_digest": commit_digest,
    }
    serialized = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()[:20], payload


def mining_cache_directory(cache_dir: Path, package: PackageRecord, cache_key: str) -> Path:
    """Return the on-disk cache directory for one package/result key."""

    return cache_dir / "mining" / normalize_pypi_name(package.name) / cache_key


def retag_cached_result(
    package: PackageRecord,
    function_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    szz_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Rewrite cached outputs with the current package label and rank."""

    function_df = function_df.copy()
    package_summary = package_summary.copy()
    szz_df = szz_df.copy()
    if not function_df.empty:
        function_df["package"] = package.name
        function_df["package_rank"] = package.rank
    if not package_summary.empty:
        package_summary["package"] = package.name
        package_summary["package_rank"] = package.rank
    if not szz_df.empty:
        szz_df["package"] = package.name
    return function_df, package_summary, szz_df


def load_mining_cache(
    package: PackageRecord,
    cache_dir: Path,
    cache_key: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    """Load cached mining outputs for a package when all files are present."""

    cache_root = mining_cache_directory(cache_dir, package, cache_key)
    metadata_path = cache_root / "metadata.json"
    function_path = cache_root / "function_metrics.csv"
    package_path = cache_root / "package_summary.csv"
    szz_path = cache_root / "szz_function_attributions.csv"
    if not all(path.exists() for path in [metadata_path, function_path, package_path, szz_path]):
        return None

    function_df = pd.read_csv(function_path)
    package_summary = pd.read_csv(package_path)
    szz_df = pd.read_csv(szz_path)
    if function_df.empty:
        function_df = empty_function_metrics_frame()
    if package_summary.empty:
        package_summary = empty_package_summary_frame(package)
    if szz_df.empty:
        szz_df = empty_szz_frame()
    return retag_cached_result(package, function_df, package_summary, szz_df)


def write_mining_cache(
    package: PackageRecord,
    cache_dir: Path,
    cache_key: str,
    metadata: Mapping[str, Any],
    function_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    szz_df: pd.DataFrame,
) -> None:
    """Persist mining outputs for reuse on later runs."""

    cache_root = mining_cache_directory(cache_dir, package, cache_key)
    ensure_directory(cache_root)
    (cache_root / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    function_df.to_csv(cache_root / "function_metrics.csv", index=False)
    package_summary.to_csv(cache_root / "package_summary.csv", index=False)
    szz_df.to_csv(cache_root / "szz_function_attributions.csv", index=False)


def collect_head_functions(
    repo_path: Path,
    include_tests: bool,
    python_only: bool = False,
    progress_queue: Any | None = None,
    package_name: str | None = None,
) -> tuple[list[ParsedFunction], int]:
    """Collect function inventory for the current HEAD revision."""

    seen_paths: set[Path] = set()
    candidate_paths: list[Path] = []
    for pattern in selected_source_globs(python_only):
        for file_path in repo_path.rglob(pattern):
            if file_path in seen_paths:
                continue
            seen_paths.add(file_path)
            relative_path = file_path.relative_to(repo_path).as_posix()
            if not should_analyze_path(
                relative_path,
                include_tests=include_tests,
                python_only=python_only,
            ):
                continue
            candidate_paths.append(file_path)

    if progress_queue is not None and package_name is not None and candidate_paths:
        emit_progress(
            progress_queue,
            "repo_total",
            package_name,
            amount=max(len(candidate_paths) - 1, 0),
        )

    functions: list[ParsedFunction] = []
    for file_path in candidate_paths:
        relative_path = file_path.relative_to(repo_path).as_posix()
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        functions.extend(parse_source_functions(source, relative_path))
        if progress_queue is not None and package_name is not None:
            emit_progress(progress_queue, "repo_advance", package_name, amount=1)
    return functions, len(candidate_paths)


def contiguous_ranges(line_numbers: Sequence[int]) -> list[tuple[int, int]]:
    """Collapse sorted line numbers into contiguous inclusive ranges."""

    if not line_numbers:
        return []
    ranges: list[tuple[int, int]] = []
    start = line_numbers[0]
    end = line_numbers[0]
    for line_number in line_numbers[1:]:
        if line_number == end + 1:
            end = line_number
            continue
        ranges.append((start, end))
        start = end = line_number
    ranges.append((start, end))
    return ranges


def blame_deleted_lines(
    repo_path: Path, parent_commit: str, file_path: str, line_numbers: Sequence[int]
) -> list[str]:
    """Blame deleted lines in a parent revision."""

    blamed_hashes: list[str] = []
    seen: set[str] = set()
    for start_line, end_line in contiguous_ranges(sorted(set(line_numbers))):
        result = subprocess.run(
            [
                "git",
                "blame",
                "--line-porcelain",
                "-L",
                f"{start_line},{end_line}",
                parent_commit,
                "--",
                file_path,
            ],
            cwd=repo_path,
            capture_output=True,
            check=False,
            **SUBPROCESS_TEXT_KWARGS,
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            if re.match(r"^[0-9a-f]{40} ", line):
                commit_hash = line.split()[0]
                if commit_hash not in seen:
                    seen.add(commit_hash)
                    blamed_hashes.append(commit_hash)
    return blamed_hashes


def compute_complexity_delta(
    repo_path: Path,
    commit_hash: str,
    file_path: str,
    qualname: str,
    snapshot_cache: dict[tuple[str, str], list[ParsedFunction]],
) -> int | None:
    """Compute complexity delta for a function across a commit."""

    try:
        parent_hash = run_git(repo_path, "rev-parse", f"{commit_hash}^").strip()
    except RuntimeError:
        return None

    before_key = (parent_hash, file_path)
    after_key = (commit_hash, file_path)

    if before_key not in snapshot_cache:
        source_before = git_show_file(repo_path, parent_hash, file_path)
        snapshot_cache[before_key] = (
            parse_source_functions(source_before, file_path) if source_before else []
        )
    if after_key not in snapshot_cache:
        source_after = git_show_file(repo_path, commit_hash, file_path)
        snapshot_cache[after_key] = (
            parse_source_functions(source_after, file_path) if source_after else []
        )

    before_function = function_by_qualname(snapshot_cache[before_key], qualname)
    after_function = function_by_qualname(snapshot_cache[after_key], qualname)
    if before_function is None or after_function is None:
        return None
    return after_function.complexity - before_function.complexity


def mine_repository_metrics(
    package: PackageRecord,
    repo_path: Path,
    commit_hashes: Sequence[str],
    include_tests: bool,
    python_only: bool,
    skip_szz: bool,
    max_szz_commits_per_repo: int | None,
    max_commits_per_repo: int | None,
    progress_queue: Any | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Mine function-level metrics, correlations, and SZZ data for one repository."""

    commit_total = len(commit_hashes)
    if not commit_hashes:
        emit_progress(progress_queue, "repo_start", package.name, total=1, phase="no commits")
        emit_log(progress_queue, f"{package.name}: no supported source commits found in the requested window.")
        emit_progress(progress_queue, "repo_done", package.name)
        return empty_function_metrics_frame(), empty_package_summary_frame(package), empty_szz_frame()

    emit_progress(
        progress_queue,
        "repo_start",
        package.name,
        total=max(commit_total + 1, 1),
        phase="inventory",
    )
    emit_log(progress_queue, f"{package.name}: collecting head function inventory.")
    head_functions, inventory_file_count = collect_head_functions(
        repo_path,
        include_tests=include_tests,
        python_only=python_only,
        progress_queue=progress_queue,
        package_name=package.name,
    )
    head_index = {(item.file_path, item.qualname): item for item in head_functions}
    if inventory_file_count == 0:
        emit_progress(progress_queue, "repo_advance", package.name, amount=1)
    emit_progress(
        progress_queue,
        "repo_start",
        package.name,
        total=max(commit_total, 1),
        phase="mining",
    )

    bugfix_touches: Counter[tuple[str, str]] = Counter()
    all_touches: Counter[tuple[str, str]] = Counter()
    bugfix_deletions: list[BugfixDeletionRecord] = []
    bugfix_commit_count = 0

    repository_kwargs: dict[str, Any] = {
        "path_to_repo": str(repo_path),
        "only_no_merge": True,
        "only_modifications_with_file_types": list(selected_source_extensions(python_only)),
    }
    emit_log(
        progress_queue,
        (
            f"{package.name}: mining {commit_total} source commits"
            + (
                f" (capped to {max_commits_per_repo})"
                if max_commits_per_repo is not None
                else ""
            )
        ),
    )

    for commit_hash in commit_hashes:
        emit_progress(
            progress_queue,
            "repo_status",
            package.name,
            status=f"commit {commit_hash[:12]}",
        )
        emit_progress(progress_queue, "repo_advance", package.name, amount=1)

        repository = Repository(**{**repository_kwargs, "only_commits": [commit_hash]})
        commit = next(repository.traverse_commits(), None)
        if commit is None:
            continue

        message = commit.msg or ""
        is_bugfix = bool(BUGFIX_PATTERN.search(message))
        parent_commit = commit.parents[0] if commit.parents else None
        if is_bugfix:
            bugfix_commit_count += 1

        analyzed_files = [
            modified_file
            for modified_file in commit.modified_files
            if should_analyze_path(
                modified_file.new_path or modified_file.old_path,
                include_tests=include_tests,
                python_only=python_only,
            )
        ]
        for modified_file in analyzed_files:
            diff_parsed = modified_file.diff_parsed or {"added": [], "deleted": []}
            added_lines = [line_number for line_number, _ in diff_parsed.get("added", [])]
            deleted_lines = [line_number for line_number, _ in diff_parsed.get("deleted", [])]
            current_path = (modified_file.new_path or modified_file.old_path or "").replace("\\", "/")
            before_path = (modified_file.old_path or current_path or "").replace("\\", "/")

            before_source = modified_file.source_code_before or ""
            after_source = modified_file.source_code or ""
            before_functions = parse_source_functions(before_source, before_path)
            after_functions = parse_source_functions(after_source, current_path)

            touched_functions: dict[tuple[str, str], ParsedFunction] = {}
            for qualname, function in functions_for_lines(after_functions, added_lines).items():
                touched_functions[(current_path, qualname)] = function
            for qualname, function in functions_for_lines(before_functions, deleted_lines).items():
                touched_functions.setdefault((current_path, qualname), function)

            for key in touched_functions:
                all_touches[key] += 1
                if is_bugfix:
                    bugfix_touches[key] += 1

            if skip_szz or not is_bugfix or not parent_commit:
                continue

            deletions_by_function: dict[str, list[int]] = defaultdict(list)
            for qualname, function in functions_for_lines(before_functions, deleted_lines).items():
                contained_lines = [
                    line_number
                    for line_number in deleted_lines
                    if function.start_line <= line_number <= function.end_line
                ]
                if contained_lines:
                    deletions_by_function[qualname].extend(contained_lines)
            for qualname, line_numbers in deletions_by_function.items():
                bugfix_deletions.append(
                    BugfixDeletionRecord(
                        package_name=package.name,
                        bugfix_commit=commit.hash,
                        parent_commit=parent_commit,
                        file_path=before_path,
                        function_qualname=qualname,
                        deleted_lines=tuple(sorted(set(line_numbers))),
                    )
                )

    if max_szz_commits_per_repo is not None:
        by_commit: dict[str, list[BugfixDeletionRecord]] = defaultdict(list)
        for record in bugfix_deletions:
            by_commit[record.bugfix_commit].append(record)
        selected_commits = sorted(by_commit)[:max_szz_commits_per_repo]
        bugfix_deletions = [record for commit_hash in selected_commits for record in by_commit[commit_hash]]

    rows: list[dict[str, Any]] = []
    for key, function in head_index.items():
        rows.append(
            {
                "package": package.name,
                "package_rank": package.rank,
                "file_path": function.file_path,
                "function": function.qualname,
                "kind": function.kind,
                "complexity": function.complexity,
                "n_bugfix_commits": int(bugfix_touches.get(key, 0)),
                "n_touch_commits": int(all_touches.get(key, 0)),
                "was_bugfixed": int(bugfix_touches.get(key, 0) > 0),
            }
        )
    function_df = pd.DataFrame(rows, columns=FUNCTION_METRIC_COLUMNS)

    spearman_value = math.nan
    spearman_pvalue = math.nan
    pearson_value = math.nan
    pearson_pvalue = math.nan
    if not function_df.empty and function_df["complexity"].nunique() > 1 and function_df["n_bugfix_commits"].nunique() > 1:
        pearson_value, pearson_pvalue = pearsonr(
            function_df["complexity"], function_df["n_bugfix_commits"]
        )
        spearman_result = spearmanr(function_df["complexity"], function_df["n_bugfix_commits"])
        spearman_value = float(spearman_result.statistic)
        spearman_pvalue = float(spearman_result.pvalue)

    package_summary = pd.DataFrame(
        [
            {
                "package": package.name,
                "package_rank": package.rank,
                "functions_analyzed": int(len(function_df)),
                "mean_complexity": float(function_df["complexity"].mean()) if not function_df.empty else math.nan,
                "median_complexity": float(function_df["complexity"].median()) if not function_df.empty else math.nan,
                "functions_bugfixed": int(function_df["was_bugfixed"].sum()) if not function_df.empty else 0,
                "bugfix_commits": int(bugfix_commit_count),
                "spearman_r": spearman_value,
                "spearman_p": spearman_pvalue,
                "pearson_r": pearson_value,
                "pearson_p": pearson_pvalue,
            }
        ],
        columns=PACKAGE_SUMMARY_COLUMNS,
    )

    szz_rows: list[dict[str, Any]] = []
    if not skip_szz:
        emit_progress(
            progress_queue,
            "repo_start",
            package.name,
            total=max(len(bugfix_deletions), 1),
            phase="szz",
        )
        emit_progress(progress_queue, "repo_status", package.name, status="")
        snapshot_cache: dict[tuple[str, str], list[ParsedFunction]] = {}
        pending_szz_updates = 0
        for deletion in bugfix_deletions:
            blamed_hashes = blame_deleted_lines(
                repo_path, deletion.parent_commit, deletion.file_path, deletion.deleted_lines
            )
            pending_szz_updates += 1
            if pending_szz_updates >= PROGRESS_UPDATE_BATCH_SIZE:
                emit_progress(
                    progress_queue,
                    "repo_advance",
                    package.name,
                    amount=pending_szz_updates,
                )
                pending_szz_updates = 0
            for blamed_hash in blamed_hashes:
                if blamed_hash in {deletion.bugfix_commit, "0" * 40}:
                    continue
                complexity_delta = compute_complexity_delta(
                    repo_path,
                    blamed_hash,
                    deletion.file_path,
                    deletion.function_qualname,
                    snapshot_cache,
                )
                szz_rows.append(
                    {
                        "package": package.name,
                        "bugfix_commit": deletion.bugfix_commit,
                        "bug_introducing_commit": blamed_hash,
                        "file_path": deletion.file_path,
                        "function": deletion.function_qualname,
                        "complexity_delta": complexity_delta,
                        "complexity_increased": (
                            int(complexity_delta > 0) if complexity_delta is not None else math.nan
                        ),
                    }
                )
        if pending_szz_updates:
            emit_progress(
                progress_queue,
                "repo_advance",
                package.name,
                amount=pending_szz_updates,
            )
    emit_progress(progress_queue, "repo_phase", package.name, phase="done")
    emit_progress(progress_queue, "repo_done", package.name)
    emit_log(
        progress_queue,
        (
            f"{package.name}: {len(function_df):,} functions, {bugfix_commit_count} bug-fix commits"
            + (f", {len(szz_rows)} SZZ attributions" if not skip_szz else "")
        ),
    )
    szz_df = pd.DataFrame(szz_rows, columns=SZZ_COLUMNS)
    return function_df, package_summary, szz_df


def mine_package_task(
    package: PackageRecord,
    repo_path: Path,
    commit_hashes: Sequence[str],
    include_tests: bool,
    python_only: bool,
    skip_szz: bool,
    max_szz_commits_per_repo: int | None,
    max_commits_per_repo: int | None,
    progress_queue: Any | None,
    cache_dir: Path | None,
    cache_key: str | None,
    cache_metadata: Mapping[str, Any] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run repository mining for one package in a worker process."""

    function_df, package_summary, szz_df = mine_repository_metrics(
        package=package,
        repo_path=repo_path,
        commit_hashes=commit_hashes,
        include_tests=include_tests,
        python_only=python_only,
        skip_szz=skip_szz,
        max_szz_commits_per_repo=max_szz_commits_per_repo,
        max_commits_per_repo=max_commits_per_repo,
        progress_queue=progress_queue,
    )
    if cache_dir is not None and cache_key is not None and cache_metadata is not None:
        write_mining_cache(
            package=package,
            cache_dir=cache_dir,
            cache_key=cache_key,
            metadata=cache_metadata,
            function_df=function_df,
            package_summary=package_summary,
            szz_df=szz_df,
        )
    return function_df, package_summary, szz_df