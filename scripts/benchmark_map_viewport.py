"""Read-only, bounded performance evidence for the map viewport query."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import event, text


_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from realty_radar.application.listing_map_service import ListingMapService
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.infrastructure.database.session import SessionLocal


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=_positive_int, default=30, help="measured map viewport calls (default: 30)")
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=10,
        help="per-query MySQL execution limit in seconds (default: 10)",
    )
    return parser.parse_args(argv)


def nearest_rank_p95(samples: list[float]) -> float:
    if not samples:
        raise ValueError("at least one sample is required")
    rank = math.ceil(len(samples) * 0.95)
    return sorted(samples)[rank - 1]


def _configure_read_only_timeout(session, timeout_seconds: int) -> None:
    if session.bind is None or session.bind.dialect.name != "mysql":
        raise RuntimeError("map viewport benchmark requires configured MySQL")
    session.execute(text("SET SESSION TRANSACTION READ ONLY"))
    session.execute(text("SET SESSION MAX_EXECUTION_TIME = :timeout_ms"), {"timeout_ms": timeout_seconds * 1000})


def _explain_captured_selects(session, captured: list[tuple[str, Any]]) -> list[object]:
    if not captured:
        raise RuntimeError("map viewport call did not issue a SELECT statement")
    explains: list[object] = []
    connection = session.connection()
    for statement, parameters in captured:
        explained = connection.exec_driver_sql(f"EXPLAIN FORMAT=JSON {statement}", parameters).scalar_one()
        explains.append(json.loads(explained))
    return explains


def _measure_viewport(timeout_seconds: int, *, capture_selects: bool) -> tuple[float, dict[str, int], list[object]]:
    session = SessionLocal()
    captured: list[tuple[str, Any]] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            captured.append((statement, parameters))

    try:
        _configure_read_only_timeout(session, timeout_seconds)
        if capture_selects:
            event.listen(session.bind, "before_cursor_execute", capture)
        try:
            started_at = time.perf_counter()
            viewport = ListingMapService(session).build_viewport(ListingSearchFilter(), None, 7)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
        finally:
            if capture_selects:
                event.remove(session.bind, "before_cursor_execute", capture)
        explains = _explain_captured_selects(session, captured) if capture_selects else []
        return elapsed_ms, {
            "matching_complex_count": viewport.matching_complex_count,
            "mapped_complex_count": viewport.mapped_complex_count,
            "unmapped_complex_count": viewport.unmapped_complex_count,
            "marker_count": len(viewport.markers),
            "cluster_count": len(viewport.clusters),
        }, explains
    finally:
        session.close()


def run_benchmark(runs: int, timeout_seconds: int) -> dict[str, object]:
    _measure_viewport(timeout_seconds, capture_selects=False)

    durations_ms: list[float] = []
    map_counts: dict[str, int] | None = None
    explain: list[object] = []
    for run_index in range(runs):
        elapsed_ms, counts, run_explain = _measure_viewport(
            timeout_seconds,
            capture_selects=run_index == 0,
        )
        durations_ms.append(elapsed_ms)
        if map_counts is None:
            map_counts = counts
            explain = run_explain

    sorted_durations = sorted(durations_ms)
    p50_rank = math.ceil(len(sorted_durations) * 0.50)
    return {
        "status": "ok",
        "runs": runs,
        "latency_ms": {
            "min": sorted_durations[0],
            "p50": sorted_durations[p50_rank - 1],
            "p95": nearest_rank_p95(durations_ms),
            "max": sorted_durations[-1],
        },
        "map_counts": map_counts,
        "explain": explain,
    }


def _error_record(exc: Exception) -> dict[str, str]:
    timeout = "timeout" in f"{type(exc).__name__} {exc}".lower()
    return {
        "status": "error",
        "error_type": type(exc).__name__,
        "error": "database operation timed out" if timeout else "database operation failed",
    }


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        record = run_benchmark(options.runs, options.timeout_seconds)
    except Exception as exc:
        print(json.dumps(_error_record(exc), ensure_ascii=False))
        return 2
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
