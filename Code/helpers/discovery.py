from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from .models import PackageRecord

LIBRARIES_API_KEY_ENV_VAR = "LIBRARIES_API_KEY"
LIBRARIES_IO_PLATFORM = "PyPI"
LIBRARIES_IO_SEARCH_SORT = "dependents_count"
LIBRARIES_IO_SEARCH_PAGE_SIZE = 100
LOCAL_ENV_CANDIDATES = (".env", "Code/.env")
PYPI_PROJECT_URL = "https://pypi.org/pypi/{name}/json"
USER_AGENT = "WAB-ASSE-Ecosystem-Analysis/0.1"


def ensure_directory(path: Path) -> None:
    """Create a directory if it does not already exist."""

    path.mkdir(parents=True, exist_ok=True)


def normalize_pypi_name(name: str) -> str:
    """Normalize a PyPI project name using PEP 503 semantics."""

    return re.sub(r"[-_.]+", "-", name).lower()


def read_env_value(env_path: Path, key: str) -> str | None:
    """Read a single key from a simple .env-style file."""

    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        current_key, value = line.split("=", maxsplit=1)
        if current_key.strip() != key:
            continue
        return value.strip().strip("\"'")
    return None


def ensure_libraries_api_key() -> str:
    """Load the Libraries.io API key from the environment or a local .env file."""

    api_key = os.environ.get(LIBRARIES_API_KEY_ENV_VAR, "").strip()
    if api_key:
        return api_key

    repo_root = Path(__file__).resolve().parents[2]
    for candidate in LOCAL_ENV_CANDIDATES:
        env_path = repo_root / candidate
        api_key = read_env_value(env_path, LIBRARIES_API_KEY_ENV_VAR) or ""
        if api_key:
            os.environ[LIBRARIES_API_KEY_ENV_VAR] = api_key
            return api_key

    raise RuntimeError(
        "Libraries.io discovery requires LIBRARIES_API_KEY to be set in the environment "
        "or stored in a local .env file that is not committed."
    )


def build_libraries_search_client() -> Any:
    """Create a pybraries search client after loading the local API key."""

    ensure_libraries_api_key()
    try:
        from pybraries import Search
    except ImportError as exc:
        raise RuntimeError(
            "Libraries.io discovery requires the pybraries package to be installed."
        ) from exc
    return Search()


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


def fetch_libraries_search_page(search_client: Any, cache_dir: Path, page: int, per_page: int) -> Any:
    """Fetch a Libraries.io search page with on-disk caching."""

    ensure_directory(cache_dir)
    cache_key = (
        "libraries.io/search"
        f"?platforms={LIBRARIES_IO_PLATFORM}&sort={LIBRARIES_IO_SEARCH_SORT}"
        f"&page={page}&per_page={per_page}&keywords="
    )
    target = cache_path_for_url(cache_dir, cache_key)
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))

    payload = search_client.project_search(
        keywords="",
        platforms=LIBRARIES_IO_PLATFORM,
        sort=LIBRARIES_IO_SEARCH_SORT,
        page=page,
        per_page=per_page,
    )
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_session() -> requests.Session:
    """Create a configured HTTP session."""

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get_selected_version(candidate: Mapping[str, Any], pypi_payload: Mapping[str, Any]) -> str | None:
    """Pick the release version to record for a selected package."""

    for key in ("latest_stable_release_number", "latest_release_number"):
        value = str(candidate.get(key, "")).strip()
        if value:
            return value
    return str(pypi_payload.get("info", {}).get("version", "")).strip() or None


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
    candidate: Mapping[str, Any], pypi_payload: Mapping[str, Any]
) -> tuple[str, str, str]:
    """Pick the most trustworthy source repository for a package."""

    repository_url = str(candidate.get("repository_url", "")).strip()
    repo_id = extract_github_identifier(repository_url)
    if repo_id and not is_probable_release_repository(repo_id):
        return repo_id, f"https://{repo_id}.git", "LIBRARIES_IO"

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
    """Discover the most depended-upon packages in a practical PyPI pool.

    Parameters
    ----------
    session : requests.Session
        HTTP session used for PyPI requests.
    top_n : int
        Number of top-ranked packages to keep.
    candidate_pool : int
        Maximum number of ranked Libraries.io candidates to inspect while
        collecting ``top_n`` valid packages.
    cache_dir : Path
        Cache root for HTTP responses.
    progress_bar : tqdm | None, optional
        Progress bar updated as candidate packages are processed.

    Returns
    -------
    list[PackageRecord]
        Selected packages in Libraries.io ranking order with assigned ranks.
    """

    search_client = build_libraries_search_client()
    records: list[PackageRecord] = []
    seen: set[str] = set()
    inspected_candidates = 0
    page = 1

    while len(records) < top_n and inspected_candidates < candidate_pool:
        per_page = min(LIBRARIES_IO_SEARCH_PAGE_SIZE, candidate_pool - inspected_candidates)
        payload = fetch_libraries_search_page(search_client, cache_dir / "http", page, per_page)
        if not isinstance(payload, list) or not payload:
            break

        previous_inspected = inspected_candidates
        for candidate in payload:
            package_name = normalize_pypi_name(str(candidate.get("name", "")).strip())
            if not package_name or package_name in seen:
                continue

            seen.add(package_name)
            inspected_candidates += 1
            if progress_bar is not None:
                progress_bar.update(1)

            try:
                pypi_url = PYPI_PROJECT_URL.format(name=package_name)
                pypi_payload = fetch_json(session, pypi_url, cache_dir / "http")
                version = get_selected_version(candidate, pypi_payload)
                if not version:
                    continue
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    continue
                raise

            source_repo, source_repo_url, provenance = pick_source_repository(candidate, pypi_payload)
            if not source_repo_url:
                continue

            records.append(
                PackageRecord(
                    rank=0,
                    name=package_name,
                    version=version,
                    source_repo=source_repo,
                    source_repo_url=source_repo_url,
                    provenance=provenance,
                    summary=(pypi_payload.get("info", {}).get("summary") or "").strip(),
                )
            )
            if len(records) >= top_n or inspected_candidates >= candidate_pool:
                break

        if inspected_candidates == previous_inspected:
            break
        page += 1

    ranked = records[:top_n]
    return [
        PackageRecord(**{**record.__dict__, "rank": index})
        for index, record in enumerate(ranked, start=1)
    ]