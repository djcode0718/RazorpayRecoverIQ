from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_engine_url: str | None = None
_session_local: sessionmaker[Session] | None = None


def _connect_args_for(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def get_engine() -> Engine:
    global _engine, _engine_url, _session_local
    settings = get_settings()
    url = settings.recoveriq_db_url
    if _engine is None or _engine_url != url:
        if _engine is not None:
            _engine.dispose()
        _engine = create_engine(
            url,
            connect_args=_connect_args_for(url),
            echo=settings.log_sql_queries,
        )
        _engine_url = url
        _session_local = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_local() -> sessionmaker[Session]:
    get_engine()
    if _session_local is None:
        raise RuntimeError("Session factory is not initialized")
    return _session_local


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema_compatibility(engine)


def _ensure_sqlite_schema_compatibility(engine: Engine) -> None:
    # Ensure SQLite table columns are present on startup.
    if not str(engine.url).startswith("sqlite"):
        return

    inspector = inspect(engine)
    _ensure_table_columns(
        engine,
        inspector,
        table_name="policy_evaluations",
        required_columns={
            "evaluated_rules": "TEXT NOT NULL DEFAULT '{}'",
        },
    )
    _ensure_table_columns(
        engine,
        inspector,
        table_name="audit_events",
        required_columns={
            "actor_id": "TEXT",
            "correlation_id": "TEXT",
            "result": "TEXT",
            "metadata": "TEXT",
            "input_snapshot": "TEXT",
            "decision_snapshot": "TEXT",
            "policy_snapshot": "TEXT",
            "outcome_snapshot": "TEXT",
            "reason": "TEXT",
        },
    )


def _ensure_table_columns(
    engine: Engine,
    inspector,
    *,
    table_name: str,
    required_columns: dict[str, str],
) -> None:
    if not inspector.has_table(table_name):
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing_columns = [
        (column_name, column_ddl)
        for column_name, column_ddl in required_columns.items()
        if column_name not in existing_columns
    ]
    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_ddl in missing_columns:
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {column_name} {column_ddl}"
                )
            )


def reset_db_runtime() -> None:
    global _engine, _engine_url, _session_local
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
    _session_local = None


def get_db() -> Generator[Session, None, None]:
    session_local = get_session_local()
    db = session_local()
    try:
        yield db
    finally:
        db.close()

