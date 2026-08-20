# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_api.signal_config_groups import SignalConfigGroupTable
from em_radar_api.signal_pack_import import apply_signal_pack_import
from em_radar_api.tables import ReportJobTable

DEFAULT_PACK_PATH = (
    Path(__file__).parents[4] / "packages" / "config" / "defaults" / "default-pack.yaml"
)
DEFAULT_GROUP_NAME = "Default signals"


def recover_interrupted_jobs(app_session_factory: sessionmaker[Session]) -> None:
    """Mark any queued/running jobs from a previous server run as failed.

    On restart those jobs will never complete, so the frontend would poll them forever.
    """
    with app_session_factory() as session:
        stuck = session.exec(
            select(ReportJobTable).where(ReportJobTable.status.in_(["queued", "running"]))  # type: ignore[union-attr]
        ).all()
        if not stuck:
            return
        now = datetime.now(timezone.utc)
        for job in stuck:
            job.status = "failed"
            job.error = "Interrupted: server restarted"
            job.finished_at = now
            session.add(job)
        session.commit()


def seed_default_signal_group(app_session_factory: sessionmaker[Session]) -> None:
    """Seed the default signal group from the bundled declarative default pack YAML.

    Idempotent: if the default group already exists, the function returns immediately.
    """
    with app_session_factory() as session:
        if (
            session.exec(
                select(SignalConfigGroupTable).where(
                    SignalConfigGroupTable.name == DEFAULT_GROUP_NAME
                )
            ).first()
            is not None
        ):
            return
        apply_signal_pack_import(
            session, DEFAULT_PACK_PATH.read_text(encoding="utf-8"), conflict="skip"
        )
