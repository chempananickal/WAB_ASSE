from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
from scipy.stats import spearmanr

from .common import ensure_directory
from .models import PackageRecord


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
    unique_complexities = function_df["complexity"].nunique()
    quantiles = max(2, min(4, unique_complexities))
    bucket_df = function_df.copy()
    bucket_df["complexity_bucket"] = pd.qcut(
        bucket_df["complexity"], q=quantiles, duplicates="drop"
    )
    summary = (
        bucket_df.groupby("complexity_bucket", observed=True)
        .agg(
            functions=("function", "count"),
            bugfixed_functions=("was_bugfixed", "sum"),
            mean_bugfix_commits=("n_bugfix_commits", "mean"),
        )
        .reset_index()
    )
    summary["bugfix_share"] = summary["bugfixed_functions"] / summary["functions"]

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=summary, x="complexity_bucket", y="bugfix_share", color="#e07a5f", ax=ax)
    ax.set_xlabel("Complexity quartile")
    ax.set_ylabel("Share of functions touched by bug-fix commits")
    ax.set_title("Bug-fix exposure rises with complexity bucket")
    ax.tick_params(axis="x", rotation=15)
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
    """Plot whether bug-introducing commits increased complexity."""

    ensure_directory(target.parent)
    plt, sns = load_plotting_modules()
    if szz_df.empty:
        summary = pd.DataFrame(
            [{"category": "No SZZ attributions", "count": 0, "share": math.nan}]
        )
        return summary

    plot_df = szz_df.copy()
    plot_df["category"] = plot_df["complexity_delta"].apply(
        lambda value: "Increase"
        if value is not None and not pd.isna(value) and value > 0
        else ("No increase" if value is not None and not pd.isna(value) else "Unresolved")
    )
    summary = plot_df.groupby("category").size().reset_index(name="count")
    summary["share"] = summary["count"] / summary["count"].sum()
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=summary, x="category", y="count", palette="deep", ax=ax)
    ax.set_xlabel("Bug-introducing commit category")
    ax.set_ylabel("Attributed commits")
    ax.set_title("Did the attributed bug-introducing commit raise complexity?")
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

    top_names = ", ".join(packages_df["name"].tolist())
    return "\n".join(
        [
            "# Ecosystem Analysis Summary",
            "",
            "## Package set",
            f"Selected packages: {top_names}.",
            "",
            "## Complexity and bug fixes",
            (
                f"Across {len(function_df):,} functions, the overall Spearman correlation between "
                f"cyclomatic complexity and bug-fix commit count was {overall_spearman:.4f} "
                f"(p={overall_spearman_p:.4f})."
                if not math.isnan(overall_spearman)
                else "The overall correlation could not be estimated because the data were constant."
            ),
            (
                f"The highest complexity bucket was {highest_bucket_share['complexity_bucket']} and "
                f"showed a bug-fix share of {highest_bucket_share['bugfix_share']:.1%}."
            ),
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