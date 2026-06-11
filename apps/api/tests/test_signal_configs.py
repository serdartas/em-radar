import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel, Session

from em_radar_api.db import create_db_engine
from em_radar_api.repositories.signal_configs import (
    list_signal_configs,
    reset_all_signal_configs,
    reset_signal_config,
    upsert_signal_config,
)
from em_radar_api.signal_configs import SignalConfigUpsert
from em_radar_core.models import Severity

SIGNAL_ID = "stale-in-progress-work-item"


def test_signal_config_upsert_and_reset_to_catalog_defaults() -> None:
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        created = upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id=SIGNAL_ID,
                enabled=False,
                severity_override=Severity.CRITICAL,
                params={"days_threshold": 2, "exclude_labels": ["parked"]},
                scope={"project_keys": ["RAD"]},
            ),
        )

        assert list_signal_configs(session) == [created]

        updated = upsert_signal_config(
            session,
            SignalConfigUpsert(signal_id=SIGNAL_ID, params={"days_threshold": 3}),
        )
        assert updated.id == created.id
        assert updated.params == {"days_threshold": 3, "exclude_labels": []}
        assert list_signal_configs(session) == [updated]

        reset = reset_signal_config(session, SIGNAL_ID)
        assert reset.id == created.id
        assert reset.enabled
        assert reset.severity_override is None
        assert reset.params == {"days_threshold": 7, "exclude_labels": []}
        assert reset.scope == {}


def test_reset_all_restores_defaults_without_seeding_missing_rows() -> None:
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(signal_id=SIGNAL_ID, enabled=False, params={"days_threshold": 1}),
        )

        reset = reset_all_signal_configs(session)

        assert len(reset) == 1
        assert reset[0].enabled
        assert reset[0].params == {"days_threshold": 7, "exclude_labels": []}


def test_unknown_signal_id_is_rejected() -> None:
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        with pytest.raises(ValueError, match="unknown signal id: unknown-signal"):
            upsert_signal_config(session, SignalConfigUpsert(signal_id="unknown-signal"))
        with pytest.raises(ValueError, match="unknown signal id: unknown-signal"):
            reset_signal_config(session, "unknown-signal")


@pytest.mark.parametrize(
    "params",
    [
        {"days_threshold": -1},
        {"unknown": True},
    ],
)
def test_invalid_signal_params_are_rejected_before_persisting(
    params: dict[str, object],
) -> None:
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        with pytest.raises(ValidationError):
            upsert_signal_config(session, SignalConfigUpsert(signal_id=SIGNAL_ID, params=params))

        assert list_signal_configs(session) == []
