from __future__ import annotations

import argparse
import logging
import os
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timedelta
from multiprocessing import Manager
from pathlib import Path

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
    from helpers.common import LOG_LEVELS, ensure_directory, utc_now
    from helpers.discovery import build_session, discover_top_packages
    from helpers.models import PackageRecord
    from helpers.progress import configure_logging, consume_progress_events, log_message
    from helpers.reporting import (
        package_records_to_frame,
        plot_complexity_buckets,
        plot_complexity_scatter,
        plot_package_correlations,
        plot_szz_summary,
        plot_top_packages,
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
    from Code.helpers.common import LOG_LEVELS, ensure_directory, utc_now
    from Code.helpers.discovery import build_session, discover_top_packages
    from Code.helpers.models import PackageRecord
    from Code.helpers.progress import configure_logging, consume_progress_events, log_message
    from Code.helpers.reporting import (
        package_records_to_frame,
        plot_complexity_buckets,
        plot_complexity_scatter,
        plot_package_correlations,
        plot_szz_summary,
        plot_top_packages,
        write_dataframe,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the analysis pipeline."""

    code_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Analyze reverse dependencies and bug-fix patterns in Python packages."
    )
    parser.add_argument("--top-n", type=int, default=10, help="Number of packages to analyze.")
    parser.add_argument(
        "--candidate-pool",
        type=int,
        default=250,
        help="Downloaded package candidates reranked by direct dependents.",
    )
    parser.add_argument(
        "--years",
        type=float,
        default=2.0,
        help="Analysis window in years for commit mining.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=code_dir / "output" / "latest",
        help="Directory for plots, tables, and summaries.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=code_dir / "cache",
        help="Directory for cached HTTP responses.",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=code_dir / "repos",
        help="Directory where source repositories are cloned.",
    )
    parser.add_argument(
        "--max-szz-commits-per-repo",
        type=int,
        default=None,
        help="Optional cap for SZZ bug-fix commits per repository.",
    )
    parser.add_argument(
        "--max-commits-per-repo",
        type=int,
        default=None,
        help="Optional cap for the most recent Python commits mined per repository.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Optional number of worker processes for per-package mining.",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(LOG_LEVELS),
        default="INFO",
        help="Terminal log verbosity for phase updates and progress messages.",
    )
    parser.add_argument(
        "--refresh-mining-cache",
        action="store_true",
        help="Ignore cached per-package mining results and recompute them.",
    )
    parser.add_argument(
        "--skip-szz",
        action="store_true",
        help="Skip the simplified SZZ pass if you only want the correlation analysis.",
    )
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="Stop after package discovery and metadata export.",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include test and example files in the function-level analysis.",
    )
    parser.add_argument(
        "--python-only",
        action="store_true",
        help="Restrict mining and complexity analysis to Python files only.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the end-to-end package ecosystem analysis."""

    args = parse_args()
    configure_logging(args.log_level)
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    repos_dir = args.repos_dir.resolve()
    ensure_directory(output_dir)
    ensure_directory(cache_dir)
    ensure_directory(repos_dir)

    phase_names = ["discovery", "plots"] if args.discovery_only else [
        "discovery",
        "repo prep",
        "mining+szz",
        "plots",
        "csv export",
    ]
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

    if args.discovery_only:
        phase_bar.set_description_str("phase [plots]")
        log_message("Plotting discovery output.")
        plot_top_packages(packages_df, output_dir / "plots" / "top_packages.png")
        phase_bar.update(1)
        phase_bar.set_description_str("phase [done]")
        phase_bar.close()
        log_message(f"Finished. CSVs and plots are in {output_dir}.")
        return

    since_date = utc_now() - timedelta(days=int(args.years * 365.25))
    function_frames: list[pd.DataFrame] = []
    package_frames: list[pd.DataFrame] = []
    szz_frames: list[pd.DataFrame] = []
    package_tasks: list[tuple[PackageRecord, Path, list[str], str, dict[str, object]]] = []

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
        repo_head = run_git(repo_path, "rev-parse", "HEAD").strip()
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
            skip_szz=args.skip_szz,
            max_szz_commits_per_repo=args.max_szz_commits_per_repo,
            max_commits_per_repo=args.max_commits_per_repo,
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
            function_df, package_summary, szz_df = cached_result
            function_frames.append(function_df)
            package_frames.append(package_summary)
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
                    function_df, package_summary, szz_df = mine_package_task(
                        package=package,
                        repo_path=repo_path,
                        commit_hashes=commit_hashes,
                        include_tests=args.include_tests,
                        python_only=args.python_only,
                        skip_szz=args.skip_szz,
                        max_szz_commits_per_repo=args.max_szz_commits_per_repo,
                        max_commits_per_repo=args.max_commits_per_repo,
                        progress_queue=progress_queue,
                        cache_dir=cache_dir,
                        cache_key=cache_key,
                        cache_metadata=cache_metadata,
                    )
                    function_frames.append(function_df)
                    package_frames.append(package_summary)
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
                            args.skip_szz,
                            args.max_szz_commits_per_repo,
                            args.max_commits_per_repo,
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
                            function_df, package_summary, szz_df = future.result()
                        except Exception as exc:
                            raise RuntimeError(f"Failed while mining package {package_name}") from exc
                        function_frames.append(function_df)
                        package_frames.append(package_summary)
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
    szz_df = pd.concat(szz_frames, ignore_index=True) if szz_frames else pd.DataFrame()

    phase_bar.set_description_str("phase [plots]")
    log_message("Generating plots.")
    if not packages_df.empty:
        plot_top_packages(packages_df, output_dir / "plots" / "top_packages.png")
    if not function_df.empty:
        plot_complexity_scatter(function_df, output_dir / "plots" / "complexity_vs_bugfixes.png")
        bucket_summary = plot_complexity_buckets(
            function_df, output_dir / "plots" / "complexity_bucket_bugfix_share.png"
        )
    else:
        bucket_summary = pd.DataFrame(
            columns=["complexity_bucket", "functions", "bugfixed_functions", "mean_bugfix_commits", "bugfix_share"]
        )
    if not package_summary.empty:
        plot_package_correlations(
            package_summary, output_dir / "plots" / "package_correlations.png"
        )
    szz_summary = plot_szz_summary(szz_df, output_dir / "plots" / "szz_complexity_changes.png")
    phase_bar.update(1)

    phase_bar.set_description_str("phase [csv export]")
    log_message("Writing CSV outputs.")
    write_dataframe(function_df, output_dir / "function_metrics.csv")
    write_dataframe(package_summary, output_dir / "package_summary.csv")
    write_dataframe(szz_df, output_dir / "szz_function_attributions.csv")
    write_dataframe(bucket_summary, output_dir / "complexity_bucket_summary.csv")
    write_dataframe(szz_summary, output_dir / "szz_summary.csv")
    phase_bar.update(1)
    phase_bar.set_description_str("phase [done]")
    phase_bar.close()
    log_message(f"Finished. CSVs and plots are in {output_dir}.")


if __name__ == "__main__":
    main()