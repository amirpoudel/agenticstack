import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1 import apps, chat, memory, health
from config.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    from core.memory.store import init_memory_service, close_memory_service
    from core.registry import init_app_registry_store, close_app_registry_store
    await init_memory_service()
    await init_app_registry_store()

    # Show the actual model/deployment name in use — for Azure this is the
    # deployment name, for other providers it's llm_model.
    display_model = (
        settings.azure_openai_deployment_name
        if settings.llm_provider.lower() == "azure" and settings.azure_openai_deployment_name
        else settings.llm_model
    )
    logging.getLogger(__name__).info(
        f"AgenticStack ready — llm={settings.llm_provider} "
        f"model={display_model} memory={'on' if settings.memory_enabled else 'off'}"
    )
    yield

    from core.webhook import close_http_client
    await close_http_client()
    await close_app_registry_store()
    await close_memory_service()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AgenticStack",
        description=(
            "Plug-and-play agentic AI engine. "
            "Domain-agnostic LLM orchestration with memory. "
            "Register your tools, send messages, get intelligent replies."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(apps.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    app.include_router(memory.router, prefix="/v1")
    app.include_router(health.router, prefix="/v1")

    return app


app = create_app()
