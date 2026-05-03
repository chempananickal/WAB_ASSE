from __future__ import annotations

import logging
import queue
from datetime import datetime
from typing import Any, Mapping

from tqdm import tqdm

from .common import LOG_LEVELS

CURRENT_LOG_LEVEL = logging.INFO


def configure_logging(level_name: str) -> None:
    """Configure the terminal log verbosity for the current process."""

    global CURRENT_LOG_LEVEL
    CURRENT_LOG_LEVEL = LOG_LEVELS[level_name.upper()]


def render_log_line(level: int, message: str) -> str:
    """Render a compact terminal log line."""

    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"{timestamp} | {logging.getLevelName(level):<7} | {message}"


def log_message(message: str, level: int = logging.INFO) -> None:
    """Write a compact log line without breaking tqdm progress bars."""

    if level < CURRENT_LOG_LEVEL:
        return
    tqdm.write(render_log_line(level, message))


def emit_progress(
    progress_queue: Any | None,
    kind: str,
    package_name: str | None = None,
    **payload: Any,
) -> None:
    """Emit a worker progress event to the main process if available."""

    if progress_queue is None:
        return
    event: dict[str, Any] = {"kind": kind}
    if package_name is not None:
        event["package_name"] = package_name
    event.update(payload)
    progress_queue.put(event)


def emit_log(progress_queue: Any | None, message: str, level: int = logging.INFO) -> None:
    """Emit a log event either directly or through the shared progress queue."""

    if progress_queue is None:
        log_message(message, level=level)
        return
    emit_progress(progress_queue, "log", level=level, message=message)


def consume_progress_events(progress_queue: Any, repo_bars: Mapping[str, tqdm]) -> None:
    """Update repository progress bars from worker events."""

    while True:
        try:
            event = progress_queue.get(timeout=1.0)
        except queue.Empty:
            for bar in repo_bars.values():
                bar.refresh()
            continue
        kind = event.get("kind")
        if kind == "stop":
            return
        if kind == "log":
            log_message(event["message"], level=int(event["level"]))
            continue

        package_name = event.get("package_name")
        if not package_name:
            continue
        bar = repo_bars[package_name]
        if kind == "repo_start":
            bar.reset(total=max(int(event.get("total", 1)), 1))
            bar.set_description_str(f"{package_name} [{event.get('phase', 'mining')}]")
            bar.set_postfix_str(str(event.get("status", "")), refresh=False)
            bar.refresh()
        elif kind == "repo_phase":
            bar.set_description_str(f"{package_name} [{event.get('phase', 'working')}]")
            bar.refresh()
        elif kind == "repo_status":
            bar.set_postfix_str(str(event.get("status", "")), refresh=False)
            bar.refresh()
        elif kind == "repo_total":
            bar.total = max(bar.total + int(event.get("amount", 0)), bar.n, 1)
        elif kind == "repo_advance":
            bar.update(int(event.get("amount", 0)))
        elif kind == "repo_done":
            if bar.n < bar.total:
                bar.update(bar.total - bar.n)
            bar.set_description_str(f"{package_name} [done]")
            bar.set_postfix_str("done", refresh=False)
            bar.refresh()
            bar.display()