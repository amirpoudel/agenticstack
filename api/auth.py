"""API key authentication dependency."""
from fastapi import Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader

from config.settings import get_settings

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def check_api_key(x_api_key: str | None = Depends(_api_key_header)) -> None:
    settings = get_settings()
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key")
