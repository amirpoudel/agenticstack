"""
SQLAlchemy async models for AgenticStack.

The `registered_apps` table stores every app registered via POST /v1/apps/register.
Each app has a unique name, an optional description, an optional system prompt,
a list of tool schemas, a default state dict, and an optional structured output
schema.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import async_sessionmaker


class Base(DeclarativeBase):
    pass


class RegisteredApp(Base):
    """One row per registered app — identified by a unique app_name."""

    __tablename__ = "registered_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tools: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    state: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    structured_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Per-app overrides — None means fall back to global env var defaults
    llm_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Engine / session factory (module-level singletons) ───────────────────────

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine not initialised. Call init_db() first.")
    return _engine


def get_session() -> AsyncSession:
    if _session_factory is None:
        raise RuntimeError("Session factory not initialised. Call init_db() first.")
    return _session_factory()


async def init_db(database_url: str) -> None:
    """Create the engine, run CREATE TABLE IF NOT EXISTS for all models."""
    global _engine, _session_factory
    _engine = create_async_engine(database_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        has_structured_output = await conn.run_sync(
            lambda sync_conn: "structured_output" in {
                col["name"] for col in inspect(sync_conn).get_columns("registered_apps")
            }
        )
        if not has_structured_output:
            await conn.execute(
                text("ALTER TABLE registered_apps ADD COLUMN structured_output JSONB")
            )


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
