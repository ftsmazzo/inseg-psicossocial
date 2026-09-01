from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_schema_patches() -> None:
    """Ajustes leves sem Alembic (ex.: coluna nova em SQLite/Postgres já existente)."""
    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
            }
            if "job_lines" not in tables:
                return
            cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(job_lines)")).fetchall()
            }
            if "needs_review" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE job_lines ADD COLUMN needs_review BOOLEAN "
                        "NOT NULL DEFAULT 0"
                    )
                )
        elif dialect in {"postgresql", "postgres"}:
            conn.execute(
                text(
                    "ALTER TABLE job_lines ADD COLUMN IF NOT EXISTS "
                    "needs_review BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
