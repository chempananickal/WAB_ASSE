from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lizard_languages
import pandas as pd

from .models import PackageRecord

EXCLUDED_PATH_PARTS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".tox",
    ".venv",
    "benchmarks",
    "build",
    "dist",
    "docs",
    "doc",
    "example",
    "examples",
    "site-packages",
    "test",
    "tests",
    "testing",
    "venv",
}
LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}
MINING_CACHE_VERSION = 2
SUBPROCESS_TEXT_KWARGS: dict[str, Any] = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}
PYTHON_SOURCE_EXTENSIONS = {".py"}
FUNCTION_METRIC_COLUMNS = [
    "package",
    "package_rank",
    "file_path",
    "function",
    "kind",
    "complexity",
    "n_bugfix_commits",
    "n_touch_commits",
    "was_bugfixed",
]
PACKAGE_SUMMARY_COLUMNS = [
    "package",
    "package_rank",
    "functions_analyzed",
    "mean_complexity",
    "median_complexity",
    "functions_bugfixed",
    "bugfix_commits",
    "spearman_r",
    "spearman_p",
    "pearson_r",
    "pearson_p",
]
SZZ_COLUMNS = [
    "package",
    "bugfix_commit",
    "bug_introducing_commit",
    "file_path",
    "function",
    "complexity_delta",
    "complexity_increased",
]


def lizard_source_extensions() -> set[str]:
    """Return the source-file extensions recognized by lizard."""

    extensions: set[str] = set()
    for reader in lizard_languages.languages():
        for extension in getattr(reader, "ext", []):
            normalized = extension.strip()
            if not normalized:
                continue
            extensions.add(f".{normalized.lower()}")
    return extensions


LIZARD_SOURCE_EXTENSIONS = lizard_source_extensions()
SUPPORTED_SOURCE_EXTENSIONS = tuple(sorted(PYTHON_SOURCE_EXTENSIONS | LIZARD_SOURCE_EXTENSIONS))


def selected_source_extensions(python_only: bool) -> tuple[str, ...]:
    """Return the active source-file extension set for the current run."""

    if python_only:
        return tuple(sorted(PYTHON_SOURCE_EXTENSIONS))
    return SUPPORTED_SOURCE_EXTENSIONS


def selected_source_globs(python_only: bool) -> tuple[str, ...]:
    """Return the active glob set for the current run."""

    return tuple(f"*{extension}" for extension in selected_source_extensions(python_only))


def ensure_directory(path: Path) -> None:
    """Create a directory if it does not already exist."""

    path.mkdir(parents=True, exist_ok=True)


def empty_function_metrics_frame() -> pd.DataFrame:
    """Create an empty function metrics dataframe with stable columns."""

    return pd.DataFrame(columns=FUNCTION_METRIC_COLUMNS)


def empty_package_summary_frame(package: PackageRecord) -> pd.DataFrame:
    """Create an empty package summary row for a package."""

    return pd.DataFrame(
        [
            {
                "package": package.name,
                "package_rank": package.rank,
                "functions_analyzed": 0,
                "mean_complexity": math.nan,
                "median_complexity": math.nan,
                "functions_bugfixed": 0,
                "bugfix_commits": 0,
                "spearman_r": math.nan,
                "spearman_p": math.nan,
                "pearson_r": math.nan,
                "pearson_p": math.nan,
            }
        ],
        columns=PACKAGE_SUMMARY_COLUMNS,
    )


def empty_szz_frame() -> pd.DataFrame:
    """Create an empty SZZ dataframe with stable columns."""

    return pd.DataFrame(columns=SZZ_COLUMNS)


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)