"""Read-only HTTP benchmark for listing search endpoints."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class BenchmarkMode:
    name: str
    path: str
    route_path: str
    default_p95_ms: float
    item_marker: bytes
    mode_marker: bytes
    forbidden_marker: bytes | None = None
    expected_items: int = 20


@dataclass(frozen=True)
class BenchmarkResult:
    mode: BenchmarkMode
    durations_ms: tuple[float, ...]
    status_codes: tuple[int, ...]
    response_bytes: tuple[int, ...]
    item_counts: tuple[int, ...]
    mode_marker_counts: tuple[int, ...]
    forbidden_counts: tuple[int, ...]
    error_type: str | None = None

    @property
    def p50_ms(self) -> float:
        return _percentile(self.durations_ms, 0.50)

    @property
    def p95_ms(self) -> float:
        return _percentile(self.durations_ms, 0.95)


MODE_NAMES = ("normal", "grouped", "eligible-loans", "purchase-affordable", "complex-detail")
_SEARCH_ROUTE = "/listings/search"
_COMPLEX_ROUTE = "/listings/complex/{complex_id}"
_HTMX_HEADERS = {"HX-Request": "true"}
_GROUPED_MAX_RESPONSE_BYTES = 1_000_000
_DEFAULT_MIN_ACTIVE_LISTINGS = 500_000


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return value


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def _positive_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a finite value greater than zero")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        action="append",
        choices=("all", *MODE_NAMES),
        help="mode to measure; repeat for multiple modes (default: all)",
    )
    parser.add_argument(
        "--warmup",
        type=_non_negative_int,
        default=2,
        help="warm-up GET requests per mode (default: 2)",
    )
    parser.add_argument(
        "--runs",
        type=_positive_int,
        default=30,
        help="measured GET requests per mode (default: 30)",
    )
    parser.add_argument(
        "--fail-p95-ms",
        type=_positive_float,
        help="override the p95 failure threshold for every mode",
    )
    parser.add_argument(
        "--complex-id",
        type=_positive_int,
        help="complex id used by the complex-detail benchmark",
    )
    parser.add_argument(
        "--min-active-listings",
        type=_non_negative_int,
        default=_DEFAULT_MIN_ACTIVE_LISTINGS,
        help=f"minimum active listing cardinality required before measuring (default: {_DEFAULT_MIN_ACTIVE_LISTINGS})",
    )
    options = parser.parse_args(argv)
    options.mode = options.mode or ["all"]
    return options


def _mode_specs(complex_id: int | None) -> dict[str, BenchmarkMode]:
    return {
        "normal": BenchmarkMode(
            name="normal",
            path=f"{_SEARCH_ROUTE}?page_size=20&sort_by=price_asc",
            route_path=_SEARCH_ROUTE,
            default_p95_ms=500.0,
            item_marker=b"data-listing-card",
            mode_marker=b'data-search-mode="normal"',
        ),
        "grouped": BenchmarkMode(
            name="grouped",
            path=f"{_SEARCH_ROUTE}?page_size=20&sort_by=price_asc&group_by_complex=true",
            route_path=_SEARCH_ROUTE,
            default_p95_ms=1_000.0,
            item_marker=b"data-complex-group",
            mode_marker=b'data-search-mode="grouped"',
            forbidden_marker=b"data-listing-card",
        ),
        "eligible-loans": BenchmarkMode(
            name="eligible-loans",
            path=f"{_SEARCH_ROUTE}?page_size=20&sort_by=price_asc&only_eligible_loans=true",
            route_path=_SEARCH_ROUTE,
            default_p95_ms=1_000.0,
            item_marker=b"data-listing-card",
            mode_marker=b'data-search-mode="eligible-loans"',
        ),
        "purchase-affordable": BenchmarkMode(
            name="purchase-affordable",
            path=f"{_SEARCH_ROUTE}?page_size=20&sort_by=price_asc&only_purchase_affordable=true",
            route_path=_SEARCH_ROUTE,
            default_p95_ms=1_000.0,
            item_marker=b"data-listing-card",
            mode_marker=b'data-search-mode="purchase-affordable"',
        ),
        "complex-detail": BenchmarkMode(
            name="complex-detail",
            path=f"/listings/complex/{complex_id}?page_size=20&sort_by=price_asc",
            route_path=_COMPLEX_ROUTE,
            default_p95_ms=500.0,
            item_marker=b"data-listing-card",
            mode_marker=b'data-search-mode="complex-detail"',
        ),
    }


def _selected_mode_names(raw_modes: list[str]) -> tuple[str, ...]:
    if "all" in raw_modes:
        return MODE_NAMES
    return tuple(dict.fromkeys(raw_modes))


def _percentile(values: tuple[float, ...] | tuple[int, ...], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return float(ordered[index])


def _measure_mode(
    client,
    mode: BenchmarkMode,
    *,
    warmup: int,
    runs: int,
    timer: Callable[[], float],
) -> BenchmarkResult:
    try:
        for _ in range(warmup):
            client.get(mode.path, headers=_HTMX_HEADERS)

        durations_ms: list[float] = []
        status_codes: list[int] = []
        response_bytes: list[int] = []
        item_counts: list[int] = []
        mode_marker_counts: list[int] = []
        forbidden_counts: list[int] = []
        for _ in range(runs):
            started_at = timer()
            response = client.get(mode.path, headers=_HTMX_HEADERS)
            durations_ms.append((timer() - started_at) * 1_000)
            status_codes.append(int(response.status_code))
            response_bytes.append(len(response.content))
            item_counts.append(response.content.count(mode.item_marker))
            mode_marker_counts.append(response.content.count(mode.mode_marker))
            forbidden_counts.append(
                response.content.count(mode.forbidden_marker)
                if mode.forbidden_marker is not None
                else 0
            )
    except Exception as exc:
        return BenchmarkResult(
            mode,
            (),
            (),
            (),
            (),
            (),
            (),
            error_type=type(exc).__name__,
        )

    return BenchmarkResult(
        mode,
        tuple(durations_ms),
        tuple(status_codes),
        tuple(response_bytes),
        tuple(item_counts),
        tuple(mode_marker_counts),
        tuple(forbidden_counts),
    )


def _status_summary(status_codes: tuple[int, ...]) -> str:
    counts = Counter(status_codes)
    return ",".join(f"{status}:{counts[status]}" for status in sorted(counts))


def _print_result(
    result: BenchmarkResult,
    *,
    threshold_ms: float,
    stream: TextIO,
) -> int:
    if result.error_type is not None:
        print(f"[ERROR] {result.mode.name} request_error={result.error_type}", file=stream)
        return 2

    statuses_ok = all(200 <= status < 300 for status in result.status_codes)
    latency_ok = result.p95_ms <= threshold_ms
    response_bytes_max = max(result.response_bytes)
    item_count_min = min(result.item_counts)
    item_count_max = max(result.item_counts)
    mode_marker_min = min(result.mode_marker_counts)
    workload_ok = (
        item_count_min == result.mode.expected_items
        and item_count_max == result.mode.expected_items
        and mode_marker_min >= 1
        and max(result.forbidden_counts) == 0
    )
    bytes_target = _GROUPED_MAX_RESPONSE_BYTES if result.mode.name == "grouped" else None
    response_size_ok = bytes_target is None or response_bytes_max <= bytes_target
    outcome = (
        "PASS"
        if statuses_ok and latency_ok and response_size_ok and workload_ok
        else "FAIL"
    )
    response_size_summary = (
        f"bytes_p50={int(_percentile(result.response_bytes, 0.50))} bytes_max={response_bytes_max}"
    )
    if bytes_target is not None:
        response_size_summary += f" bytes_target={bytes_target}"
    print(
        f"[{outcome}] {result.mode.name} "
        f"p50_ms={result.p50_ms:.2f} p95_ms={result.p95_ms:.2f} target_ms={threshold_ms:.2f} "
        f"status={_status_summary(result.status_codes)} "
        f"items_min={item_count_min} items_max={item_count_max} "
        f"items_target={result.mode.expected_items} "
        f"mode_marker_min={mode_marker_min} "
        f"{response_size_summary}",
        file=stream,
    )
    return 0 if outcome == "PASS" else 1


def run_benchmarks(
    options: argparse.Namespace,
    client,
    *,
    route_paths: set[str],
    active_listing_count: int,
    complex_listing_count: int | None,
    timer: Callable[[], float] = time.perf_counter,
    stream: TextIO = sys.stdout,
) -> int:
    modes = _mode_specs(options.complex_id)
    selected_mode_names = _selected_mode_names(options.mode)
    if active_listing_count < options.min_active_listings:
        print(
            f"[ERROR] preflight active_listings={active_listing_count} "
            f"required={options.min_active_listings}",
            file=stream,
        )
        return 2
    for mode_name in selected_mode_names:
        mode = modes[mode_name]
        if mode.name == "complex-detail" and options.complex_id is None:
            print("[ERROR] complex-detail requires --complex-id", file=stream)
            return 2
        if mode.route_path not in route_paths:
            print(f"[ERROR] {mode.name} unsupported route={mode.route_path}", file=stream)
            return 2
    if "complex-detail" in selected_mode_names:
        if complex_listing_count is None or complex_listing_count < 20:
            print(
                f"[ERROR] preflight complex_id={options.complex_id} "
                f"active_listings={complex_listing_count or 0} required=20",
                file=stream,
            )
            return 2

    exit_code = 0
    measured_count = 0
    for mode_name in selected_mode_names:
        mode = modes[mode_name]
        result = _measure_mode(
            client,
            mode,
            warmup=options.warmup,
            runs=options.runs,
            timer=timer,
        )
        measured_count += 1
        threshold_ms = options.fail_p95_ms or mode.default_p95_ms
        exit_code = max(exit_code, _print_result(result, threshold_ms=threshold_ms, stream=stream))
    if measured_count != len(selected_mode_names):
        print(
            f"[ERROR] measured_modes={measured_count} requested_modes={len(selected_mode_names)}",
            file=stream,
        )
        return 2
    return exit_code


def _load_runtime(options: argparse.Namespace):
    repository_root = Path(__file__).resolve().parents[1]
    source_root = repository_root / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

    from fastapi.testclient import TestClient
    from sqlalchemy import text as sql_text

    from realty_radar.infrastructure.database.engine import engine
    from realty_radar.domain.loan.entities import ApplicantProfile
    from realty_radar.web.main import app
    from realty_radar.web.routes.settings import GUEST_COOKIE_NAME

    if engine.dialect.name != "mysql":
        raise RuntimeError("listing search benchmark requires MySQL")
    with engine.connect() as connection:
        active_listing_count = int(
            connection.scalar(
                sql_text(
                    "SELECT COUNT(*) FROM listing_current "
                    "WHERE lifecycle = 1 AND is_short_term = FALSE"
                )
            )
            or 0
        )
        complex_listing_count = None
        if options.complex_id is not None:
            complex_listing_count = int(
                connection.scalar(
                    sql_text(
                        "SELECT COUNT(*) FROM listing_current "
                        "WHERE lifecycle = 1 AND is_short_term = FALSE "
                        "AND complex_id = :complex_id"
                    ),
                    {"complex_id": options.complex_id},
                )
                or 0
            )
    client = TestClient(app, raise_server_exceptions=False)
    benchmark_profile = ApplicantProfile(
        available_cash=3_000_000_000,
        max_monthly_housing_cost=100_000_000,
    )
    client.cookies.set(
        GUEST_COOKIE_NAME,
        urllib.parse.quote(json.dumps(benchmark_profile.to_dict(), ensure_ascii=False)),
    )
    return app, client, active_listing_count, complex_listing_count


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        app, client, active_listing_count, complex_listing_count = _load_runtime(options)
        route_paths = {route.path for route in app.routes if hasattr(route, "path")}
        with client:
            return run_benchmarks(
                options,
                client,
                route_paths=route_paths,
                active_listing_count=active_listing_count,
                complex_listing_count=complex_listing_count,
            )
    except Exception as exc:
        print(f"[ERROR] benchmark_setup error_type={type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
