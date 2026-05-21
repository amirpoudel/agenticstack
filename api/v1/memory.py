import logging

from fastapi import APIRouter, Depends

from api.models import MemoryResponse, MemoryWriteRequest
from core.memory.store import MemoryService, get_memory_service
from api.auth import check_api_key

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Memory"])


@router.get("/memory/{user_id}", response_model=MemoryResponse)
async def get_memory(
    user_id: str,
    query: str = "",
    memory: MemoryService = Depends(get_memory_service),
    _: None = Depends(check_api_key),
) -> MemoryResponse:
    """Return recent memories for a user via LangMem semantic search.

    userId should be the same composite ID used in /chat (e.g. "tenantId_userId").
    """
    results = await memory.search(user_id, query=query or "about this user", top_k=10)
    return MemoryResponse(userId=user_id, summary="\n".join(results), facts=results)


@router.post("/memory/{user_id}", response_model=MemoryResponse)
async def set_memory(
    user_id: str,
    body: MemoryWriteRequest,
    memory: MemoryService = Depends(get_memory_service),
    _: None = Depends(check_api_key),
) -> MemoryResponse:
    """Store a user↔assistant exchange — LangMem extracts and indexes facts from it."""
    if body.summary is not None:
        await memory.add(user_id, user_message=body.summary, assistant_reply="")
    return MemoryResponse(userId=user_id, summary=body.summary)


@router.delete("/memory/{user_id}", status_code=204)
async def delete_memory(
    user_id: str,
    memory: MemoryService = Depends(get_memory_service),
    _: None = Depends(check_api_key),
) -> None:
    """Delete all LangMem memories for a user."""
    await memory.delete_user(user_id)
