from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, Sequence

import pandas as pd
from scipy.stats import spearmanr

from .common import BUGFIX_EVENT_COLUMNS, SZZ_COLUMNS, ensure_directory
from .models import PackageRecord


SZZ_CATEGORY_ORDER = [
    "Increase",
    "No change",
    "Decrease",
    "New function",
    "Deleted or renamed",
    "Function pair not recoverable",
    "No parent commit",
]
BUGFIX_CATEGORY_ORDER = [
    "Increase",
    "No change",
    "Decrease",
    "New function",
    "Deleted or renamed",
    "Function pair not recoverable",
]
CSV_MESSAGE_KEEP_PATTERN = re.compile(
    r"\b(fix(?:e[sd])?|bug(?:fix(?:es)?)?|regression|hotfix|patch(?:ed)?|close[sd]?|closing)\b",
    re.IGNORECASE,
)
CSV_MESSAGE_PRIMARY_PATTERN = re.compile(
    r"\b(fix(?:e[sd])?|bug(?:fix(?:es)?)?|regression|hotfix|patch(?:ed)?)\b",
    re.IGNORECASE,
)
CSV_MESSAGE_CLOSE_PATTERN = re.compile(r"\b(close[sd]?|closing)\b", re.IGNORECASE)
RUN_DETAILS_HEAD_PATTERN = re.compile(
    r"^- (?P<package>[^:]+): (?P<commit_hash>[0-9a-f]{7,40}) \| ",
    re.IGNORECASE,
)


def compact_commit_message_for_csv(value: Any) -> Any:
    """Collapse multiline commit messages into one CSV-friendly line.

    Keep only lines that explicitly look fix-related. If other non-empty lines
    were removed, append ``[...]`` once so the CSV still signals that the JSON
    contains more context.
    """

    if not isinstance(value, str):
        return value

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in normalized:
        return normalized.strip()

    lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.split("\n")]
    indexed_lines = [(index, line) for index, line in enumerate(lines) if line]
    if not indexed_lines:
        return ""

    primary_kept = [item for item in indexed_lines if CSV_MESSAGE_PRIMARY_PATTERN.search(item[1])]
    if primary_kept:
        kept = primary_kept
    else:
        descriptive_lines = [item for item in indexed_lines if not CSV_MESSAGE_CLOSE_PATTERN.search(item[1])]
        if descriptive_lines:
            kept = [descriptive_lines[0]]
        else:
            kept = [item for item in indexed_lines if CSV_MESSAGE_KEEP_PATTERN.search(item[1])]
    if not kept:
        return "[ ... ]".replace(" ", "") if indexed_lines else ""

    kept_indices = {index for index, _ in kept}
    parts: list[str] = []
    first_kept_index = kept[0][0]
    if any(index < first_kept_index for index, _ in indexed_lines if index not in kept_indices):
        parts.append("[...]")

    previous_index: int | None = None
    for index, line in kept:
        if previous_index is not None and any(
            skipped_index not in kept_indices
            for skipped_index, _ in indexed_lines
            if previous_index < skipped_index < index
        ):
            parts.append("[...]")
        parts.append(line)
        previous_index = index

    last_kept_index = kept[-1][0]
    if any(index > last_kept_index for index, _ in indexed_lines if index not in kept_indices):
        parts.append("[...]")

    return "; ".join(parts)


def dataframe_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare a dataframe for CSV export without mutating the source frame."""

    csv_df = df.copy()
    for column in csv_df.columns:
        if column.endswith("_message"):
            csv_df[column] = csv_df[column].map(compact_commit_message_for_csv)
    return csv_df


def load_raw_results_json(target: Path) -> dict[str, Any]:
    """Load the grouped raw JSON export."""

    return json.loads(target.read_text(encoding="utf-8"))


def bugfix_event_frame_from_raw_json(payload: dict[str, Any]) -> pd.DataFrame:
    """Rebuild the bug-fix event table from the grouped raw JSON export."""

    rows: list[dict[str, Any]] = []
    for function_record in payload.get("functions", []):
        base_row = {
            "package": function_record.get("package"),
            "package_rank": function_record.get("package_rank"),
            "function": function_record.get("function"),
            "kind": function_record.get("kind"),
        }
        for event in function_record.get("bugfix_events", []):
            rows.append(
                {
                    **base_row,
                    "before_file_path": event.get("before_file_path"),
                    "after_file_path": event.get("after_file_path"),
                    "bugfix_commit": event.get("bugfix_commit"),
                    "bugfix_message": event.get("bugfix_message"),
                    "bugfix_commit_date": event.get("bugfix_commit_date"),
                    "bugfix_before_complexity": event.get("before_complexity"),
                    "bugfix_after_complexity": event.get("after_complexity"),
                    "bugfix_complexity_delta": event.get("complexity_delta"),
                    "bugfix_complexity_category": event.get("complexity_category"),
                }
            )
    return pd.DataFrame(rows, columns=BUGFIX_EVENT_COLUMNS)


def szz_frame_from_raw_json(payload: dict[str, Any]) -> pd.DataFrame:
    """Rebuild the SZZ attribution table from the grouped raw JSON export."""

    rows: list[dict[str, Any]] = []
    for function_record in payload.get("functions", []):
        package = function_record.get("package")
        file_path = function_record.get("file_path")
        function = function_record.get("function")
        for event in function_record.get("bugfix_events", []):
            for introducing_commit in event.get("bug_introducing_commits", []):
                rows.append(
                    {
                        "package": package,
                        "bugfix_commit": event.get("bugfix_commit"),
                        "bugfix_message": event.get("bugfix_message"),
                        "bugfix_commit_date": event.get("bugfix_commit_date"),
                        "bug_introducing_commit": introducing_commit.get("commit"),
                        "bug_introducing_message": introducing_commit.get("message"),
                        "bug_introducing_commit_date": introducing_commit.get("commit_date"),
                        "file_path": file_path,
                        "function": function,
                        "complexity_delta": introducing_commit.get("complexity_delta"),
                        "complexity_category": introducing_commit.get("complexity_category"),
                        "complexity_increased": introducing_commit.get("complexity_increased"),
                    }
                )
    return pd.DataFrame(rows, columns=SZZ_COLUMNS)


def write_dataframe(df: pd.DataFrame, target: Path) -> None:
    """Write a dataframe to CSV."""

    ensure_directory(target.parent)
    dataframe_for_csv(df).to_csv(target, index=False)


def load_plotting_modules() -> tuple[Any, Any]:
    """Import plotting modules lazily so worker processes avoid the cost."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    return plt, sns


def choose_nice_bucket_width(max_complexity: int, target_bucket_count: int = 10) -> int:
    """Choose a clean bucket width near the target bucket count.

    The width is rounded up to a human-readable step (1, 2, 5, or 10 times a
    power of ten) so labels stay on round boundaries instead of odd ranges like
    39-57.
    """

    if max_complexity <= 0:
        return 1

    rough_width = max_complexity / max(target_bucket_count, 1)
    magnitude = 10 ** math.floor(math.log10(max(rough_width, 1)))
    for multiplier in (1, 2, 5, 10):
        candidate = int(multiplier * magnitude)
        if candidate >= rough_width:
            return max(candidate, 1)
    return max(int(10 * magnitude), 1)


def assign_complexity_buckets(function_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Assign fixed-width complexity buckets with clean integer bounds."""

    bucket_df = function_df.copy()
    overall_max_complexity = int(bucket_df["complexity"].max())
    bugfixed_complexities = bucket_df.loc[bucket_df["was_bugfixed"] > 0, "complexity"].dropna()
    focus_max_complexity = (
        int(bugfixed_complexities.max())
        if not bugfixed_complexities.empty
        else overall_max_complexity
    )
    bucket_width = choose_nice_bucket_width(max(focus_max_complexity, 1))
    max_complexity = max(bucket_width, int(math.ceil(focus_max_complexity / bucket_width) * bucket_width))
    bucket_count = max(1, int(math.ceil(max_complexity / bucket_width)))
    bucket_edges = [bucket_width * index for index in range(bucket_count + 1)]
    bucket_labels = [
        f"{1 if index == 0 else bucket_edges[index] + 1}-{bucket_edges[index + 1]}"
        for index in range(bucket_count)
    ]
    # Fold rarer high-complexity outliers into the final bucket so the plot
    # stays focused on the range where bug-fixed functions actually appear.
    if overall_max_complexity > bucket_edges[-1]:
        bucket_labels[-1] = f"{bucket_edges[-2] + 1}-{bucket_edges[-1]}+"
    clipped_complexity = bucket_df["complexity"].clip(upper=bucket_edges[-1])
    bucket_df["complexity_bucket"] = pd.cut(
        clipped_complexity,
        bins=bucket_edges,
        include_lowest=True,
        labels=bucket_labels,
    )
    return bucket_df, bucket_labels


def plot_hotspot_concentration(function_df: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Plot how much bug-fix activity is concentrated in the most complex functions."""

    if function_df.empty:
        return pd.DataFrame(columns=["function_rank", "function_share", "cumulative_bugfix_share"])

    from matplotlib.ticker import PercentFormatter

    plot_df = function_df.sort_values(
        ["complexity", "n_bugfix_commits", "function"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    total_functions = len(plot_df)
    total_bugfix_commits = float(plot_df["n_bugfix_commits"].sum())
    summary = pd.DataFrame(
        {
            "function_rank": range(1, total_functions + 1),
            "function_share": pd.Series(range(1, total_functions + 1), dtype=float) / total_functions,
            "cumulative_bugfix_share": (
                plot_df["n_bugfix_commits"].cumsum() / total_bugfix_commits
                if total_bugfix_commits > 0
                else 0.0
            ),
        }
    )

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(9, 6))
    step_x = pd.concat(
        [pd.Series([0.0]), summary["function_share"].reset_index(drop=True)],
        ignore_index=True,
    )
    step_y = pd.concat(
        [pd.Series([0.0]), summary["cumulative_bugfix_share"].reset_index(drop=True)],
        ignore_index=True,
    )
    ax.step(
        step_x,
        step_y,
        where="post",
        color="#264653",
        linewidth=2,
        label="Observed cumulative bug-fix share",
    )
    ax.plot(
        [0, 1],
        [0, 1],
        linestyle="--",
        color="#8d99ae",
        linewidth=1,
        label="Even distribution across all functions",
    )

    for share in [0.10, 0.20, 0.50]:
        nearest_index = (summary["function_share"] - share).abs().idxmin()
        row = summary.loc[nearest_index]
        bugfix_share = float(row["cumulative_bugfix_share"])
        ax.scatter([share], [bugfix_share], color="#e07a5f", s=28, zorder=3)
        ax.annotate(
            f"Top {share:.0%} -> {bugfix_share:.1%}",
            xy=(share, bugfix_share),
            xytext=(6, 8 if share < 0.5 else -18),
            textcoords="offset points",
            fontsize="small",
            color="#e07a5f",
        )

    saturation_rows = summary.loc[summary["cumulative_bugfix_share"] >= 1.0]
    if not saturation_rows.empty:
        saturation_share = float(saturation_rows.iloc[0]["function_share"])
        ax.axvline(saturation_share, linestyle=":", color="#e76f51", linewidth=1.5)
        ax.text(
            min(saturation_share + 0.02, 0.82),
            0.93,
            (
                f"After the top {saturation_share:.1%},\n"
                "the remaining functions add no bug-fix commits"
            ),
            color="#e76f51",
            fontsize="small",
            va="top",
        )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Top x% most complex functions")
    ax.set_ylabel("Cumulative share of all bug-fix commits captured")
    ax.set_title("Bug-fix commits captured as functions are added by descending complexity")
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    ax.legend(loc="lower right", fontsize="small", frameon=True)
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return summary


def plot_repeat_bugfix_distribution(function_df: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Plot the exact bug-fix count distribution across analyzed functions."""

    if function_df.empty:
        return pd.DataFrame(columns=["bugfix_commits", "functions_with_exact_count", "share"])

    total_functions = int(len(function_df))
    counts = function_df["n_bugfix_commits"].fillna(0).astype(int).value_counts().sort_index()
    max_bugfix_count = int(counts.index.max()) if not counts.empty else 0
    summary = pd.DataFrame(
        {
            "bugfix_commits": list(range(0, max_bugfix_count + 1)),
        }
    )
    summary["functions_with_exact_count"] = summary["bugfix_commits"].map(counts).fillna(0).astype(int)
    summary["share"] = summary["functions_with_exact_count"] / total_functions

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.lineplot(data=summary, x="bugfix_commits", y="share", marker="o", color="#e76f51", ax=ax)
    ax.set_xticks(list(range(0, max_bugfix_count + 1)))
    ax.set_xlabel("Bug-fix commits touching a function")
    ax.set_ylabel("Share of analyzed functions with exactly that count")
    ax.set_title("How are bug-fix counts distributed across analyzed functions?")
    for row in summary.itertuples(index=False):
        ax.annotate(
            str(int(row.functions_with_exact_count)),
            (row.bugfix_commits, row.share),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize="small",
        )
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return summary


def build_extreme_bugfix_function_table(
    function_df: pd.DataFrame,
    bugfix_event_df: pd.DataFrame,
    top_distinct_counts: int = 3,
) -> pd.DataFrame:
    """Build a commit-level table for functions in the highest bug-fix count bands."""

    columns = [
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
    if function_df.empty or bugfix_event_df.empty:
        return pd.DataFrame(columns=columns)

    distinct_counts = sorted(
        {
            int(value)
            for value in function_df["n_bugfix_commits"].dropna().tolist()
            if int(value) > 0
        },
        reverse=True,
    )
    if not distinct_counts:
        return pd.DataFrame(columns=columns)

    selected_counts = distinct_counts[:top_distinct_counts]
    extreme_functions = function_df.loc[
        function_df["n_bugfix_commits"].isin(selected_counts),
        ["package", "package_rank", "file_path", "function", "kind", "complexity", "n_bugfix_commits"],
    ].copy()
    if extreme_functions.empty:
        return pd.DataFrame(columns=columns)

    event_rows = bugfix_event_df.loc[
        :,
        [
            "package",
            "after_file_path",
            "before_file_path",
            "function",
            "kind",
            "bugfix_commit",
            "bugfix_commit_date",
            "bugfix_message",
        ],
    ].copy()
    event_rows["file_path"] = event_rows["after_file_path"].fillna(event_rows["before_file_path"])
    merged = extreme_functions.merge(
        event_rows[
            [
                "package",
                "file_path",
                "function",
                "kind",
                "bugfix_commit",
                "bugfix_commit_date",
                "bugfix_message",
            ]
        ],
        on=["package", "file_path", "function", "kind"],
        how="left",
    )
    merged = merged.sort_values(
        ["n_bugfix_commits", "package", "file_path", "function", "bugfix_commit_date", "bugfix_commit"],
        ascending=[False, True, True, True, True, True],
    ).reset_index(drop=True)
    return merged.reindex(columns=columns)


def build_selected_package_overview(
    packages_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    analysis_run_details_path: Path | None = None,
) -> pd.DataFrame:
    """Build the selected-package overview table used in the methods chapter."""

    columns = ["rank", "package", "version", "commit_code", "functions_analyzed"]
    if packages_df.empty:
        return pd.DataFrame(columns=columns)

    commit_codes: dict[str, str] = {}
    if analysis_run_details_path is not None and analysis_run_details_path.exists():
        for line in analysis_run_details_path.read_text(encoding="utf-8").splitlines():
            match = RUN_DETAILS_HEAD_PATTERN.match(line.strip())
            if match is None:
                continue
            commit_codes[match.group("package")] = match.group("commit_hash")[:12]

    overview = packages_df.loc[:, ["rank", "name", "version"]].rename(columns={"name": "package"})
    functions = (
        package_summary.loc[:, ["package", "functions_analyzed"]]
        if not package_summary.empty
        else pd.DataFrame(columns=["package", "functions_analyzed"])
    )
    overview = overview.merge(functions, on="package", how="left")
    overview["commit_code"] = overview["package"].map(commit_codes).fillna("")
    overview["functions_analyzed"] = overview["functions_analyzed"].fillna(0).astype(int)
    return overview.reindex(columns=columns)


def build_package_correlation_table(package_summary: pd.DataFrame) -> pd.DataFrame:
    """Build the compact package-level correlation table used in the results chapter."""

    columns = ["package", "spearman_r", "pearson_r"]
    if package_summary.empty:
        return pd.DataFrame(columns=columns)

    table = package_summary.loc[:, ["package_rank", "package", "spearman_r", "pearson_r"]].copy()
    table = table.sort_values(["spearman_r", "package"], ascending=[False, True]).reset_index(drop=True)
    table["spearman_r"] = table["spearman_r"].map(lambda value: f"{float(value):.3f}")
    table["pearson_r"] = table["pearson_r"].map(lambda value: f"{float(value):.3f}")
    return table.loc[:, columns]


def build_szz_matched_summary(szz_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize only matched SZZ attributions with explicit function pairs."""

    columns = ["category", "count", "share", "matched_total", "overall_total"]
    if szz_df.empty:
        return pd.DataFrame(columns=columns)

    matched_categories = ["Increase", "No change", "Decrease"]
    matched = szz_df.loc[szz_df["complexity_category"].isin(matched_categories)].copy()
    overall_total = int(len(szz_df))
    matched_total = int(len(matched))
    if matched_total == 0:
        return pd.DataFrame(columns=columns)

    summary = matched.groupby("complexity_category").size().reset_index(name="count")
    summary = summary.rename(columns={"complexity_category": "category"})
    summary["share"] = summary["count"] / matched_total
    summary["matched_total"] = matched_total
    summary["overall_total"] = overall_total
    summary["category"] = pd.Categorical(summary["category"], categories=matched_categories, ordered=True)
    summary = summary.sort_values("category").reset_index(drop=True)
    return summary.reindex(columns=columns)


def build_overall_szz_lag_summary(szz_df: pd.DataFrame) -> pd.DataFrame:
    """Build a one-row overall lag summary across all valid SZZ pairs."""

    columns = ["pair_count", "median_lag_days", "p25_lag_days", "p75_lag_days"]
    if szz_df.empty:
        return pd.DataFrame(columns=columns)

    lag_df = szz_df[
        [
            "bugfix_commit",
            "bugfix_commit_date",
            "bug_introducing_commit",
            "bug_introducing_commit_date",
        ]
    ].drop_duplicates().copy()
    lag_df["bugfix_commit_date"] = pd.to_datetime(lag_df["bugfix_commit_date"], utc=True, errors="coerce")
    lag_df["bug_introducing_commit_date"] = pd.to_datetime(
        lag_df["bug_introducing_commit_date"], utc=True, errors="coerce"
    )
    lag_df = lag_df.dropna(subset=["bugfix_commit_date", "bug_introducing_commit_date"])
    if lag_df.empty:
        return pd.DataFrame(columns=columns)

    lag_df["lag_days"] = (
        lag_df["bugfix_commit_date"] - lag_df["bug_introducing_commit_date"]
    ).dt.total_seconds() / 86400.0
    lag_df = lag_df.loc[lag_df["lag_days"] >= 0].copy()
    if lag_df.empty:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(
        [
            {
                "pair_count": int(len(lag_df)),
                "median_lag_days": float(lag_df["lag_days"].median()),
                "p25_lag_days": float(lag_df["lag_days"].quantile(0.25)),
                "p75_lag_days": float(lag_df["lag_days"].quantile(0.75)),
            }
        ],
        columns=columns,
    )


def plot_package_normalized_bugfix_density(package_summary: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Plot package-level bug-fix densities normalized by analyzed function count."""

    if package_summary.empty:
        return pd.DataFrame(columns=["package", "metric", "value"])

    summary = package_summary.copy()
    denominator = summary["functions_analyzed"].where(summary["functions_analyzed"] > 0)
    summary["bugfixed_function_share"] = (summary["functions_bugfixed"] / denominator).fillna(0.0)
    summary["bugfix_commit_density"] = (summary["bugfix_commits"] / denominator).fillna(0.0)
    summary["introducing_commit_density"] = (
        summary["unique_bug_introducing_commits"] / denominator
    ).fillna(0.0)
    long_summary = summary[["package", "bugfixed_function_share", "bugfix_commit_density", "introducing_commit_density"]].melt(
        id_vars="package",
        var_name="metric",
        value_name="value",
    )
    metric_labels = {
        "bugfixed_function_share": "Bug-fixed functions / analyzed functions",
        "bugfix_commit_density": "Bug-fix commits / analyzed functions",
        "introducing_commit_density": "Unique bug-introducing commits / analyzed functions",
    }
    long_summary["metric"] = long_summary["metric"].map(metric_labels)
    package_order = (
        summary.sort_values("bugfix_commit_density", ascending=True)["package"].tolist()
    )

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(11, 6))
    sns.barplot(
        data=long_summary,
        y="package",
        x="value",
        hue="metric",
        order=package_order,
        orient="h",
        ax=ax,
    )
    ax.set_xlabel("Normalized rate")
    ax.set_ylabel("Package")
    ax.set_title("How bug-fix burden differs after normalizing for package size")
    ax.legend(loc="lower right", fontsize="small", frameon=True)
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return long_summary


def plot_complexity_buckets(function_df: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Create a complexity bucket summary plot."""

    ensure_directory(target.parent)
    from matplotlib.ticker import PercentFormatter

    plt, sns = load_plotting_modules()
    bucket_df, bucket_labels = assign_complexity_buckets(function_df)
    summary = (
        bucket_df.groupby("complexity_bucket", observed=False)
        .agg(
            functions=("function", "count"),
            bugfixed_functions=("was_bugfixed", "sum"),
            mean_bugfix_commits=("n_bugfix_commits", "mean"),
        )
        .reset_index()
    )
    summary["complexity_bucket"] = pd.Categorical(
        summary["complexity_bucket"],
        categories=bucket_labels,
        ordered=True,
    )
    summary = summary.sort_values("complexity_bucket").reset_index(drop=True)
    summary["mean_bugfix_commits"] = summary["mean_bugfix_commits"].fillna(0.0)
    summary["bugfix_share"] = (
        summary["bugfixed_functions"] / summary["functions"].where(summary["functions"] > 0)
    ).fillna(0.0)

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=summary, x="complexity_bucket", y="bugfix_share", color="#e07a5f", ax=ax)
    y_max = float(summary["bugfix_share"].max()) if not summary.empty else 0.0
    offset = max(y_max * 0.015, 0.01)
    for patch, row in zip(ax.patches, summary.itertuples(index=False), strict=False):
        height = patch.get_height()
        ax.text(
            patch.get_x() + patch.get_width() / 2,
            height + offset,
            f"{int(row.bugfixed_functions)}/{int(row.functions)}\n{float(row.bugfix_share):.1%}",
            ha="center",
            va="bottom",
            fontsize="small",
            clip_on=False,
        )
    if y_max > 0:
        ax.set_ylim(0, y_max + (offset * 6))
    ax.set_xlabel("Cyclomatic complexity score")
    ax.set_ylabel("Percentage of functions touched by bug-fix commits")
    ax.set_title("Percentage of bug-fixed functions by cyclomatic complexity score")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return summary


def plot_bugfix_complexity_before_after(bugfix_event_df: pd.DataFrame, target: Path) -> None:
    """Plot function complexity before and after bug-fix commits."""

    measured = bugfix_event_df.dropna(
        subset=["bugfix_before_complexity", "bugfix_after_complexity"]
    ).copy()
    if measured.empty:
        return

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    max_complexity = max(
        float(measured["bugfix_before_complexity"].max()),
        float(measured["bugfix_after_complexity"].max()),
    )
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.scatterplot(
        data=measured,
        x="bugfix_before_complexity",
        y="bugfix_after_complexity",
        alpha=0.4,
        s=28,
        color="#33658a",
        ax=ax,
    )
    ax.plot([0, max_complexity], [0, max_complexity], linestyle="--", color="#8d99ae", linewidth=1)
    ax.set_xlabel("Complexity before bug-fix commit")
    ax.set_ylabel("Complexity after bug-fix commit")
    ax.set_title("Function complexity before and after bug-fix commits")
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)


def plot_bugfix_complexity_changes(bugfix_event_df: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Plot how bug-fix commits change function complexity."""

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    if bugfix_event_df.empty:
        return pd.DataFrame(
            [{"category": "No bug-fix events", "count": 0, "share": math.nan}]
        )

    plot_df = bugfix_event_df.copy()
    plot_df["category"] = plot_df["bugfix_complexity_category"].fillna("Function pair not recoverable")
    present_categories = [
        category for category in BUGFIX_CATEGORY_ORDER if category in set(plot_df["category"])
    ]
    plot_df["category"] = pd.Categorical(plot_df["category"], categories=present_categories, ordered=True)
    summary = plot_df.groupby("category", observed=True).size().reset_index(name="count")
    summary["share"] = summary["count"] / summary["count"].sum()

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(
        data=summary,
        x="category",
        y="count",
        hue="category",
        palette="muted",
        dodge=False,
        legend=False,
        ax=ax,
    )
    y_max = float(summary["count"].max()) if not summary.empty else 0.0
    offset = max(y_max * 0.01, 0.5)
    for patch, row in zip(ax.patches, summary.itertuples(index=False), strict=False):
        height = patch.get_height()
        ax.text(
            patch.get_x() + patch.get_width() / 2,
            height + offset,
            str(int(row.count)),
            ha="center",
            va="bottom",
            fontsize="small",
            clip_on=False,
        )
    if y_max > 0:
        ax.set_ylim(0, y_max + (offset * 6))
    ax.set_xlabel("Bug-fix commit category")
    ax.set_ylabel("Touched functions")
    ax.set_title("How do bug-fix commits change function complexity?")
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return summary


def plot_bugfix_commit_timeline(
    bugfix_event_df: pd.DataFrame,
    target: Path,
    analysis_years: float,
    granularity: str = "auto",
) -> pd.DataFrame:
    """Plot bug-fix commit counts over time."""

    if bugfix_event_df.empty:
        return pd.DataFrame(columns=["period_start", "period_label", "count"])

    timeline_df = bugfix_event_df[["package", "bugfix_commit", "bugfix_commit_date"]].drop_duplicates().copy()
    timeline_df["bugfix_commit_date"] = pd.to_datetime(
        timeline_df["bugfix_commit_date"],
        utc=True,
        errors="coerce",
    )
    timeline_df = timeline_df.dropna(subset=["bugfix_commit_date"])
    if timeline_df.empty:
        return pd.DataFrame(columns=["period_start", "period_label", "count"])

    resolved_granularity = granularity
    if resolved_granularity == "auto":
        resolved_granularity = "month" if analysis_years <= 2 else "year"

    frequency = {
        "month": "MS",
        "quarter": "QS",
        "year": "YS",
    }[resolved_granularity]
    summary = (
        timeline_df.set_index("bugfix_commit_date")
        .groupby(pd.Grouper(freq=frequency))
        .size()
        .rename("count")
        .reset_index()
        .rename(columns={"bugfix_commit_date": "period_start"})
    )
    if resolved_granularity == "month":
        summary["period_label"] = summary["period_start"].dt.strftime("%Y-%m")
        axis_label = "Month"
    elif resolved_granularity == "quarter":
        summary["period_label"] = summary["period_start"].apply(
            lambda value: f"Q{value.quarter} {value.year}"
        )
        axis_label = "Quarter"
    else:
        summary["period_label"] = summary["period_start"].dt.strftime("%Y")
        axis_label = "Year"

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.lineplot(data=summary, x="period_label", y="count", marker="o", color="#2a9d8f", ax=ax)
    ax.set_xlabel(axis_label)
    ax.set_ylabel("Bug-fix commits")
    ax.set_title("Bug-fix commit frequency over time")
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return summary


def plot_szz_fix_lag_distribution(szz_df: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Plot the time lag between attributed bug-introducing and bug-fixing commits."""

    if szz_df.empty:
        return pd.DataFrame(columns=["package", "pair_count", "median_lag_days", "p25_lag_days", "p75_lag_days"])

    lag_df = szz_df[
        [
            "package",
            "bugfix_commit",
            "bugfix_commit_date",
            "bug_introducing_commit",
            "bug_introducing_commit_date",
        ]
    ].drop_duplicates().copy()
    lag_df["bugfix_commit_date"] = pd.to_datetime(lag_df["bugfix_commit_date"], utc=True, errors="coerce")
    lag_df["bug_introducing_commit_date"] = pd.to_datetime(
        lag_df["bug_introducing_commit_date"], utc=True, errors="coerce"
    )
    lag_df = lag_df.dropna(subset=["bugfix_commit_date", "bug_introducing_commit_date"])
    if lag_df.empty:
        return pd.DataFrame(columns=["package", "pair_count", "median_lag_days", "p25_lag_days", "p75_lag_days"])

    lag_df["lag_days"] = (
        lag_df["bugfix_commit_date"] - lag_df["bug_introducing_commit_date"]
    ).dt.total_seconds() / 86400.0
    lag_df = lag_df.loc[lag_df["lag_days"] >= 0].copy()
    if lag_df.empty:
        return pd.DataFrame(columns=["package", "pair_count", "median_lag_days", "p25_lag_days", "p75_lag_days"])

    summary = (
        lag_df.groupby("package")
        .agg(
            pair_count=("lag_days", "size"),
            median_lag_days=("lag_days", "median"),
            p25_lag_days=("lag_days", lambda values: values.quantile(0.25)),
            p75_lag_days=("lag_days", lambda values: values.quantile(0.75)),
        )
        .reset_index()
        .sort_values("median_lag_days", ascending=True)
    )

    def format_years_label(days: float) -> str:
        years = float(days) / 365.25
        if years >= 10:
            return f"median {years:.1f}y"
        if years >= 1:
            return f"median {years:.2f}y"
        return f"median {years:.3f}y"

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(11, 6))
    plot_lag_df = lag_df.copy()
    plot_lag_df["lag_days_plot"] = plot_lag_df["lag_days"].clip(lower=1.0)
    sns.boxplot(
        data=plot_lag_df,
        y="package",
        x="lag_days_plot",
        order=summary["package"].tolist(),
        orient="h",
        ax=ax,
    )
    ax.set_xscale("log")
    ax.set_xlim(left=1.0)
    for index, row in enumerate(summary.itertuples(index=False)):
        plotted_median = max(float(row.median_lag_days), 1.0)
        ax.annotate(
            format_years_label(float(row.median_lag_days)),
            (plotted_median, index),
            textcoords="offset points",
            xytext=(0, 0),
            ha="center",
            va="center",
            fontsize="small",
            clip_on=False,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "#8d99ae", "alpha": 0.9},
        )
    ax.set_xlabel("Days between attributed bug-introducing and bug-fixing commits (log scale; values < 1 day shown at 1 day)")
    ax.set_ylabel("Package")
    ax.set_title("How long do attributed bugs stay latent before a bug-fixing commit?")
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return summary


def plot_package_correlations(package_summary: pd.DataFrame, target: Path) -> None:
    """Plot package-level Spearman correlations."""

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(10, 6))
    ordered = package_summary.sort_values("spearman_r", ascending=True)
    ax.barh(ordered["package"], ordered["spearman_r"], color="#81b29a")
    ax.axvline(0, color="black", linewidth=1)
    ax.set_xlabel("Spearman correlation")
    ax.set_ylabel("Package")
    ax.set_title("Package-level complexity to bug-fix correlation")
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)


def plot_szz_summary(szz_df: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Plot SZZ complexity outcomes and return the summary table.

    Parameters
    ----------
    szz_df : pandas.DataFrame
        Function-level SZZ attribution rows.
    target : Path
        Output path for the rendered plot image.

    Returns
    -------
    pandas.DataFrame
        Summary counts and shares for each plotted SZZ complexity category.
    """

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    if szz_df.empty:
        summary = pd.DataFrame(
            [{"category": "No SZZ attributions", "count": 0, "share": math.nan}]
        )
        return summary

    plot_df = szz_df.copy()
    if "complexity_category" in plot_df.columns:
        plot_df["category"] = plot_df["complexity_category"].fillna("Function pair not recoverable")
    else:
        plot_df["category"] = plot_df["complexity_delta"].apply(
            lambda value: "Increase"
            if value is not None and not pd.isna(value) and value > 0
            else (
                "Decrease"
                if value is not None and not pd.isna(value) and value < 0
                else (
                    "No change"
                    if value is not None and not pd.isna(value)
                    else "Function pair not recoverable"
                )
            )
        )
    present_categories = [
        category for category in SZZ_CATEGORY_ORDER if category in set(plot_df["category"])
    ]
    plot_df["category"] = pd.Categorical(
        plot_df["category"],
        categories=present_categories,
        ordered=True,
    )
    summary = (
        plot_df.groupby("category", observed=True).size().reset_index(name="count")
    )
    summary["share"] = summary["count"] / summary["count"].sum()
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(
        data=summary,
        x="category",
        y="count",
        hue="category",
        palette="deep",
        dodge=False,
        legend=False,
        ax=ax,
    )
    y_max = float(summary["count"].max()) if not summary.empty else 0.0
    offset = max(y_max * 0.01, 0.5)
    for patch, row in zip(ax.patches, summary.itertuples(index=False), strict=False):
        height = patch.get_height()
        ax.text(
            patch.get_x() + patch.get_width() / 2,
            height + offset,
            str(int(row.count)),
            ha="center",
            va="bottom",
            fontsize="small",
            clip_on=False,
        )
    if y_max > 0:
        ax.set_ylim(0, y_max + (offset * 6))
    ax.set_xlabel("Bug-introducing commit category")
    ax.set_ylabel("Attributed commits")
    ax.set_title("How did the attributed bug-introducing commit affect complexity?")
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)
    return summary


def build_summary_markdown(
    packages_df: pd.DataFrame,
    function_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    szz_summary: pd.DataFrame,
) -> str:
    """Build a Markdown summary for the current analysis run."""

    overall_spearman = math.nan
    overall_spearman_p = math.nan
    if not function_df.empty and function_df["complexity"].nunique() > 1 and function_df["n_bugfix_commits"].nunique() > 1:
        result = spearmanr(function_df["complexity"], function_df["n_bugfix_commits"])
        overall_spearman = float(result.statistic)
        overall_spearman_p = float(result.pvalue)

    highest_bucket_share = None
    if not bucket_summary.empty:
        highest_bucket_share = bucket_summary.sort_values("bugfix_share", ascending=False).iloc[0]
    szz_text = "No SZZ attributions were produced."
    if not szz_summary.empty and szz_summary["count"].sum() > 0:
        top_category = szz_summary.sort_values("count", ascending=False).iloc[0]
        share = float(top_category.get("share", math.nan))
        if not math.isnan(share):
            szz_text = (
                f"The largest SZZ category was {top_category['category']} with "
                f"{share:.1%} of attributed commits."
            )
    top_names = ", ".join(packages_df["name"].tolist()) if not packages_df.empty else "None"
    complexity_text = (
        f"Across {len(function_df):,} functions, the overall Spearman correlation between "
        f"cyclomatic complexity and bug-fix commit count was {overall_spearman:.4f} "
        f"(p={overall_spearman_p:.4f})."
        if not math.isnan(overall_spearman)
        else (
            "Function-level metrics were available, but the overall correlation could not be estimated because the data were constant."
            if not function_df.empty
            else "No function-level metrics were available for this run."
        )
    )
    bucket_text = (
        f"The highest complexity bucket was {highest_bucket_share['complexity_bucket']} and "
        f"showed a bug-fix share of {highest_bucket_share['bugfix_share']:.1%}."
        if highest_bucket_share is not None
        else "No complexity bucket summary was produced."
    )
    return "\n".join(
        [
            "# Ecosystem Analysis Summary",
            "",
            "## Package set",
            f"Selected packages: {top_names}.",
            "",
            "## Complexity and bug fixes",
            complexity_text,
            bucket_text,
            "",
            "## SZZ heuristic",
            szz_text,
            "",
            "## Notes",
            "Bug-fix commits are identified with a commit-message heuristic.",
            "Package selection follows the Libraries.io PyPI dependent-count leaderboard, filtered to packages with resolvable GitHub source repositories.",
            "The SZZ pass is line-based and intentionally conservative: unresolved file history and renamed functions are left as missing values.",
        ]
    )


def package_records_to_frame(records: Sequence[PackageRecord]) -> pd.DataFrame:
    """Convert package records to a dataframe."""

    return pd.DataFrame([record.__dict__ for record in records])


def sanitize_json_value(value: Any) -> Any:
    """Convert pandas/NumPy-style missing values into JSON-safe values."""

    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if pd.isna(value):
        return None
    return value


def write_raw_results_json(
    packages_df: pd.DataFrame,
    function_df: pd.DataFrame,
    package_summary: pd.DataFrame,
    bugfix_event_df: pd.DataFrame,
    szz_df: pd.DataFrame,
    target: Path,
) -> None:
    """Write a grouped JSON view of the analysis results keyed by function."""

    ensure_directory(target.parent)

    functions: dict[tuple[str, str, str], dict[str, Any]] = {}
    event_index: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in function_df.to_dict(orient="records"):
        key = (row["package"], row["file_path"], row["function"])
        functions[key] = {
            "package": row["package"],
            "package_rank": row.get("package_rank"),
            "file_path": row["file_path"],
            "function": row["function"],
            "kind": row.get("kind"),
            "current_complexity": row.get("complexity"),
            "n_bugfix_commits": row.get("n_bugfix_commits"),
            "n_touch_commits": row.get("n_touch_commits"),
            "was_bugfixed": row.get("was_bugfixed"),
            "bugfix_events": [],
        }

    for row in bugfix_event_df.to_dict(orient="records"):
        canonical_path = row.get("after_file_path") or row.get("before_file_path") or ""
        key = (row["package"], canonical_path, row["function"])
        function_record = functions.setdefault(
            key,
            {
                "package": row["package"],
                "package_rank": row.get("package_rank"),
                "file_path": canonical_path,
                "function": row["function"],
                "kind": row.get("kind"),
                "current_complexity": None,
                "n_bugfix_commits": None,
                "n_touch_commits": None,
                "was_bugfixed": 1,
                "bugfix_events": [],
            },
        )
        event_record = {
            "bugfix_commit": row.get("bugfix_commit"),
            "bugfix_message": row.get("bugfix_message"),
            "bugfix_commit_date": row.get("bugfix_commit_date"),
            "before_file_path": row.get("before_file_path"),
            "after_file_path": row.get("after_file_path"),
            "before_complexity": row.get("bugfix_before_complexity"),
            "after_complexity": row.get("bugfix_after_complexity"),
            "complexity_delta": row.get("bugfix_complexity_delta"),
            "complexity_category": row.get("bugfix_complexity_category"),
            "bug_introducing_commits": [],
        }
        function_record["bugfix_events"].append(event_record)
        for path_value in {row.get("before_file_path"), row.get("after_file_path"), canonical_path}:
            if path_value:
                event_index[(row["package"], path_value, row["function"], row["bugfix_commit"])] = event_record

    for row in szz_df.to_dict(orient="records"):
        event_record = event_index.get(
            (row["package"], row["file_path"], row["function"], row["bugfix_commit"])
        )
        if event_record is None:
            canonical_key = (row["package"], row["file_path"], row["function"])
            function_record = functions.setdefault(
                canonical_key,
                {
                    "package": row["package"],
                    "package_rank": None,
                    "file_path": row["file_path"],
                    "function": row["function"],
                    "kind": None,
                    "current_complexity": None,
                    "n_bugfix_commits": None,
                    "n_touch_commits": None,
                    "was_bugfixed": None,
                    "bugfix_events": [],
                },
            )
            event_record = {
                "bugfix_commit": row.get("bugfix_commit"),
                "bugfix_message": row.get("bugfix_message"),
                "bugfix_commit_date": row.get("bugfix_commit_date"),
                "before_file_path": row.get("file_path"),
                "after_file_path": row.get("file_path"),
                "before_complexity": None,
                "after_complexity": None,
                "complexity_delta": None,
                "complexity_category": None,
                "bug_introducing_commits": [],
            }
            function_record["bugfix_events"].append(event_record)
            event_index[(row["package"], row["file_path"], row["function"], row["bugfix_commit"])] = event_record

        event_record["bug_introducing_commits"].append(
            {
                "commit": row.get("bug_introducing_commit"),
                "message": row.get("bug_introducing_message"),
                "commit_date": row.get("bug_introducing_commit_date"),
                "complexity_delta": row.get("complexity_delta"),
                "complexity_category": row.get("complexity_category"),
                "complexity_increased": row.get("complexity_increased"),
            }
        )

    payload = {
        "packages": packages_df.to_dict(orient="records"),
        "package_summary": package_summary.to_dict(orient="records"),
        "functions": sorted(
            functions.values(),
            key=lambda item: (item.get("package") or "", item.get("file_path") or "", item.get("function") or ""),
        ),
    }
    target.write_text(
        json.dumps(sanitize_json_value(payload), indent=2, sort_keys=False),
        encoding="utf-8",
    )