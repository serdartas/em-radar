import os
from collections.abc import Iterator
from pathlib import Path
from threading import Lock

from sqlalchemy import Engine, event
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine

DEFAULT_DATABASE_PATH = Path("/data/em-radar.db")
DATABASE_PATH_ENV = "EM_RADAR_DATABASE_PATH"
schema_version = 1

_write_lock = Lock()


def create_db_engine(database_path: str | Path | None = None) -> Engine:
    path = Path(database_path or os.environ.get(DATABASE_PATH_ENV, DEFAULT_DATABASE_PATH))
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _set_sqlite_pragmas(dbapi_connection: object, connection_record: object) -> None:
    del connection_record
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


engine = create_db_engine()
session_factory = create_session_factory(engine)


def get_session() -> Iterator[Session]:
    with session_factory() as session:
        yield session


def get_write_session() -> Iterator[Session]:
    with _write_lock, session_factory() as session:
        yield session
