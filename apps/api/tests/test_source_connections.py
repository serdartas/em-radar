from uuid import uuid4

from pydantic import SecretStr
from sqlmodel import SQLModel, Session, select

from em_radar_api.db import create_db_engine
from em_radar_api.repositories.source_connections import (
    create_source_connection,
    delete_source_connection,
    get_source_connection,
    instantiate_connector,
    list_source_connections,
    update_source_connection,
)
from em_radar_api.source_connections import (
    ConnectorName,
    SourceConnectionCreate,
    SourceConnectionTable,
    SourceConnectionUpdate,
)


class RecordingConnector:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config


def test_source_connection_crud_masks_credentials_but_instantiates_with_raw_config() -> None:
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)
    project_id = uuid4()
    board_id = uuid4()
    repository_id = uuid4()

    with Session(engine) as session:
        created = create_source_connection(
            session,
            SourceConnectionCreate(
                connector_name=ConnectorName.JIRA,
                config={
                    "base_url": "https://jira.example.com",
                    "token": "jira-token-12345678",
                    "nested": {"api_key": "nested-key-87654321"},
                    "credential_from_type": SecretStr("typed-secret-11223344"),
                },
                selected_project_ids=[project_id],
                selected_board_ids=[board_id],
                selected_repository_ids=[repository_id],
            ),
        )

        assert created.config == {
            "base_url": "https://jira.example.com",
            "token": "****5678",
            "nested": {"api_key": "****4321"},
            "credential_from_type": "****3344",
        }
        assert created.selected_project_ids == [project_id]
        assert get_source_connection(session, created.id) == created
        assert list_source_connections(session) == [created]

        connector = instantiate_connector(session, created.id, RecordingConnector)
        assert connector is not None
        assert connector.config["token"] == "jira-token-12345678"
        assert connector.config["credential_from_type"] == "typed-secret-11223344"

        stored = session.exec(select(SourceConnectionTable)).one()
        assert stored.config["token"] == "jira-token-12345678"

        updated = update_source_connection(
            session,
            created.id,
            SourceConnectionUpdate(
                connector_name=ConnectorName.GITLAB,
                config={"password": "new-password-abcdefgh"},
                selected_project_ids=[],
            ),
        )
        assert updated is not None
        assert updated.connector_name is ConnectorName.GITLAB
        assert updated.config == {"password": "****efgh"}
        assert updated.selected_project_ids == []
        assert updated.selected_board_ids == [board_id]

        assert delete_source_connection(session, created.id)
        assert get_source_connection(session, created.id) is None
        assert not delete_source_connection(session, created.id)
        assert instantiate_connector(session, created.id, RecordingConnector) is None
