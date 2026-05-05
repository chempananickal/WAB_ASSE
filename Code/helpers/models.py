from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedFunction:
    """Representation of a Python function or method.

    Parameters
    ----------
    file_path:
        Repository-relative path of the file containing the function.
    qualname:
        Qualified name of the function, including any class or outer function
        scopes.
    start_line:
        First line of the function definition.
    end_line:
        Last line belonging to the function body.
    complexity:
        Cyclomatic complexity estimate for the function.
    kind:
        Function kind, either ``function`` or ``method``.
    """

    file_path: str
    qualname: str
    start_line: int
    end_line: int
    complexity: int
    kind: str


@dataclass(frozen=True)
class PackageRecord:
    """Metadata for a selected PyPI package.

    Parameters
    ----------
    rank:
        Rank in the selected package set.
    name:
        Normalized PyPI project name.
    version:
        Selected release version.
    source_repo:
        Canonical source repository identifier when resolvable.
    source_repo_url:
        Cloneable repository URL.
    provenance:
        Provenance label for the source repository mapping.
    summary:
        Short project summary from PyPI metadata.
    """

    rank: int
    name: str
    version: str
    source_repo: str
    source_repo_url: str
    provenance: str
    summary: str


@dataclass(frozen=True)
class BugfixDeletionRecord:
    """Deleted line information needed for the simplified SZZ pass.

    Parameters
    ----------
    package_name:
        Package under analysis.
    bugfix_commit:
        Commit hash of the bug-fixing commit.
    parent_commit:
        Parent hash blamed against.
    file_path:
        Repository-relative file path in the parent revision.
    function_qualname:
        Function qualified name containing the deleted lines.
    deleted_lines:
        Deleted line numbers from the parent revision.
    """

    package_name: str
    bugfix_commit: str
    parent_commit: str
    file_path: str
    function_qualname: str
    deleted_lines: tuple[int, ...]