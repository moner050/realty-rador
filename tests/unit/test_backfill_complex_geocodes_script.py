from pathlib import Path
import subprocess
import sys


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
