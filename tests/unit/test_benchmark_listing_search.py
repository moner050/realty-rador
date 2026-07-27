import io
import subprocess
import sys
from pathlib import Path

from scripts import benchmark_listing_search as benchmark


_LISTING_CARDS = b'<article data-listing-card></article>' * 20
_NORMAL_BODY = b'<div data-search-mode="normal">' + _LISTING_CARDS
_ELIGIBLE_BODY = b'<div data-search-mode="eligible-loans">' + _LISTING_CARDS
_COMPLEX_BODY = b'<template data-search-mode="complex-detail">' + _LISTING_CARDS
_GROUPED_BODY = (
    b'<div data-search-mode="grouped">'
    + b'<details data-complex-group></details>' * 20
)


class _Response:
    def __init__(self, status_code: int = 200, content: bytes = _NORMAL_BODY):
        self.status_code = status_code
        self.content = content


class _GetOnlyClient:
    def __init__(
        self,
        *,
        response: _Response | None = None,
        error: Exception | None = None,
    ):
        self.response = response
        self.error = error
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, *, headers: dict[str, str]):
        self.requests.append((path, headers))
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        if "group_by_complex=true" in path:
            return _Response(content=_GROUPED_BODY)
        if "only_eligible_loans=true" in path:
            return _Response(content=_ELIGIBLE_BODY)
        if path.startswith("/listings/complex/"):
            return _Response(content=_COMPLEX_BODY)
        return _Response()


class _StepClock:
    def __init__(self, step_seconds: float):
        self._step_seconds = step_seconds
        self._value = 0.0

    def __call__(self) -> float:
        self._value += self._step_seconds
        return self._value


def _run_benchmarks(options, client, **kwargs):
    return benchmark.run_benchmarks(
        options,
        client,
        active_listing_count=656_875,
        complex_listing_count=40,
        **kwargs,
    )


def test_cli_help_documents_benchmark_controls():
    repository_root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        [sys.executable, "scripts/benchmark_listing_search.py", "--help"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--warmup" in completed.stdout
    assert "--runs" in completed.stdout
    assert "--fail-p95-ms" in completed.stdout
    assert "--complex-id" in completed.stdout
    assert "--min-active-listings" in completed.stdout


def test_default_options_use_two_warmups_and_thirty_measurements():
    options = benchmark.parse_args([])

    assert options.warmup == 2
    assert options.runs == 30
    assert options.mode == ["all"]


def test_all_modes_measure_supported_searches_with_full_result_markers():
    options = benchmark.parse_args(
        ["--warmup", "2", "--runs", "3", "--complex-id", "51"]
    )
    client = _GetOnlyClient()
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        client,
        route_paths={"/listings/search", "/listings/complex/{complex_id}"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 0
    assert len(client.requests) == 20
    assert all(headers == {"HX-Request": "true"} for _, headers in client.requests)
    assert "[PASS] normal" in output.getvalue()
    assert "[PASS] grouped" in output.getvalue()
    assert "[PASS] eligible-loans" in output.getvalue()
    assert "[PASS] complex-detail" in output.getvalue()
    assert "p50_ms=10.00 p95_ms=10.00" in output.getvalue()
    assert "items_min=20" in output.getvalue()


def test_explicit_mode_fails_when_route_is_unavailable():
    options = benchmark.parse_args(
        ["--mode", "complex-detail", "--complex-id", "51"]
    )
    client = _GetOnlyClient()
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        client,
        route_paths={"/listings/search"},
        stream=output,
    )

    assert exit_code == 2
    assert client.requests == []
    assert "[ERROR] complex-detail unsupported route=/listings/complex/{complex_id}" in output.getvalue()


def test_complex_detail_mode_fails_when_complex_id_is_missing():
    options = benchmark.parse_args(["--mode", "complex-detail"])
    client = _GetOnlyClient()
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        client,
        route_paths={"/listings/complex/{complex_id}"},
        stream=output,
    )

    assert exit_code == 2
    assert client.requests == []
    assert "[ERROR] complex-detail requires --complex-id" in output.getvalue()


def test_complex_detail_runs_when_route_and_complex_id_are_available():
    options = benchmark.parse_args(
        ["--mode", "complex-detail", "--warmup", "0", "--runs", "1", "--complex-id", "51"]
    )
    client = _GetOnlyClient()
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        client,
        route_paths={"/listings/complex/{complex_id}"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 0
    assert client.requests == [
        (
            "/listings/complex/51?page_size=20&sort_by=price_asc",
            {"HX-Request": "true"},
        )
    ]
    assert "[PASS] complex-detail" in output.getvalue()


def test_threshold_override_returns_nonzero_when_p95_is_too_slow():
    options = benchmark.parse_args(
        ["--mode", "normal", "--warmup", "0", "--runs", "2", "--fail-p95-ms", "5"]
    )
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 1
    assert "[FAIL] normal" in output.getvalue()
    assert "p95_ms=10.00 target_ms=5.00" in output.getvalue()


def test_default_targets_are_500ms_for_normal_and_1000ms_for_grouped():
    normal_output = io.StringIO()
    normal_code = _run_benchmarks(
        benchmark.parse_args(["--mode", "normal", "--warmup", "0", "--runs", "1"]),
        _GetOnlyClient(),
        route_paths={"/listings/search"},
        timer=_StepClock(0.6),
        stream=normal_output,
    )
    grouped_output = io.StringIO()
    grouped_code = _run_benchmarks(
        benchmark.parse_args(["--mode", "grouped", "--warmup", "0", "--runs", "1"]),
        _GetOnlyClient(),
        route_paths={"/listings/search"},
        timer=_StepClock(0.6),
        stream=grouped_output,
    )

    assert normal_code == 1
    assert "target_ms=500.00" in normal_output.getvalue()
    assert grouped_code == 0
    assert "target_ms=1000.00" in grouped_output.getvalue()


def test_non_success_http_status_returns_nonzero():
    options = benchmark.parse_args(["--mode", "normal", "--warmup", "0", "--runs", "1"])
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(response=_Response(status_code=500)),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 1
    assert "[FAIL] normal" in output.getvalue()
    assert "status=500:1" in output.getvalue()


def test_grouped_response_larger_than_one_megabyte_returns_nonzero():
    options = benchmark.parse_args(["--mode", "grouped", "--warmup", "0", "--runs", "1"])
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(response=_Response(content=b"x" * 1_000_001)),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 1
    assert "[FAIL] grouped" in output.getvalue()
    assert "bytes_max=1000001 bytes_target=1000000" in output.getvalue()


def test_non_grouped_response_size_does_not_fail_the_benchmark():
    options = benchmark.parse_args(["--mode", "normal", "--warmup", "0", "--runs", "1"])
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(response=_Response(content=_NORMAL_BODY + b"x" * 1_000_001)),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 0
    assert "[PASS] normal" in output.getvalue()
    assert "bytes_target" not in output.getvalue()


def test_request_error_does_not_print_database_credentials():
    options = benchmark.parse_args(["--mode", "normal", "--warmup", "0", "--runs", "1"])
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(error=RuntimeError("mysql+pymysql://user:super-secret@db.example/test")),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 2
    assert "[ERROR] normal request_error=RuntimeError" in output.getvalue()
    assert "super-secret" not in output.getvalue()


def test_fast_but_empty_success_response_fails_workload_validation():
    options = benchmark.parse_args(["--mode", "normal", "--warmup", "0", "--runs", "1"])
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(response=_Response(content=b"data")),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 1
    assert "[FAIL] normal" in output.getvalue()
    assert "items_min=0 items_max=0 items_target=20" in output.getvalue()


def test_overfull_grouped_response_fails_twenty_item_contract():
    options = benchmark.parse_args(
        ["--mode", "grouped", "--warmup", "0", "--runs", "1"]
    )
    output = io.StringIO()
    body = (
        b'<div data-search-mode="grouped">'
        + b'<details data-complex-group></details>' * 21
    )

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(response=_Response(content=body)),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 1
    assert "[FAIL] grouped" in output.getvalue()
    assert "items_min=21 items_max=21 items_target=20" in output.getvalue()


def test_wrong_mode_success_response_fails_response_marker_validation():
    options = benchmark.parse_args(
        ["--mode", "eligible-loans", "--warmup", "0", "--runs", "1"]
    )
    output = io.StringIO()

    exit_code = _run_benchmarks(
        options,
        _GetOnlyClient(response=_Response(content=_NORMAL_BODY)),
        route_paths={"/listings/search"},
        timer=_StepClock(0.01),
        stream=output,
    )

    assert exit_code == 1
    assert "[FAIL] eligible-loans" in output.getvalue()
    assert "mode_marker_min=0" in output.getvalue()


def test_preflight_fails_when_dataset_is_smaller_than_requested_cardinality():
    options = benchmark.parse_args(
        ["--mode", "normal", "--min-active-listings", "500000"]
    )
    client = _GetOnlyClient()
    output = io.StringIO()

    exit_code = benchmark.run_benchmarks(
        options,
        client,
        route_paths={"/listings/search"},
        active_listing_count=12,
        complex_listing_count=None,
        stream=output,
    )

    assert exit_code == 2
    assert client.requests == []
    assert "[ERROR] preflight active_listings=12 required=500000" in output.getvalue()


def test_complex_preflight_requires_a_full_twenty_listing_page():
    options = benchmark.parse_args(
        ["--mode", "complex-detail", "--complex-id", "51"]
    )
    client = _GetOnlyClient()
    output = io.StringIO()

    exit_code = benchmark.run_benchmarks(
        options,
        client,
        route_paths={"/listings/complex/{complex_id}"},
        active_listing_count=656_875,
        complex_listing_count=19,
        stream=output,
    )

    assert exit_code == 2
    assert client.requests == []
    assert "[ERROR] preflight complex_id=51 active_listings=19 required=20" in output.getvalue()
