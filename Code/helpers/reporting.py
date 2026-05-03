from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
from scipy.stats import spearmanr

from .common import ensure_directory
from .models import PackageRecord


SZZ_CATEGORY_ORDER = [
    "Increase",
    "No change",
    "Decrease",
    "New function",
    "Deleted or renamed",
    "Match unavailable",
    "No parent commit",
]
BUGFIX_CATEGORY_ORDER = [
    "Increase",
    "No change",
    "Decrease",
    "New function",
    "Deleted or renamed",
    "Match unavailable",
]


def write_dataframe(df: pd.DataFrame, target: Path) -> None:
    """Write a dataframe to CSV."""

    ensure_directory(target.parent)
    df.to_csv(target, index=False)


def load_plotting_modules() -> tuple[Any, Any]:
    """Import plotting modules lazily so worker processes avoid the cost."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    return plt, sns


def assign_complexity_buckets(function_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Assign fixed-width complexity buckets with clean integer bounds."""

    bucket_df = function_df.copy()
    max_complexity = max(1, int(bucket_df["complexity"].max()))
    bucket_width = max(1, math.ceil(max_complexity / 10))
    bucket_edges = [bucket_width * index for index in range(11)]
    bucket_labels = [
        f"{1 if index == 0 else bucket_edges[index] + 1}-{bucket_edges[index + 1]}"
        for index in range(10)
    ]
    bucket_df["complexity_bucket"] = pd.cut(
        bucket_df["complexity"],
        bins=bucket_edges,
        include_lowest=True,
        labels=bucket_labels,
    )
    return bucket_df, bucket_labels


def plot_top_packages(packages_df: pd.DataFrame, target: Path) -> None:
    """Plot direct dependent counts for the selected packages."""

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6))
    ordered = packages_df.sort_values("direct_dependents", ascending=True)
    ax.barh(ordered["name"], ordered["direct_dependents"], color="#2a6f97")
    ax.set_xlabel("Direct dependents")
    ax.set_ylabel("Package")
    ax.set_title("Most depended-upon packages in the candidate pool")
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)


def plot_complexity_scatter(function_df: pd.DataFrame, target: Path) -> None:
    """Plot complexity against bug-fix counts."""

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(10, 6))
    plot_df = function_df.copy()
    plot_df["bugfix_plus_one"] = plot_df["n_bugfix_commits"] + 1
    sns.scatterplot(
        data=plot_df,
        x="complexity",
        y="bugfix_plus_one",
        hue="package",
        alpha=0.45,
        s=30,
        ax=ax,
    )
    ax.set_yscale("log")
    ax.set_xlabel("Cyclomatic complexity")
    ax.set_ylabel("Bug-fix commits touching function (+1, log scale)")
    ax.set_title("Function complexity versus bug-fix frequency")
    ax.legend(loc="upper right", fontsize="small", frameon=True)
    fig.tight_layout()
    fig.savefig(target, dpi=200)
    plt.close(fig)


def plot_complexity_buckets(function_df: pd.DataFrame, target: Path) -> pd.DataFrame:
    """Create a complexity bucket summary plot."""

    ensure_directory(target.parent)
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
    ax.set_xlabel("Complexity bucket")
    ax.set_ylabel("Share of functions touched by bug-fix commits")
    ax.set_title("Bug-fix exposure across fixed-width complexity buckets")
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
    plot_df["category"] = plot_df["bugfix_complexity_category"].fillna("Match unavailable")
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

    frequency = "MS" if analysis_years <= 2 else "YS"
    period_label = "%Y-%m" if analysis_years <= 2 else "%Y"
    summary = (
        timeline_df.set_index("bugfix_commit_date")
        .groupby(pd.Grouper(freq=frequency))
        .size()
        .rename("count")
        .reset_index()
        .rename(columns={"bugfix_commit_date": "period_start"})
    )
    summary["period_label"] = summary["period_start"].dt.strftime(period_label)

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.lineplot(data=summary, x="period_label", y="count", marker="o", color="#2a9d8f", ax=ax)
    ax.set_xlabel("Month" if analysis_years <= 2 else "Year")
    ax.set_ylabel("Bug-fix commits")
    ax.set_title("Bug-fix commit frequency over time")
    ax.tick_params(axis="x", rotation=25)
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
        plot_df["category"] = plot_df["complexity_category"].fillna("Match unavailable")
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
                    else "Match unavailable"
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
            "The reverse dependency ranking uses PyPI metadata plus deps.dev because PyPI does not expose a first-party reverse dependency leaderboard.",
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