from pathlib import Path
import subprocess
import sys


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    workspace = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "scripts/enrich_listing_details.py", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
    )


def test_detail_preload_script_requires_an_explicit_job_id():
    result = _run_script("--help")

    assert result.returncode == 0
    assert "--job-id" in result.stdout
    assert "--max-batches" in result.stdout


def test_detail_preload_script_rejects_out_of_range_bounds():
    result = _run_script("--job-id", "0")

    assert result.returncode != 0
    assert "--job-id must be positive" in result.stderr
