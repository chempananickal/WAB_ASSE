from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import tomllib

try:
    from .common import LOG_LEVELS
except ImportError:
    from Code.helpers.common import LOG_LEVELS


VALID_MODES = {"compute", "plot", "both"}


@dataclass(frozen=True)
class RenameMatchConfig:
    """Thresholds controlling when two functions are treated as the same logical unit."""

    min_overlap_ratio: float = 0.6
    max_boundary_distance_with_overlap: int = 6
    min_score: float = 0.99
    max_boundary_distance_for_score: int = 3

    def as_dict(self) -> dict[str, float | int]:
        return {
            "min_overlap_ratio": self.min_overlap_ratio,
            "max_boundary_distance_with_overlap": self.max_boundary_distance_with_overlap,
            "min_score": self.min_score,
            "max_boundary_distance_for_score": self.max_boundary_distance_for_score,
        }


DEFAULT_RENAME_MATCH_CONFIG = RenameMatchConfig()


@dataclass(frozen=True)
class AnalysisConfig:
    """Materialized runtime configuration for the analysis pipeline."""

    config_path: Path
    top_n: int
    candidate_pool: int
    years: float
    output_dir: Path
    cache_dir: Path
    repos_dir: Path
    max_szz_commits_per_repo: int | None
    max_commits_per_repo: int | None
    workers: int | None
    mode: str
    log_level: str
    refresh_mining_cache: bool
    discovery_only: bool
    include_tests: bool
    python_only: bool
    rename_match: RenameMatchConfig = field(default_factory=RenameMatchConfig)


def _require_table(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"Config section [{key}] must be a TOML table.")
    return value


def _require_known_keys(table: Mapping[str, Any], section: str, allowed: set[str]) -> None:
    unknown_keys = sorted(set(table) - allowed)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ValueError(f"Unknown config key(s) in [{section}]: {joined}")


def _read_int(table: Mapping[str, Any], key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Config key {key!r} must be an integer.")
    return value


def _read_optional_int(table: Mapping[str, Any], key: str, default: int | None = None) -> int | None:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Config key {key!r} must be an integer when set.")
    return value


def _read_float(table: Mapping[str, Any], key: str, default: float) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Config key {key!r} must be a number.")
    return float(value)


def _read_bool(table: Mapping[str, Any], key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Config key {key!r} must be true or false.")
    return value


def _read_string(table: Mapping[str, Any], key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Config key {key!r} must be a string.")
    return value


def _read_optional_path(table: Mapping[str, Any], key: str, default: Path, base_dir: Path) -> Path:
    raw_value = table.get(key)
    if raw_value is None:
        value = default
    else:
        if not isinstance(raw_value, str):
            raise ValueError(f"Config key {key!r} must be a path string.")
        value = Path(raw_value).expanduser()
    return (base_dir / value).resolve() if not value.is_absolute() else value.resolve()


def load_analysis_config(config_path: Path) -> AnalysisConfig:
    """Load, validate, and materialize the TOML analysis configuration."""

    config_path = config_path.expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("rb") as handle:
        raw_config = tomllib.load(handle)

    if not isinstance(raw_config, Mapping):
        raise ValueError("The config file must contain TOML tables.")

    _require_known_keys(raw_config, "root", {"discovery", "paths", "mining", "execution", "matching"})

    discovery = _require_table(raw_config, "discovery")
    paths = _require_table(raw_config, "paths")
    mining = _require_table(raw_config, "mining")
    execution = _require_table(raw_config, "execution")
    matching = _require_table(raw_config, "matching")
    rename_matching = _require_table(matching, "rename")

    _require_known_keys(discovery, "discovery", {"top_n", "candidate_pool", "discovery_only"})
    _require_known_keys(paths, "paths", {"output_dir", "cache_dir", "repos_dir"})
    _require_known_keys(
        mining,
        "mining",
        {"years", "max_szz_commits_per_repo", "max_commits_per_repo", "include_tests", "python_only"},
    )
    _require_known_keys(
        execution,
        "execution",
        {"workers", "mode", "log_level", "refresh_mining_cache"},
    )
    _require_known_keys(matching, "matching", {"rename"})
    _require_known_keys(
        rename_matching,
        "matching.rename",
        {
            "min_overlap_ratio",
            "max_boundary_distance_with_overlap",
            "min_score",
            "max_boundary_distance_for_score",
        },
    )

    base_dir = config_path.parent
    top_n = _read_int(discovery, "top_n", 10)
    candidate_pool = _read_int(discovery, "candidate_pool", 250)
    years = _read_float(mining, "years", 2.0)
    max_szz_commits_per_repo = _read_optional_int(mining, "max_szz_commits_per_repo")
    max_commits_per_repo = _read_optional_int(mining, "max_commits_per_repo")
    workers = _read_optional_int(execution, "workers")
    mode = _read_string(execution, "mode", "both")
    log_level = _read_string(execution, "log_level", "INFO").upper()
    refresh_mining_cache = _read_bool(execution, "refresh_mining_cache", False)
    discovery_only = _read_bool(discovery, "discovery_only", False)
    include_tests = _read_bool(mining, "include_tests", False)
    python_only = _read_bool(mining, "python_only", False)

    if top_n <= 0:
        raise ValueError("discovery.top_n must be greater than 0.")
    if candidate_pool <= 0:
        raise ValueError("discovery.candidate_pool must be greater than 0.")
    if candidate_pool < top_n:
        raise ValueError("discovery.candidate_pool must be greater than or equal to discovery.top_n.")
    if years <= 0:
        raise ValueError("mining.years must be greater than 0.")
    if max_szz_commits_per_repo is not None and max_szz_commits_per_repo < 0:
        raise ValueError("mining.max_szz_commits_per_repo must be 0 or greater when set.")
    if max_commits_per_repo is not None and max_commits_per_repo <= 0:
        raise ValueError("mining.max_commits_per_repo must be greater than 0 when set.")
    if workers is not None and workers <= 0:
        raise ValueError("execution.workers must be greater than 0 when set.")
    if mode not in VALID_MODES:
        allowed = ", ".join(sorted(VALID_MODES))
        raise ValueError(f"execution.mode must be one of: {allowed}")
    if log_level not in LOG_LEVELS:
        allowed = ", ".join(LOG_LEVELS)
        raise ValueError(f"execution.log_level must be one of: {allowed}")

    rename_match = RenameMatchConfig(
        min_overlap_ratio=_read_float(rename_matching, "min_overlap_ratio", DEFAULT_RENAME_MATCH_CONFIG.min_overlap_ratio),
        max_boundary_distance_with_overlap=_read_int(
            rename_matching,
            "max_boundary_distance_with_overlap",
            DEFAULT_RENAME_MATCH_CONFIG.max_boundary_distance_with_overlap,
        ),
        min_score=_read_float(rename_matching, "min_score", DEFAULT_RENAME_MATCH_CONFIG.min_score),
        max_boundary_distance_for_score=_read_int(
            rename_matching,
            "max_boundary_distance_for_score",
            DEFAULT_RENAME_MATCH_CONFIG.max_boundary_distance_for_score,
        ),
    )
    if not 0 <= rename_match.min_overlap_ratio <= 1:
        raise ValueError("matching.rename.min_overlap_ratio must be between 0 and 1.")
    if rename_match.max_boundary_distance_with_overlap < 0:
        raise ValueError("matching.rename.max_boundary_distance_with_overlap must be 0 or greater.")
    if rename_match.min_score < 0:
        raise ValueError("matching.rename.min_score must be 0 or greater.")
    if rename_match.max_boundary_distance_for_score < 0:
        raise ValueError("matching.rename.max_boundary_distance_for_score must be 0 or greater.")

    return AnalysisConfig(
        config_path=config_path,
        top_n=top_n,
        candidate_pool=candidate_pool,
        years=years,
        output_dir=_read_optional_path(paths, "output_dir", Path("output") / "latest", base_dir),
        cache_dir=_read_optional_path(paths, "cache_dir", Path("cache"), base_dir),
        repos_dir=_read_optional_path(paths, "repos_dir", Path("repos"), base_dir),
        max_szz_commits_per_repo=max_szz_commits_per_repo,
        max_commits_per_repo=max_commits_per_repo,
        workers=workers,
        mode=mode,
        log_level=log_level,
        refresh_mining_cache=refresh_mining_cache,
        discovery_only=discovery_only,
        include_tests=include_tests,
        python_only=python_only,
        rename_match=rename_match,
    )