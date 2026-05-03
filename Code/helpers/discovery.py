from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import requests
from tqdm import tqdm

from .models import PackageRecord

TOP_PYPI_PACKAGES_URL = (
    "https://hugovk.github.io/top-pypi-packages/"
    "top-pypi-packages-30-days.min.json"
)
DEPS_DEV_PACKAGE_URL = "https://api.deps.dev/v3alpha/systems/PYPI/packages/{name}"
DEPS_DEV_VERSION_URL = (
    "https://api.deps.dev/v3/systems/PYPI/packages/{name}/versions/{version}"
)
DEPS_DEV_DEPENDENTS_URL = (
    "https://api.deps.dev/v3alpha/systems/PYPI/packages/{name}/"
    "versions/{version}:dependents"
)
PYPI_PROJECT_URL = "https://pypi.org/pypi/{name}/json"
USER_AGENT = "WAB-ASSE-Ecosystem-Analysis/0.1"


def ensure_directory(path: Path) -> None:
    """Create a directory if it does not already exist."""

    path.mkdir(parents=True, exist_ok=True)


def normalize_pypi_name(name: str) -> str:
    """Normalize a PyPI project name using PEP 503 semantics."""

    return re.sub(r"[-_.]+", "-", name).lower()


def cache_path_for_url(cache_dir: Path, url: str) -> Path:
    """Build a deterministic JSON cache path for a URL."""

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def fetch_json(session: requests.Session, url: str, cache_dir: Path) -> Any:
    """Fetch JSON with a small on-disk cache."""

    ensure_directory(cache_dir)
    target = cache_path_for_url(cache_dir, url)
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))

    response = session.get(url, timeout=60)
    response.raise_for_status()
    payload = response.json()
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_session() -> requests.Session:
    """Create a configured HTTP session."""

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get_default_version(package_payload: Mapping[str, Any]) -> str | None:
    """Extract the default version from a deps.dev package payload."""

    versions = package_payload.get("versions", [])
    default_version = next((item for item in versions if item.get("isDefault")), None)
    if default_version is not None:
        return default_version.get("versionKey", {}).get("version")

    published = [item for item in versions if item.get("publishedAt")]
    if published:
        published.sort(key=lambda item: item["publishedAt"])
        return published[-1].get("versionKey", {}).get("version")

    if versions:
        return versions[-1].get("versionKey", {}).get("version")
    return None


def extract_github_identifier(url: str) -> str:
    """Convert a GitHub URL into a stable ``github.com/owner/repo`` identifier."""

    parsed = urlparse(url)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return ""
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"github.com/{owner}/{repo}"


def is_probable_release_repository(repo_id: str) -> bool:
    """Detect packaging-focused repositories that are poor analysis targets."""

    repo_name = repo_id.rsplit("/", maxsplit=1)[-1].lower()
    return bool(re.search(r"(^|[-_])(release|releases|dist|distribution)([-_]|$)", repo_name))


def pick_source_repository(
    version_payload: Mapping[str, Any], pypi_payload: Mapping[str, Any]
) -> tuple[str, str, str]:
    """Pick the most trustworthy source repository for a package."""

    candidates: list[tuple[int, str, str]] = []
    provenance_order = {
        "SLSA_ATTESTATION": 30,
        "PYPI_PUBLISH_ATTESTATION": 25,
        "GO_ORIGIN": 20,
        "RUBYGEMS_PUBLISH_ATTESTATION": 20,
        "UNVERIFIED_METADATA": 10,
    }
    for project in version_payload.get("relatedProjects", []):
        if project.get("relationType") != "SOURCE_REPO":
            continue
        repo_id = project.get("projectKey", {}).get("id", "")
        if not repo_id.startswith("github.com/"):
            continue
        score = provenance_order.get(project.get("relationProvenance", ""), 0)
        candidates.append((score, repo_id, project.get("relationProvenance", "UNKNOWN")))

    if candidates:
        if any(not is_probable_release_repository(repo_id) for _, repo_id, _ in candidates):
            candidates = [
                candidate
                for candidate in candidates
                if not is_probable_release_repository(candidate[1])
            ]
        candidates.sort(reverse=True)
        _, repo_id, provenance = candidates[0]
        return repo_id, f"https://{repo_id}.git", provenance

    info = pypi_payload.get("info", {})
    url_fields = [info.get("home_page", "")]
    project_urls = info.get("project_urls") or {}
    preferred_keys = [
        "Source",
        "Source Code",
        "Repository",
        "Homepage",
        "Home",
        "Code",
    ]
    url_fields.extend(project_urls.get(key, "") for key in preferred_keys)
    url_fields.extend(project_urls.values())

    for candidate in url_fields:
        repo_id = extract_github_identifier(candidate)
        if repo_id:
            return repo_id, f"https://{repo_id}.git", "PYPI_PROJECT_URL"

    return "", "", "UNRESOLVED"


def discover_top_packages(
    session: requests.Session,
    top_n: int,
    candidate_pool: int,
    cache_dir: Path,
    progress_bar: tqdm | None = None,
) -> list[PackageRecord]:
    """Discover the most depended-upon packages in a practical PyPI candidate pool."""

    ranking_payload = fetch_json(session, TOP_PYPI_PACKAGES_URL, cache_dir / "http")
    rows = ranking_payload.get("rows", [])[:candidate_pool]
    records: list[PackageRecord] = []

    for candidate in rows:
        package_name = normalize_pypi_name(candidate["project"])
        package_url = DEPS_DEV_PACKAGE_URL.format(name=quote(package_name, safe=""))
        try:
            package_payload = fetch_json(session, package_url, cache_dir / "http")
            version = get_default_version(package_payload)
            if not version:
                continue

            dependents_url = DEPS_DEV_DEPENDENTS_URL.format(
                name=quote(package_name, safe=""),
                version=quote(version, safe=""),
            )
            version_url = DEPS_DEV_VERSION_URL.format(
                name=quote(package_name, safe=""),
                version=quote(version, safe=""),
            )
            pypi_url = PYPI_PROJECT_URL.format(name=quote(package_name, safe=""))
            dependents_payload = fetch_json(session, dependents_url, cache_dir / "http")
            version_payload = fetch_json(session, version_url, cache_dir / "http")
            pypi_payload = fetch_json(session, pypi_url, cache_dir / "http")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                if progress_bar is not None:
                    progress_bar.update(1)
                continue
            raise

        source_repo, source_repo_url, provenance = pick_source_repository(
            version_payload, pypi_payload
        )
        records.append(
            PackageRecord(
                rank=0,
                name=package_name,
                version=version,
                direct_dependents=int(dependents_payload.get("directDependentCount", 0)),
                total_dependents=int(dependents_payload.get("dependentCount", 0)),
                source_repo=source_repo,
                source_repo_url=source_repo_url,
                provenance=provenance,
                summary=(pypi_payload.get("info", {}).get("summary") or "").strip(),
            )
        )
        if progress_bar is not None:
            progress_bar.update(1)

    ranked = sorted(records, key=lambda item: (-item.direct_dependents, item.name))[:top_n]
    return [
        PackageRecord(**{**record.__dict__, "rank": index})
        for index, record in enumerate(ranked, start=1)
    ]