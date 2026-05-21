"""
App registration endpoint.

POST /v1/apps/register  — Register an app by name. Returns 409 if already registered.
GET  /v1/apps/{app_name} — Check registration status.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.models import RegisterAppRequest, RegisterAppResponse
from core.registry import AlreadyRegisteredError, AppRegistry, get_registry
from api.auth import check_api_key

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Apps"])


@router.post(
    "/apps/register",
    response_model=RegisterAppResponse,
    summary="Register an agent app",
    description=(
        "Register your app by a unique name. "
        "Provide a description (or a full systemPrompt), tool schemas, and optional default state. "
        "Returns 409 if the app name is already registered."
    ),
)
async def register_app(
    request: RegisterAppRequest,
    registry: AppRegistry = Depends(get_registry),
    _: None = Depends(check_api_key),
) -> RegisterAppResponse:
    try:
        reg = await registry.register(request)
        return RegisterAppResponse(appName=reg.app_name, toolCount=reg.tool_count, status="registered")
    except AlreadyRegisteredError:
        raise HTTPException(status_code=409, detail=f"App '{request.appName}' is already registered.")


@router.get(
    "/apps/{app_name}",
    response_model=RegisterAppResponse,
    summary="Check app registration status",
)
async def get_app(
    app_name: str,
    registry: AppRegistry = Depends(get_registry),
    _: None = Depends(check_api_key),
) -> RegisterAppResponse:
    reg = await registry.get(app_name)
    if not reg:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not registered.")
    return RegisterAppResponse(appName=reg.app_name, toolCount=reg.tool_count, status="registered")
