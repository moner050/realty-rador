import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


def test_backfill_command_exposes_an_explicit_batch_size_flag():
    workspace = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "scripts/backfill_complex_geocodes.py", "--help"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--batch-size" in result.stdout
    assert "--complex-id" in result.stdout


def test_backfill_command_exposes_sweep_limits():
    workspace = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "scripts/backfill_complex_geocodes.py", "--help"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--max-batches" in result.stdout
    assert "--max-requests" in result.stdout


def _load_backfill_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "backfill_complex_geocodes.py"
    specification = importlib.util.spec_from_file_location("backfill_complex_geocodes_script", script_path)
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    specification.loader.exec_module(module)
    return module


def test_backfill_command_uses_default_sweep_limits_and_prints_aggregate_stats(monkeypatch, capsys):
    script = _load_backfill_script()
    observed = {}

    def run_sweep(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return SimpleNamespace(
            batch_count=1,
            selected_count=2,
            external_request_count=1,
            reused_count=1,
            ok_count=2,
            not_found_count=0,
            failed_count=0,
        )

    monkeypatch.setattr(script, "run_geocode_sweep", run_sweep)
    monkeypatch.setattr(script, "NaverGeocoder", lambda: "geocoder")
    monkeypatch.setattr(script.sys, "argv", ["backfill_complex_geocodes.py"])

    script.main()

    assert observed["args"] == (script.SessionLocal, "geocoder")
    assert observed["kwargs"]["batch_size"] == 100
    assert observed["kwargs"]["max_batches"] == 1
    assert observed["kwargs"]["max_requests"] == 15000
    output = capsys.readouterr().out
    assert "batch_count=1" in output
    assert "selected_count=2" in output
