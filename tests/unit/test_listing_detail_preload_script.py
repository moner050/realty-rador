from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.crawl_job_service import JOB_FAILED, JOB_SUCCESS
from realty_radar.infrastructure.database.models import Base, CrawlJob


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    workspace = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "scripts/enrich_listing_details.py", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
    )


def _script_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "enrich_listing_details.py"
    spec = importlib.util.spec_from_file_location("enrich_listing_details_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _crawl_job(job_id: int, status: int) -> CrawlJob:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return CrawlJob(
        job_id=job_id,
        dedupe_key=f"detail-preload:{job_id}",
        status=status,
        scope_level=3,
        scope_code=1150010200,
        available_at=now,
        created_at=now,
        updated_at=now,
    )


def _run_main(monkeypatch, module, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["enrich_listing_details.py", *args])
    module.main()


def test_detail_preload_script_requires_an_explicit_job_id():
    result = _run_script("--help")

    assert result.returncode == 0
    assert "--job-id" in result.stdout
    assert "--max-batches" in result.stdout


def test_detail_preload_script_rejects_out_of_range_bounds():
    result = _run_script("--job-id", "0")

    assert result.returncode != 0
    assert "--job-id must be positive" in result.stderr


@pytest.mark.parametrize("status", [None, JOB_FAILED])
def test_detail_preload_script_rejects_missing_or_non_successful_job_before_enrichment(monkeypatch, capsys, status):
    module = _script_module()
    factory = _session_factory()
    if status is not None:
        with factory() as session:
            session.add(_crawl_job(7, status))
            session.commit()
    invoked = False

    async def enrich(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        return 1

    monkeypatch.setattr(module, "SessionFactory", factory)
    monkeypatch.setattr(module, "run_site_a_mortgage_enrichment", enrich)

    with pytest.raises(SystemExit) as error:
        _run_main(monkeypatch, module, "--job-id", "7")

    assert error.value.code == 2
    assert "--job-id must reference a successful crawl job" in capsys.readouterr().err
    assert invoked is False


def test_detail_preload_script_runs_only_for_a_successful_job(monkeypatch, capsys):
    module = _script_module()
    factory = _session_factory()
    with factory() as session:
        session.add(_crawl_job(7, JOB_SUCCESS))
        session.commit()
    observed = {}

    async def enrich(*args, **kwargs):
        observed.update(args=args, kwargs=kwargs)
        return 3

    monkeypatch.setattr(module, "SessionFactory", factory)
    monkeypatch.setattr(module, "run_site_a_mortgage_enrichment", enrich)

    _run_main(monkeypatch, module, "--job-id", "7")

    assert observed["args"] == (factory,)
    assert observed["kwargs"] == {"job_id": 7, "batch_size": 100, "max_batches": 50, "concurrency": 2}
    assert capsys.readouterr().out == "checked=3\n"
