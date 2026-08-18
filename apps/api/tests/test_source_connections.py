import pytest
from pydantic import SecretStr
from sqlmodel import SQLModel, Session, select

from em_radar_api.db import create_db_engine
from em_radar_api.repositories.scope_definitions import create_scope_definition
from em_radar_api.repositories.source_connections import (
    SourceConnectionInUse,
    create_source_connection,
    delete_source_connection,
    get_source_connection,
    instantiate_connector,
    list_source_connections,
    update_source_connection,
)
from em_radar_api.repositories.team_profiles import create_team_profile
from em_radar_api.scope_definitions import ScopeDefinitionCreate, ScopeType
from em_radar_api.source_connections import (
    ConnectorName,
    SourceConnectionCreate,
    SourceConnectionTable,
    SourceConnectionUpdate,
)
from em_radar_api.team_profiles import TeamProfileCreate


class RecordingConnector:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config


def test_source_connection_crud_masks_credentials_but_instantiates_with_raw_config() -> None:
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        created = create_source_connection(
            session,
            SourceConnectionCreate(
                name="Jira prod",
                connector_name=ConnectorName.JIRA,
                config={
                    "base_url": "https://jira.example.com",
                    "token": "jira-token-12345678",
                    "nested": {"api_key": "abc"},
                    "credential_from_type": SecretStr("xyz"),
                },
            ),
        )

        assert created.name == "Jira prod"
        assert created.config == {
            "base_url": "https://jira.example.com",
            "token": "****5678",
            "nested": {"api_key": "****"},
            "credential_from_type": "****",
        }
        assert get_source_connection(session, created.id) == created
        assert list_source_connections(session) == [created]

        connector = instantiate_connector(session, created.id, RecordingConnector)
        assert connector is not None
        assert connector.config["token"] == "jira-token-12345678"
        assert connector.config["credential_from_type"] == "xyz"

        stored = session.exec(select(SourceConnectionTable)).one()
        assert stored.config["token"] == "jira-token-12345678"

        updated = update_source_connection(
            session,
            created.id,
            SourceConnectionUpdate(
                connector_name=ConnectorName.GITLAB,
                config={"password": "new-password-abcdefgh"},
            ),
        )
        assert updated is not None
        assert updated.connector_name is ConnectorName.GITLAB
        assert updated.config == {"password": "****efgh"}

        assert delete_source_connection(session, created.id)
        assert get_source_connection(session, created.id) is None
        assert not delete_source_connection(session, created.id)
        assert instantiate_connector(session, created.id, RecordingConnector) is None


def test_masked_credential_is_not_written_back_on_patch() -> None:
    """AUDIT-4 regression: PATCH with a round-tripped masked token must not overwrite the real secret."""
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    real_token = "jira-real-secret-token-abcd"

    with Session(engine) as session:
        created = create_source_connection(
            session,
            SourceConnectionCreate(
                name="Jira test",
                connector_name=ConnectorName.JIRA,
                config={"base_url": "https://jira.example.com", "token": real_token},
            ),
        )
        # GET returns masked token
        read_back = get_source_connection(session, created.id)
        assert read_back is not None
        masked_token = read_back.config["token"]
        assert isinstance(masked_token, str) and masked_token.startswith("****")

        # PATCH with masked token + a non-secret change — real token must be preserved
        updated = update_source_connection(
            session,
            created.id,
            SourceConnectionUpdate(
                config={"base_url": "https://jira-new.example.com", "token": masked_token}
            ),
        )
        assert updated is not None
        assert updated.config["base_url"] == "https://jira-new.example.com"

        stored = session.exec(select(SourceConnectionTable)).one()
        assert stored.config["token"] == real_token, (
            "masked sentinel must not overwrite real secret"
        )

        # PATCH with a genuinely new token — must be stored as the new value
        new_token = "brand-new-token-wxyz"
        updated2 = update_source_connection(
            session,
            created.id,
            SourceConnectionUpdate(config={"token": new_token}),
        )
        assert updated2 is not None
        assert updated2.config["token"].startswith("****")

        session.refresh(stored)
        assert stored.config["token"] == new_token


def test_nested_masked_credential_is_preserved_on_patch() -> None:
    """AUDIT-4: deep-nested masked tokens must not lose the real stored secret on merge."""
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    real_nested_token = "nested-real-token-efgh"

    with Session(engine) as session:
        created = create_source_connection(
            session,
            SourceConnectionCreate(
                name="Jira nested",
                connector_name=ConnectorName.JIRA,
                config={
                    "base_url": "https://jira.example.com",
                    "auth": {"token": real_nested_token, "user": "admin"},
                },
            ),
        )
        read_back = get_source_connection(session, created.id)
        assert read_back is not None
        masked_nested = read_back.config["auth"]
        assert isinstance(masked_nested, dict)
        masked_token_val = masked_nested["token"]
        assert isinstance(masked_token_val, str) and masked_token_val.startswith("****")

        # Round-trip the full config including the masked nested token
        updated = update_source_connection(
            session,
            created.id,
            SourceConnectionUpdate(
                config={
                    "base_url": "https://jira-updated.example.com",
                    "auth": {"token": masked_token_val, "user": "admin"},
                }
            ),
        )
        assert updated is not None
        assert updated.config["base_url"] == "https://jira-updated.example.com"

        stored = session.exec(select(SourceConnectionTable)).one()
        assert stored.config["auth"]["token"] == real_nested_token, (  # type: ignore[index]
            "nested masked sentinel must not overwrite real stored nested secret"
        )


def test_source_connection_referenced_by_team_cannot_be_deleted() -> None:
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(
                name="Jira",
                connector_name=ConnectorName.JIRA,
            ),
        )
        # Create a scope for the connection, then a team whose connection_ids is derived
        # from that scope.  This is the canonical way to reference a connection via a team
        # after connection_ids became server-derived.
        scope = create_scope_definition(
            session,
            ScopeDefinitionCreate(
                connection_id=connection.id,
                name="Board A",
                scope_type=ScopeType.BOARD,
                external_ref={"id": "1"},
                capabilities=[],
            ),
        )
        create_team_profile(
            session,
            TeamProfileCreate(name="Platform", scope_ids=[scope.id]),
        )

        updated = update_source_connection(
            session,
            connection.id,
            SourceConnectionUpdate(config={"base_url": "https://jira.example.com"}),
        )
        assert updated is not None
        assert updated.config == {"base_url": "https://jira.example.com"}

        # The scope (and team) references the connection; deletion is blocked.
        with pytest.raises(SourceConnectionInUse, match="referenced by one or more teams"):
            delete_source_connection(session, connection.id)
        assert get_source_connection(session, connection.id) == updated
