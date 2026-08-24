from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, Session, select

from em_radar_core.models import ReportStatus, WindowType

from em_radar_api.db import create_db_engine, create_session_factory
from em_radar_api.main import create_app
from em_radar_api.signal_definitions import SignalDefinitionTable
from em_radar_api.startup import recover_interrupted_jobs
from em_radar_api.tables import (
    EvaluationWindowTable,
    ReportJobTable,
    ReportTable,
    TeamProfileTable,
)


def test_first_startup_seeds_default_signal_group(tmp_path: Path) -> None:
    """Startup seeds the default signal group with 12 declarative signals (7 WI + 5 MR)."""
    session_factory = _empty_session_factory(tmp_path)

    with TestClient(create_app(app_session_factory=session_factory)):
        pass

    with session_factory() as session:
        count = session.exec(select(SignalDefinitionTable)).all()

    assert len(count) == 12


def test_subsequent_startup_does_not_duplicate_signals(tmp_path: Path) -> None:
    session_factory = _empty_session_factory(tmp_path)
    app = create_app(app_session_factory=session_factory)

    with TestClient(app):
        pass

    with TestClient(app):
        pass

    with session_factory() as session:
        count = session.exec(select(SignalDefinitionTable)).all()

    assert len(count) == 12


def test_recover_interrupted_jobs_reconciles_stuck_reports_and_jobs(tmp_path: Path) -> None:
    """A report/job left non-terminal by a previous run must be marked failed on startup."""
    session_factory = _empty_session_factory(tmp_path)
    now = datetime(2026, 7, 1, tzinfo=timezone.utc).replace(tzinfo=None)

    team = TeamProfileTable(id=uuid4(), name="Recovery team", created_at=now, updated_at=now)
    window = EvaluationWindowTable(
        id=uuid4(),
        window_type=WindowType.DATE_RANGE,
        start=now,
        end=now,
        team_profile_id=team.id,
    )
    running_report = ReportTable(
        id=uuid4(),
        evaluation_window_id=window.id,
        status=ReportStatus.RUNNING,
        started_at=now,
        findings_count_by_severity={},
        signal_pack_snapshot={},
    )
    running_job = ReportJobTable(
        id=uuid4(),
        team_profile_id=team.id,
        status="running",
        enqueued_at=now,
    )
    with session_factory() as session:
        session.add(team)
        session.commit()
        session.add(window)
        session.commit()
        session.add_all([running_report, running_job])
        session.commit()

    recover_interrupted_jobs(session_factory)

    with session_factory() as session:
        report = session.get(ReportTable, running_report.id)
        job = session.get(ReportJobTable, running_job.id)
        assert report is not None and report.status is ReportStatus.FAILED
        assert report.error == "Interrupted: server restarted"
        assert report.finished_at is not None
        assert job is not None and job.status == "failed"


def _empty_session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_db_engine(tmp_path / "startup-test.db")
    SQLModel.metadata.create_all(engine)
    return create_session_factory(engine)
