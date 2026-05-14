from __future__ import annotations

import argparse
import logging
import os
import threading
import tomllib
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from multiprocessing import Manager
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

try:
    from helpers.analysis_core import (
        build_mining_cache_key,
        ensure_repository,
        load_mining_cache,
        mine_package_task,
        recent_source_commit_hashes,
        run_git,
    )
    from helpers.common import (
        BUGFIX_EVENT_COLUMNS,
        FUNCTION_METRIC_COLUMNS,
        PACKAGE_SUMMARY_COLUMNS,
        SZZ_COLUMNS,
        ensure_directory,
    )
    from helpers.config import AnalysisConfig, load_analysis_config
    from helpers.discovery import build_session, discover_top_packages
    from helpers.models import PackageRecord
    from helpers.progress import configure_logging, consume_progress_events, log_message
    from helpers.reporting import (
        build_overall_szz_lag_summary,
        build_package_correlation_table,
        build_selected_package_overview,
        build_szz_matched_summary,
        build_extreme_bugfix_function_table,
        bugfix_event_frame_from_raw_json,
        load_raw_results_json,
        package_records_to_frame,
        plot_bugfix_complexity_before_after,
        plot_bugfix_complexity_changes,
        plot_bugfix_commit_timeline,
        plot_hotspot_concentration,
        plot_package_normalized_bugfix_density,
        plot_complexity_buckets,
        plot_package_correlations,
        plot_repeat_bugfix_distribution,
        szz_frame_from_raw_json,
        plot_szz_fix_lag_distribution,
        plot_szz_summary,
        write_raw_results_json,
        write_dataframe,
    )
except ImportError:
    from Code.helpers.analysis_core import (
        build_mining_cache_key,
        ensure_repository,
        load_mining_cache,
        mine_package_task,
        recent_source_commit_hashes,
        run_git,
    )
    from Code.helpers.common import (
        BUGFIX_EVENT_COLUMNS,
        FUNCTION_METRIC_COLUMNS,
        PACKAGE_SUMMARY_COLUMNS,
        SZZ_COLUMNS,
        ensure_directory,
    )
    from Code.helpers.config import AnalysisConfig, load_analysis_config
    from Code.helpers.discovery import build_session, discover_top_packages
    from Code.helpers.models import PackageRecord
    from Code.helpers.progress import configure_logging, consume_progress_events, log_message
    from Code.helpers.reporting import (
        build_overall_szz_lag_summary,
        build_package_correlation_table,
        build_selected_package_overview,
        build_szz_matched_summary,
        build_extreme_bugfix_function_table,
        bugfix_event_frame_from_raw_json,
        load_raw_results_json,
        package_records_to_frame,
        plot_bugfix_complexity_before_after,
        plot_bugfix_complexity_changes,
        plot_bugfix_commit_timeline,
        plot_hotspot_concentration,
        plot_package_normalized_bugfix_density,
        plot_complexity_buckets,
        plot_package_correlations,
        plot_repeat_bugfix_distribution,
        szz_frame_from_raw_json,
        plot_szz_fix_lag_distribution,
        plot_szz_summary,
        write_raw_results_json,
        write_dataframe,
    )


def result_paths(output_dir: Path) -> dict[str, Path]:
    """Return the canonical output file locations for one run."""

    return {
        "top_packages": output_dir / "top_packages.csv",
        "function_metrics": output_dir / "function_metrics.csv",
        "package_summary": output_dir / "package_summary.csv",
        "bugfix_event_metrics": output_dir / "bugfix_event_metrics.csv",
        "szz_function_attributions": output_dir / "szz_function_attributions.csv",
        "selected_package_overview": output_dir / "selected_package_overview.csv",
        "package_correlation_table": output_dir / "package_correlation_table.csv",
        "complexity_bucket_summary": output_dir / "complexity_bucket_summary.csv",
        "hotspot_concentration_summary": output_dir / "hotspot_concentration_summary.csv",
        "repeat_bugfix_distribution_summary": output_dir / "repeat_bugfix_distribution_summary.csv",
        "extreme_bugfix_function_table": output_dir / "extreme_bugfix_function_table.csv",
        "package_normalized_bugfix_density_summary": output_dir / "package_normalized_bugfix_density_summary.csv",
        "bugfix_complexity_change_summary": output_dir / "bugfix_complexity_change_summary.csv",
        "bugfix_commit_timeline_summary": output_dir / "bugfix_commit_timeline_summary.csv",
        "szz_fix_lag_summary": output_dir / "szz_fix_lag_summary.csv",
        "overall_szz_lag_summary": output_dir / "overall_szz_lag_summary.csv",
        "szz_summary": output_dir / "szz_summary.csv",
        "matched_szz_summary": output_dir / "matched_szz_summary.csv",
        "analysis_run_details": output_dir / "analysis_run_details.txt",
        "raw_results": output_dir / "raw_function_histories.json",
        "complexity_bucket_plot": output_dir / "plots" / "complexity_bucket_bugfix_share.png",
        "hotspot_concentration_plot": output_dir / "plots" / "hotspot_concentration.png",
        "repeat_bugfix_distribution_plot": output_dir / "plots" / "repeat_bugfix_distribution.png",
        "package_normalized_bugfix_density_plot": output_dir / "plots" / "package_normalized_bugfix_density.png",
        "bugfix_before_after_plot": output_dir / "plots" / "bugfix_complexity_before_after.png",
        "bugfix_change_plot": output_dir / "plots" / "bugfix_complexity_changes.png",
        "bugfix_timeline_plot": output_dir / "plots" / "bugfix_commit_timeline.png",
        "package_correlation_plot": output_dir / "plots" / "package_correlations.png",
        "szz_fix_lag_plot": output_dir / "plots" / "szz_fix_lag_distribution.png",
        "szz_plot": output_dir / "plots" / "szz_complexity_changes.png",
    }


def format_optional_limit(value: int | None, *, zero_label: str | None = None) -> str:
    """Format an optional integer limit for human-readable output."""

    if value is None:
        return "unbounded"
    if zero_label is not None and value == 0:
        return zero_label
    return str(value)


def repo_head_snapshot(repo_path: Path, package: PackageRecord) -> dict[str, str]:
    """Capture the current HEAD commit identity for a prepared repository."""

    lines = run_git(
        repo_path,
        "show",
        "--no-patch",
        "--format=%H%n%cI%n%s",
        "HEAD",
    ).splitlines()
    commit_hash = lines[0].strip() if len(lines) >= 1 else ""
    commit_date = lines[1].strip() if len(lines) >= 2 else ""
    subject = lines[2].strip() if len(lines) >= 3 else ""
    return {
        "package": package.name,
        "repo": package.source_repo or package.source_repo_url,
        "commit_hash": commit_hash,
        "commit_date": commit_date,
        "commit_subject": subject,
    }


def build_analysis_run_details(
    config: AnalysisConfig,
    query_started_at_local: datetime,
    since_date_utc: datetime,
    packages_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    analyzed_function_count: int,
    repo_snapshots: list[dict[str, str]],
) -> str:
    """Build a small text summary describing the run context and inputs."""

    query_started_at_utc = query_started_at_local.astimezone(timezone.utc)
    timezone_name = query_started_at_local.tzname() or "unknown"
    functions_by_package: dict[str, Any] = {}
    if not package_summary.empty and {"package", "functions_analyzed"}.issubset(package_summary.columns):
        functions_by_package = (
            package_summary.set_index("package")["functions_analyzed"].to_dict()
        )
    lines = [
        "Analysis run details",
        "",
        f"Query timestamp (local): {query_started_at_local.isoformat()}",
        f"Query timezone: {timezone_name}",
        f"Query timestamp (UTC): {query_started_at_utc.isoformat()}",
        f"Analysis window start (UTC): {since_date_utc.isoformat()}",
        "",
        "Configuration summary",
        f"- Config file: {config.config_path}",
        f"- Requested top N packages: {config.top_n}",
        f"- Maximum ranked packages inspected: {config.candidate_pool}",
        f"- Analysis window (years): {config.years}",
        f"- Functions analyzed: {analyzed_function_count}",
        f"- Include tests: {config.include_tests}",
        f"- Python only: {config.python_only}",
        f"- Max recent source commits per repo: {format_optional_limit(config.max_commits_per_repo)}",
        f"- Max SZZ blamed commits per repo: {format_optional_limit(config.max_szz_commits_per_repo, zero_label='disabled')}",
        f"- Bug-fix timeline granularity: {config.bugfix_timeline_granularity}",
        (
            "- Rename matching thresholds: "
            + f"min_overlap_ratio={config.rename_match.min_overlap_ratio}, "
            + f"max_boundary_distance_with_overlap={config.rename_match.max_boundary_distance_with_overlap}, "
            + f"min_score={config.rename_match.min_score}, "
            + f"max_boundary_distance_for_score={config.rename_match.max_boundary_distance_for_score}"
        ),
        "",
        f"Selected packages ({len(packages_df)}):",
    ]
    if packages_df.empty:
        lines.append("- none")
    else:
        for record in packages_df.itertuples(index=False):
            functions_analyzed = functions_by_package.get(record.name)
            functions_part = (
                f" | functions_analyzed={int(functions_analyzed)}"
                if functions_analyzed is not None and not pd.isna(functions_analyzed)
                else ""
            )
            lines.append(
                f"- #{record.rank} {record.name} {record.version}{functions_part}"
            )

    lines.extend(["", "Prepared repository HEAD commits:"])
    if repo_snapshots:
        for snapshot in repo_snapshots:
            subject = snapshot["commit_subject"] or "(no subject)"
            commit_hash = snapshot["commit_hash"] or "unknown"
            commit_date = snapshot["commit_date"] or "unknown date"
            lines.append(
                f"- {snapshot['package']}: {commit_hash} | {commit_date} | {subject}"
            )
    else:
        lines.append("- not collected in this run mode")

    return "\n".join(lines) + "\n"


def write_analysis_run_details(
    config: AnalysisConfig,
    output_dir: Path,
    query_started_at_local: datetime,
    since_date_utc: datetime,
    packages_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    analyzed_function_count: int,
    repo_snapshots: list[dict[str, str]],
) -> None:
    """Write the plain-text run details file alongside the other outputs."""

    paths = result_paths(output_dir)
    paths["analysis_run_details"].write_text(
        build_analysis_run_details(
            config=config,
            query_started_at_local=query_started_at_local,
            since_date_utc=since_date_utc,
            packages_df=packages_df,
            package_summary=package_summary,
            analyzed_function_count=analyzed_function_count,
            repo_snapshots=repo_snapshots,
        ),
        encoding="utf-8",
    )


def load_existing_frame(target: Path, columns: list[str]) -> pd.DataFrame:
    """Load a CSV result frame if present, else return an empty frame with stable columns."""

    if target.exists():
        frame = pd.read_csv(target)
        for column in columns:
            if column not in frame.columns:
                frame[column] = pd.NA
        return frame.reindex(columns=columns)
    return pd.DataFrame(columns=columns)


def load_existing_results(output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load previously computed result tables from an output directory."""

    paths = result_paths(output_dir)
    if not paths["top_packages"].exists():
        raise FileNotFoundError(
            f"Plot mode requires an existing result set; missing {paths['top_packages']}"
        )
    packages_df = pd.read_csv(paths["top_packages"])
    function_df = load_existing_frame(paths["function_metrics"], FUNCTION_METRIC_COLUMNS)
    package_summary = load_existing_frame(paths["package_summary"], PACKAGE_SUMMARY_COLUMNS)
    raw_payload = load_raw_results_json(paths["raw_results"]) if paths["raw_results"].exists() else None
    if raw_payload is not None:
        bugfix_event_df = bugfix_event_frame_from_raw_json(raw_payload)
        szz_df = szz_frame_from_raw_json(raw_payload)
    else:
        bugfix_event_df = load_existing_frame(paths["bugfix_event_metrics"], BUGFIX_EVENT_COLUMNS)
        szz_df = load_existing_frame(paths["szz_function_attributions"], SZZ_COLUMNS)
    return packages_df, function_df, package_summary, bugfix_event_df, szz_df


def render_plots_and_summaries(
    packages_df: pd.DataFrame,
    function_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    bugfix_event_df: pd.DataFrame,
    szz_df: pd.DataFrame,
    output_dir: Path,
    analysis_years: float,
    timeline_granularity: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Render plots and derived summaries from existing result tables."""

    paths = result_paths(output_dir)
    log_message("Generating plots and summaries.")
    selected_package_overview = build_selected_package_overview(
        packages_df,
        package_summary,
        paths["analysis_run_details"],
    )
    package_correlation_table = build_package_correlation_table(package_summary)
    if not function_df.empty:
        bucket_summary = plot_complexity_buckets(function_df, paths["complexity_bucket_plot"])
        hotspot_concentration_summary = plot_hotspot_concentration(
            function_df,
            paths["hotspot_concentration_plot"],
        )
        repeat_bugfix_distribution_summary = plot_repeat_bugfix_distribution(
            function_df,
            paths["repeat_bugfix_distribution_plot"],
        )
        extreme_bugfix_function_table = build_extreme_bugfix_function_table(
            function_df,
            bugfix_event_df,
        )
    else:
        bucket_summary = pd.DataFrame(
            columns=[
                "complexity_bucket",
                "functions",
                "bugfixed_functions",
                "mean_bugfix_commits",
                "bugfix_share",
            ]
        )
        hotspot_concentration_summary = pd.DataFrame(
            columns=["function_rank", "function_share", "cumulative_bugfix_share"]
        )
        repeat_bugfix_distribution_summary = pd.DataFrame(
            columns=["bugfix_commits", "functions_with_exact_count", "share"]
        )
        extreme_bugfix_function_table = pd.DataFrame(
            columns=[
                "package",
                "package_rank",
                "file_path",
                "function",
                "kind",
                "complexity",
                "n_bugfix_commits",
                "bugfix_commit",
                "bugfix_commit_date",
                "bugfix_message",
            ]
        )
    if not bugfix_event_df.empty:
        plot_bugfix_complexity_before_after(bugfix_event_df, paths["bugfix_before_after_plot"])
        bugfix_change_summary = plot_bugfix_complexity_changes(
            bugfix_event_df,
            paths["bugfix_change_plot"],
        )
        bugfix_timeline_summary = plot_bugfix_commit_timeline(
            bugfix_event_df,
            paths["bugfix_timeline_plot"],
            analysis_years=analysis_years,
            granularity=timeline_granularity,
        )
    else:
        bugfix_change_summary = pd.DataFrame(
            columns=["category", "count", "share"]
        )
        bugfix_timeline_summary = pd.DataFrame(
            columns=["period_start", "period_label", "count"]
        )
    if not package_summary.empty:
        plot_package_correlations(package_summary, paths["package_correlation_plot"])
        package_normalized_bugfix_density_summary = plot_package_normalized_bugfix_density(
            package_summary,
            paths["package_normalized_bugfix_density_plot"],
        )
    else:
        package_normalized_bugfix_density_summary = pd.DataFrame(
            columns=["package", "metric", "value"]
        )
    if not szz_df.empty:
        szz_fix_lag_summary = plot_szz_fix_lag_distribution(szz_df, paths["szz_fix_lag_plot"])
        overall_szz_lag_summary = build_overall_szz_lag_summary(szz_df)
        matched_szz_summary = build_szz_matched_summary(szz_df)
    else:
        szz_fix_lag_summary = pd.DataFrame(
            columns=["package", "pair_count", "median_lag_days", "p25_lag_days", "p75_lag_days"]
        )
        overall_szz_lag_summary = pd.DataFrame(
            columns=["pair_count", "median_lag_days", "p25_lag_days", "p75_lag_days"]
        )
        matched_szz_summary = pd.DataFrame(
            columns=["category", "count", "share", "matched_total", "overall_total"]
        )
    szz_summary = plot_szz_summary(szz_df, paths["szz_plot"])
    write_dataframe(selected_package_overview, paths["selected_package_overview"])
    write_dataframe(package_correlation_table, paths["package_correlation_table"])
    write_dataframe(bucket_summary, paths["complexity_bucket_summary"])
    write_dataframe(hotspot_concentration_summary, paths["hotspot_concentration_summary"])
    write_dataframe(repeat_bugfix_distribution_summary, paths["repeat_bugfix_distribution_summary"])
    write_dataframe(extreme_bugfix_function_table, paths["extreme_bugfix_function_table"])
    write_dataframe(package_normalized_bugfix_density_summary, paths["package_normalized_bugfix_density_summary"])
    write_dataframe(bugfix_change_summary, paths["bugfix_complexity_change_summary"])
    write_dataframe(bugfix_timeline_summary, paths["bugfix_commit_timeline_summary"])
    write_dataframe(szz_fix_lag_summary, paths["szz_fix_lag_summary"])
    write_dataframe(overall_szz_lag_summary, paths["overall_szz_lag_summary"])
    write_dataframe(szz_summary, paths["szz_summary"])
    write_dataframe(matched_szz_summary, paths["matched_szz_summary"])
    write_raw_results_json(
        packages_df=packages_df,
        function_df=function_df,
        package_summary=package_summary,
        bugfix_event_df=bugfix_event_df,
        szz_df=szz_df,
        target=paths["raw_results"],
    )
    stale_summary = output_dir / "analysis_summary.md"
    if stale_summary.exists():
        stale_summary.unlink()
    stale_top_packages_plot = output_dir / "plots" / "top_packages.png"
    if stale_top_packages_plot.exists():
        stale_top_packages_plot.unlink()
    return bucket_summary, bugfix_change_summary, bugfix_timeline_summary, szz_summary


def parse_args() -> AnalysisConfig:
    """Parse the minimal CLI and load the TOML configuration file."""

    code_dir = Path(__file__).resolve().parent
    default_cfg = code_dir / "analysis.toml"
    parser = argparse.ArgumentParser(
        description="Analyze reverse dependencies and bug-fix patterns in Python packages.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "All runtime settings live in a TOML config file grouped by concern. "
            f"By default, the checked-in config at {default_cfg} is used."
        ),
    )
    parser.add_argument(
        "-c",
        "--cfg",
        dest="config_path",
        type=Path,
        default=default_cfg,
        help="Path to the TOML configuration file.",
    )
    parsed = parser.parse_args()
    try:
        return load_analysis_config(parsed.config_path)
    except (AssertionError, FileNotFoundError, tomllib.TOMLDecodeError, ValueError) as exc:
        parser.error(str(exc))


def main() -> None:
    """Run the end-to-end package ecosystem analysis.

    Notes
    -----
    This entrypoint orchestrates package discovery, repository preparation,
    bounded mining, SZZ attribution, plotting, and CSV export.
    """

    args = parse_args()
    skip_szz = args.max_szz_commits_per_repo == 0
    query_started_at_local = datetime.now().astimezone()
    since_date = query_started_at_local.astimezone(timezone.utc) - timedelta(days=int(args.years * 365.25))
    configure_logging(args.log_level)
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    repos_dir = args.repos_dir.resolve()
    ensure_directory(output_dir)
    ensure_directory(cache_dir)
    ensure_directory(repos_dir)

    if args.mode == "plot":
        phase_names = ["load results", "plots+summaries"]
        phase_bar = tqdm(
            total=len(phase_names),
            desc=f"phase [{phase_names[0]}]",
            position=0,
            dynamic_ncols=True,
            unit="phase",
        )
        log_message(f"Loading existing results from {output_dir}.")
        packages_df, function_df, package_summary, bugfix_event_df, szz_df = load_existing_results(output_dir)
        phase_bar.update(1)
        phase_bar.set_description_str("phase [plots+summaries]")
        render_plots_and_summaries(
            packages_df,
            function_df,
            package_summary,
            bugfix_event_df,
            szz_df,
            output_dir,
            analysis_years=args.years,
            timeline_granularity=args.bugfix_timeline_granularity,
        )
        write_analysis_run_details(
            config=args,
            output_dir=output_dir,
            query_started_at_local=query_started_at_local,
            since_date_utc=since_date,
            packages_df=packages_df,
            package_summary=package_summary,
            analyzed_function_count=len(function_df),
            repo_snapshots=[],
        )
        phase_bar.update(1)
        phase_bar.set_description_str("phase [done]")
        phase_bar.close()
        log_message(f"Finished. CSVs and plots are in {output_dir}.")
        return

    phase_names = ["discovery"] if args.discovery_only and args.mode == "compute" else (
        ["discovery", "plots+summaries"]
        if args.discovery_only
        else (
            ["discovery", "repo prep", "mining+szz", "csv export"]
            if args.mode == "compute"
            else ["discovery", "repo prep", "mining+szz", "csv export", "plots+summaries"]
        )
    )
    phase_bar = tqdm(
        total=len(phase_names),
        desc=f"phase [{phase_names[0]}]",
        position=0,
        dynamic_ncols=True,
        unit="phase",
    )

    session = build_session()
    log_message(
        f"Starting discovery for top {args.top_n} packages from a candidate pool of {args.candidate_pool}."
    )
    discovery_bar = tqdm(
        total=args.candidate_pool,
        desc="candidates",
        position=1,
        dynamic_ncols=True,
        unit="pkg",
        leave=False,
    )
    packages = discover_top_packages(
        session=session,
        top_n=args.top_n,
        candidate_pool=args.candidate_pool,
        cache_dir=cache_dir,
        progress_bar=discovery_bar,
    )
    discovery_bar.close()
    packages_df = package_records_to_frame(packages)
    write_dataframe(packages_df, output_dir / "top_packages.csv")
    log_message(
        "Selected packages: " + ", ".join(packages_df["name"].tolist())
        if not packages_df.empty
        else "No packages were selected."
    )
    phase_bar.update(1)

    function_df = pd.DataFrame(columns=FUNCTION_METRIC_COLUMNS)
    package_summary = pd.DataFrame(columns=PACKAGE_SUMMARY_COLUMNS)
    bugfix_event_df = pd.DataFrame(columns=BUGFIX_EVENT_COLUMNS)
    szz_df = pd.DataFrame(columns=SZZ_COLUMNS)

    if args.discovery_only:
        if args.mode == "both":
            phase_bar.set_description_str("phase [plots+summaries]")
            render_plots_and_summaries(
                packages_df,
                function_df,
                package_summary,
                bugfix_event_df,
                szz_df,
                output_dir,
                analysis_years=args.years,
                timeline_granularity=args.bugfix_timeline_granularity,
            )
            phase_bar.update(1)
        write_analysis_run_details(
            config=args,
            output_dir=output_dir,
            query_started_at_local=query_started_at_local,
            since_date_utc=since_date,
            packages_df=packages_df,
            package_summary=package_summary,
            analyzed_function_count=len(function_df),
            repo_snapshots=[],
        )
        phase_bar.set_description_str("phase [done]")
        phase_bar.close()
        log_message(f"Finished. CSVs and plots are in {output_dir}.")
        return

    function_frames: list[pd.DataFrame] = []
    package_frames: list[pd.DataFrame] = []
    bugfix_event_frames: list[pd.DataFrame] = []
    szz_frames: list[pd.DataFrame] = []
    package_tasks: list[tuple[PackageRecord, Path, list[str], str, dict[str, object]]] = []
    repo_snapshots: list[dict[str, str]] = []

    phase_bar.set_description_str("phase [repo prep]")
    prep_bar = tqdm(
        total=max(len(packages), 1),
        desc="repo prep",
        position=1,
        dynamic_ncols=True,
        unit="repo",
        leave=False,
    )

    for package in packages:
        if not package.source_repo_url:
            log_message(f"Skipping {package.name}: no source repository resolved.", level=logging.WARNING)
            prep_bar.update(1)
            continue
        repo_name = package.source_repo_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        repo_target = repos_dir / repo_name
        action = "Updating" if repo_target.exists() else "Cloning"
        log_message(f"Repo prep | {action} {package.name} from {package.source_repo or package.source_repo_url}")
        repo_path = ensure_repository(package.source_repo_url, repos_dir=repos_dir)
        head_snapshot = repo_head_snapshot(repo_path, package)
        repo_snapshots.append(head_snapshot)
        repo_head = head_snapshot["commit_hash"]
        commit_hashes = recent_source_commit_hashes(
            repo_path=repo_path,
            since_date=since_date,
            max_commits=args.max_commits_per_repo,
            python_only=args.python_only,
        )
        cache_key, cache_metadata = build_mining_cache_key(
            package=package,
            repo_path=repo_path,
            repo_head=repo_head,
            include_tests=args.include_tests,
            python_only=args.python_only,
            skip_szz=skip_szz,
            max_szz_commits_per_repo=args.max_szz_commits_per_repo,
            max_commits_per_repo=args.max_commits_per_repo,
            rename_match=args.rename_match,
            commit_hashes=commit_hashes,
        )
        cached_result = None
        if not args.refresh_mining_cache:
            cached_result = load_mining_cache(
                package=package,
                cache_dir=cache_dir,
                cache_key=cache_key,
            )
        if cached_result is not None:
            log_message(
                f"Cache hit | {package.name}: reusing {len(commit_hashes)} commit-window result."
            )
            function_df, package_summary, bugfix_event_df, szz_df = cached_result
            function_frames.append(function_df)
            package_frames.append(package_summary)
            if not bugfix_event_df.empty:
                bugfix_event_frames.append(bugfix_event_df)
            if not szz_df.empty:
                szz_frames.append(szz_df)
        else:
            package_tasks.append((package, repo_path, commit_hashes, cache_key, cache_metadata))
        prep_bar.update(1)
    prep_bar.close()
    phase_bar.update(1)

    max_workers = args.workers
    if max_workers is None:
        cpu_count = os.cpu_count() or 1
        max_workers = min(len(package_tasks), cpu_count) if package_tasks else 1
    else:
        max_workers = max(1, min(max_workers, len(package_tasks) or 1))
    log_message(f"Mining with {max_workers} worker process(es).")

    phase_bar.set_description_str("phase [mining+szz]")
    repo_bar_start = 2
    repo_bars = {
        package.name: tqdm(
            total=1,
            desc=f"{package.name} [queued]",
            position=repo_bar_start + index,
            dynamic_ncols=True,
            unit="step",
        )
        for index, (package, _, _, _, _) in enumerate(package_tasks)
    }
    if package_tasks:
        progress_manager = Manager()
        progress_queue = progress_manager.Queue()
        progress_thread = threading.Thread(
            target=consume_progress_events,
            args=(progress_queue, repo_bars),
            daemon=True,
        )
        progress_thread.start()

        try:
            if max_workers == 1:
                for package, repo_path, commit_hashes, cache_key, cache_metadata in package_tasks:
                    function_df, package_summary, bugfix_event_df, szz_df = mine_package_task(
                        package=package,
                        repo_path=repo_path,
                        commit_hashes=commit_hashes,
                        include_tests=args.include_tests,
                        python_only=args.python_only,
                        skip_szz=skip_szz,
                        max_szz_commits_per_repo=args.max_szz_commits_per_repo,
                        max_commits_per_repo=args.max_commits_per_repo,
                        rename_match=args.rename_match,
                        progress_queue=progress_queue,
                        cache_dir=cache_dir,
                        cache_key=cache_key,
                        cache_metadata=cache_metadata,
                    )
                    function_frames.append(function_df)
                    package_frames.append(package_summary)
                    if not bugfix_event_df.empty:
                        bugfix_event_frames.append(bugfix_event_df)
                    if not szz_df.empty:
                        szz_frames.append(szz_df)
            else:
                with ProcessPoolExecutor(max_workers=max_workers) as executor:
                    future_to_package = {
                        executor.submit(
                            mine_package_task,
                            package,
                            repo_path,
                            commit_hashes,
                            args.include_tests,
                            args.python_only,
                            skip_szz,
                            args.max_szz_commits_per_repo,
                            args.max_commits_per_repo,
                            args.rename_match,
                            progress_queue,
                            cache_dir,
                            cache_key,
                            cache_metadata,
                        ): package.name
                        for package, repo_path, commit_hashes, cache_key, cache_metadata in package_tasks
                    }
                    for future in as_completed(future_to_package):
                        package_name = future_to_package[future]
                        try:
                            function_df, package_summary, bugfix_event_df, szz_df = future.result()
                        except Exception as exc:
                            raise RuntimeError(f"Failed while mining package {package_name}") from exc
                        function_frames.append(function_df)
                        package_frames.append(package_summary)
                        if not bugfix_event_df.empty:
                            bugfix_event_frames.append(bugfix_event_df)
                        if not szz_df.empty:
                            szz_frames.append(szz_df)
        finally:
            progress_queue.put({"kind": "stop"})
            progress_thread.join()
            progress_manager.shutdown()
            for bar in repo_bars.values():
                bar.close()
    else:
        for bar in repo_bars.values():
            bar.close()
        log_message("All package mining results were loaded from cache.")
    phase_bar.update(1)

    function_df = pd.concat(function_frames, ignore_index=True) if function_frames else pd.DataFrame()
    package_summary = pd.concat(package_frames, ignore_index=True) if package_frames else pd.DataFrame()
    bugfix_event_df = (
        pd.concat(bugfix_event_frames, ignore_index=True) if bugfix_event_frames else pd.DataFrame(columns=BUGFIX_EVENT_COLUMNS)
    )
    szz_df = pd.concat(szz_frames, ignore_index=True) if szz_frames else pd.DataFrame()

    phase_bar.set_description_str("phase [csv export]")
    log_message("Writing CSV outputs.")
    paths = result_paths(output_dir)
    write_dataframe(function_df, paths["function_metrics"])
    write_dataframe(package_summary, paths["package_summary"])
    write_dataframe(bugfix_event_df, paths["bugfix_event_metrics"])
    write_dataframe(szz_df, paths["szz_function_attributions"])
    write_raw_results_json(
        packages_df=packages_df,
        function_df=function_df,
        package_summary=package_summary,
        bugfix_event_df=bugfix_event_df,
        szz_df=szz_df,
        target=paths["raw_results"],
    )
    write_analysis_run_details(
        config=args,
        output_dir=output_dir,
        query_started_at_local=query_started_at_local,
        since_date_utc=since_date,
        packages_df=packages_df,
        package_summary=package_summary,
        analyzed_function_count=len(function_df),
        repo_snapshots=repo_snapshots,
    )
    phase_bar.update(1)

    if args.mode == "both":
        phase_bar.set_description_str("phase [plots+summaries]")
        render_plots_and_summaries(
            packages_df,
            function_df,
            package_summary,
            bugfix_event_df,
            szz_df,
            output_dir,
            analysis_years=args.years,
            timeline_granularity=args.bugfix_timeline_granularity,
        )
        phase_bar.update(1)

    phase_bar.set_description_str("phase [done]")
    phase_bar.close()
    log_message(f"Finished. CSVs and plots are in {output_dir}.")


if __name__ == "__main__":
    main()