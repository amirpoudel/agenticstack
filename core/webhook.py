"""
Webhook dispatcher — sends events to the caller's callbackUrl.

Used in async mode: AgenticStack processes in background,
then POSTs results (tool_calls / reply / error) to the callbackUrl.
"""
import logging
from typing import Optional

import httpx

from api.models import WebhookEvent

logger = logging.getLogger(__name__)

# Shared async client — connection pooling, keep-alive
_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_http_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def dispatch_webhook(callback_url: str, event: WebhookEvent) -> bool:
    """POST a WebhookEvent to the caller's callbackUrl. Returns True on success."""
    try:
        client = get_http_client()
        resp = await client.post(
            callback_url,
            json=event.model_dump(exclude_none=True),
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            logger.error(
                f"[webhook] Callback failed — url={callback_url} "
                f"status={resp.status_code} body={resp.text[:200]}"
            )
            return False
        logger.info(
            f"[webhook] Dispatched event={event.event} to {callback_url} "
            f"turnId={event.turnId}"
        )
        return True
    except Exception as e:
        logger.error(f"[webhook] Dispatch error — url={callback_url} err={e}")
        return False
