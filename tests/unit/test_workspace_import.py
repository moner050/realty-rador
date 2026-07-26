from pathlib import Path

import realty_radar


def test_tests_import_the_package_from_this_worktree():
    repository_root = Path(__file__).resolve().parents[2]
    assert Path(realty_radar.__file__).resolve().is_relative_to(repository_root / "src")
