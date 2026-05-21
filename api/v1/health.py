from fastapi import APIRouter, Depends

from core.memory.store import MemoryService, get_memory_service
from core.registry import AppRegistry, get_registry
from core.llm.provider import get_llm
from config.settings import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(
    memory: MemoryService = Depends(get_memory_service),
    registry: AppRegistry = Depends(get_registry),
) -> dict:
    settings = get_settings()
    mem_ok = await memory.is_healthy() if memory else False

    llm_ok = True
    try:
        get_llm()
    except Exception:
        llm_ok = False

    status = "ok" if (llm_ok and (mem_ok or not settings.memory_enabled)) else "degraded"

    apps = await registry.list_apps()
    registered_apps = len(apps)

    return {
        "status": status,
        "llmProvider": settings.llm_provider,
        "llmModel": settings.llm_model,
        "memoryEnabled": settings.memory_enabled,
        "memoryConnected": mem_ok,
        "registeredApps": registered_apps,
        "apps": apps,
        "version": "2.0.0",
    }
