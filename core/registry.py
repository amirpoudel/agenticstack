"""App registry backed by the `registered_apps` Postgres table.

Each app registers once by a unique name.  On chat, the graph loads the
app's config (tools, system prompt, default state) from this table.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.models import RegisterAppRequest, ToolSchema
from core.agent.models import RegisteredApp, get_session

logger = logging.getLogger(__name__)


class AlreadyRegisteredError(Exception):
    """Raised when an app name is already in the registry."""


@dataclass
class AppRegistration:
    """In-memory snapshot of a registered app's config."""

    app_name: str
    description: str = ""
    system_prompt: Optional[str] = None
    tools: List[ToolSchema] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    @classmethod
    def from_row(cls, row: RegisteredApp) -> "AppRegistration":
        return cls(
            app_name=row.app_name,
            description=row.description or "",
            system_prompt=row.system_prompt,
            tools=[ToolSchema(**t) for t in (row.tools or [])],
            state=dict(row.state or {}),
        )


class AppRegistry:
    """Registry with an in-memory cache (warm reads, DB writes)."""

    def __init__(self) -> None:
        self._cache: Dict[str, AppRegistration] = {}

    # ── Write ─────────────────────────────────────────────────────────────────

    async def register(self, request: RegisterAppRequest) -> AppRegistration:
        name = request.appName.strip()
        if not name:
            raise ValueError("appName is required")

        if name in self._cache:
            raise AlreadyRegisteredError(name)

        row = RegisteredApp(
            app_name=name,
            description=request.description,
            system_prompt=request.systemPrompt,
            tools=[t.model_dump(mode="json") for t in request.tools],
            state=request.state,
        )

        async with get_session() as session:
            try:
                session.add(row)
                await session.commit()
                await session.refresh(row)
            except IntegrityError:
                await session.rollback()
                raise AlreadyRegisteredError(name)

        reg = AppRegistration.from_row(row)
        self._cache[name] = reg
        logger.info(f"[registry] Registered '{name}' — {reg.tool_count} tools")
        return reg

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, app_name: str) -> Optional[AppRegistration]:
        name = app_name.strip()
        if not name:
            return None

        if name in self._cache:
            return self._cache[name]

        async with get_session() as session:
            result = await session.execute(
                select(RegisteredApp).where(RegisteredApp.app_name == name)
            )
            row = result.scalar_one_or_none()

        if row is None:
            return None

        reg = AppRegistration.from_row(row)
        self._cache[name] = reg
        return reg

    async def list_apps(self) -> List[str]:
        async with get_session() as session:
            result = await session.execute(select(RegisteredApp.app_name))
            return [r for (r,) in result.all()]


# ── Module-level singleton ────────────────────────────────────────────────────

_registry = AppRegistry()


async def init_app_registry_store() -> None:
    """Initialise the DB engine (called on FastAPI startup)."""
    from core.agent.models import init_db
    from config.settings import get_settings

    settings = get_settings()
    db_url = (
        f"postgresql+psycopg://{settings.langmem_postgres_user}"
        f":{settings.langmem_postgres_password}"
        f"@{settings.langmem_postgres_host}"
        f":{settings.langmem_postgres_port}"
        f"/{settings.langmem_postgres_db}"
    )
    await init_db(db_url)
    logger.info(f"[registry] DB ready → {settings.langmem_postgres_host}")


async def close_app_registry_store() -> None:
    from core.agent.models import close_db
    await close_db()


def get_registry() -> AppRegistry:
    return _registry
