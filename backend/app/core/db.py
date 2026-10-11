from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns() -> None:
    """Минимальная автомиграция для MVP: добавляет в существующие таблицы колонки, которых там ещё нет.
    Нужна, чтобы обновление не требовало пересоздавать базу. В проде — Alembic."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(dialect=engine.dialect)
                default = ""
                if col.server_default is not None:
                    default = " DEFAULT " + str(col.server_default.arg.compile(dialect=engine.dialect)
                                                 if hasattr(col.server_default.arg, "compile") else f"'{col.server_default.arg}'")
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}{default}'))
    # Новые значения перечислений (PostgreSQL хранит Enum как отдельный тип)
    if engine.dialect.name == "postgresql":
        from sqlalchemy import Enum as SaEnum
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for table in Base.metadata.sorted_tables:
                for col in table.columns:
                    if isinstance(col.type, SaEnum) and col.type.name:
                        for value in col.type.enums:
                            conn.execute(text(f"ALTER TYPE {col.type.name} ADD VALUE IF NOT EXISTS '{value}'"))
