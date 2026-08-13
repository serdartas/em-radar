from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_api.repositories.signal_config_groups import create_signal_config_group
from em_radar_api.repositories.signal_definitions import create_signal_definition
from em_radar_api.signal_config_groups import SignalConfigGroupCreate, SignalConfigGroupTable
from em_radar_api.signal_definitions import SignalDefinitionCreate, SignalDefinitionTable
from em_radar_config import seed_jira_signal_templates

DEFAULT_GROUP_NAME = "Default signals"


def seed_default_signal_group(app_session_factory: sessionmaker[Session]) -> None:
    with app_session_factory() as session:
        existing = session.exec(
            select(SignalConfigGroupTable).where(SignalConfigGroupTable.name == DEFAULT_GROUP_NAME)
        ).first()
        if existing is not None:
            return

        names = set(session.exec(select(SignalDefinitionTable.name)))
        signal_ids = []
        for template in seed_jira_signal_templates():
            if template.name in names:
                row = session.exec(
                    select(SignalDefinitionTable).where(SignalDefinitionTable.name == template.name)
                ).first()
                if row is not None:
                    signal_ids.append(row.id)
                continue
            created = create_signal_definition(
                session,
                SignalDefinitionCreate(
                    name=template.name,
                    description=template.description,
                    entity_type=template.entity_type,
                    expression=template.expression,
                    report_settings=template.report_settings.model_dump(mode="json"),
                    enabled=template.enabled_by_default,
                    origin="system_template",
                    template_key=template.key,
                ),
            )
            names.add(template.name)
            signal_ids.append(created.id)

        create_signal_config_group(
            session,
            SignalConfigGroupCreate(
                name=DEFAULT_GROUP_NAME,
                description="Bundled default signals.",
                signal_ids=signal_ids,
            ),
        )
