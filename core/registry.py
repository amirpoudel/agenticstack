"""App registry backed by the `registered_apps` Postgres table.

Apps are upserted on register and fully cached in memory on startup so that
chat hot-paths never hit the DB.  Delete/update are supported at runtime.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.models import RegisterAppRequest, ToolSchema
from core.agent.models import RegisteredApp, get_session

logger = logging.getLogger(__name__)


@dataclass
class AppRegistration:
    """In-memory snapshot of a registered app's config."""

    app_name: str
    description: str = ""
    system_prompt: Optional[str] = None
    tools: List[ToolSchema] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)

    # Per-app overrides — None means fall back to global env var defaults
    llm_temperature: Optional[float] = None
    memory_enabled: Optional[bool] = None

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
            llm_temperature=row.llm_temperature,
            memory_enabled=row.memory_enabled,
        )


class AppRegistry:
    """Registry with a warm in-memory cache.

    * On startup all rows are loaded from DB (``warm_cache``).
    * ``register`` upserts — never raises a duplicate error.
    * ``update`` replaces an existing app's config.
    * ``delete`` removes an app from both cache and DB.
    * ``get`` / ``list_apps`` are cache-only after startup.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, AppRegistration] = {}

    # ── Cache warm-up ─────────────────────────────────────────────────────────

    async def warm_cache(self) -> None:
        """Load all registered apps from DB into memory on startup."""
        async with get_session() as session:
            result = await session.execute(select(RegisteredApp))
            rows = result.scalars().all()

        self._cache = {row.app_name: AppRegistration.from_row(row) for row in rows}
        logger.info(f"[registry] Warmed cache — {len(self._cache)} apps loaded")

    # ── Write ─────────────────────────────────────────────────────────────────

    async def register(self, request: RegisterAppRequest) -> Tuple[AppRegistration, bool]:
        """Upsert an app.  Returns (registration, created) where created=False means updated."""
        name = request.appName.strip()
        if not name:
            raise ValueError("appName is required")

        tools_json = [t.model_dump(mode="json") for t in request.tools]

        stmt = (
            pg_insert(RegisteredApp)
            .values(
                app_name=name,
                description=request.description,
                system_prompt=request.systemPrompt,
                tools=tools_json,
                state=request.state,
                llm_temperature=request.llmTemperature,
                memory_enabled=request.memoryEnabled,
            )
            .on_conflict_do_update(
                index_elements=["app_name"],
                set_={
                    "description": request.description,
                    "system_prompt": request.systemPrompt,
                    "tools": tools_json,
                    "state": request.state,
                    "llm_temperature": request.llmTemperature,
                    "memory_enabled": request.memoryEnabled,
                },
            )
            .returning(RegisteredApp)
        )

        created = name not in self._cache

        async with get_session() as session:
            result = await session.execute(stmt)
            await session.commit()
            row = result.scalar_one()

        reg = AppRegistration.from_row(row)
        self._cache[name] = reg
        action = "Registered" if created else "Updated"
        logger.info(f"[registry] {action} '{name}' — {reg.tool_count} tools")
        return reg, created

    async def update(self, app_name: str, request: RegisterAppRequest) -> Optional[AppRegistration]:
        """Update an existing app.  Returns None if the app does not exist."""
        name = app_name.strip()
        if name not in self._cache:
            return None

        # Reuse upsert path
        reg, _ = await self.register(request)
        return reg

    async def delete(self, app_name: str) -> bool:
        """Delete an app from cache and DB.  Returns True if it existed."""
        name = app_name.strip()
        if name not in self._cache:
            return False

        async with get_session() as session:
            await session.execute(
                sa_delete(RegisteredApp).where(RegisteredApp.app_name == name)
            )
            await session.commit()

        del self._cache[name]
        logger.info(f"[registry] Deleted '{name}'")
        return True

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, app_name: str) -> Optional[AppRegistration]:
        return self._cache.get(app_name.strip())

    async def list_apps(self) -> List[str]:
        return list(self._cache.keys())


# ── Module-level singleton ────────────────────────────────────────────────────

_registry = AppRegistry()


async def init_app_registry_store() -> None:
    """Initialise the DB engine and warm the in-memory cache (called on FastAPI startup)."""
    from core.agent.models import init_db
    from config.settings import get_settings

    settings = get_settings()
    db_url = (
        f"postgresql+psycopg://{settings.app_postgres_user}"
        f":{settings.app_postgres_password}"
        f"@{settings.app_postgres_host}"
        f":{settings.app_postgres_port}"
        f"/{settings.app_postgres_db}"
    )
    await init_db(db_url)
    logger.info(f"[registry] DB ready → {settings.app_postgres_host}/{settings.app_postgres_db}")
    await _registry.warm_cache()


async def close_app_registry_store() -> None:
    from core.agent.models import close_db
    await close_db()


def get_registry() -> AppRegistry:
    return _registry
