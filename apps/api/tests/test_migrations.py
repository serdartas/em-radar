from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect

from em_radar_api.db import DATABASE_PATH_ENV, create_db_engine

EXPECTED_TABLES = {
    "alembic_version",
    "board",
    "comment",
    "evaluation_window",
    "merge_request",
    "project",
    "report",
    "repository",
    "review",
    "signal_config",
    "signal_finding",
    "signal_pack_history",
    "source_connection",
    "sprint",
    "team_profile",
    "transition",
    "user",
    "work_item",
    "work_item_link",
}
REPO_ROOT = Path(__file__).parents[3]


def test_baseline_migration_round_trips_and_matches_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "migration.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    config = Config(REPO_ROOT / "alembic.ini")

    command.upgrade(config, "head")
    assert set(inspect(create_db_engine(database_path)).get_table_names()) == EXPECTED_TABLES

    command.downgrade(config, "base")
    assert inspect(create_db_engine(database_path)).get_table_names() == ["alembic_version"]

    command.upgrade(config, "head")
    command.check(config)
