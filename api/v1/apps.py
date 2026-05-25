"""
App registration endpoints.

POST   /v1/apps/register      — Upsert an app (creates or updates, never 409).
GET    /v1/apps/{app_name}    — Get registration details.
PUT    /v1/apps/{app_name}    — Update an existing app's config.
DELETE /v1/apps/{app_name}    — Remove an app from registry and memory.
GET    /v1/apps               — List all registered app names.
"""
from fastapi import APIRouter, Depends, HTTPException

from api.models import AppInfo, RegisterAppRequest, RegisterAppResponse
from core.registry import AppRegistry, get_registry
from api.auth import check_api_key
router = APIRouter(tags=["Apps"])


@router.post(
    "/apps/register",
    response_model=RegisterAppResponse,
    summary="Register or update an agent app",
    description=(
        "Upsert your app by a unique name.  Creates the app on first call; "
        "updates its config on subsequent calls with the same name."
    ),
)
async def register_app(
    request: RegisterAppRequest,
    registry: AppRegistry = Depends(get_registry),
    _: None = Depends(check_api_key),
) -> RegisterAppResponse:
    reg, created = await registry.register(request)
    status = "registered" if created else "updated"
    return RegisterAppResponse(appName=reg.app_name, toolCount=reg.tool_count, status=status)


@router.put(
    "/apps/{app_name}",
    response_model=RegisterAppResponse,
    summary="Update a registered app",
)
async def update_app(
    app_name: str,
    request: RegisterAppRequest,
    registry: AppRegistry = Depends(get_registry),
    _: None = Depends(check_api_key),
) -> RegisterAppResponse:
    reg = await registry.update(app_name, request)
    if not reg:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not registered.")
    return RegisterAppResponse(appName=reg.app_name, toolCount=reg.tool_count, status="updated")


@router.delete(
    "/apps/{app_name}",
    response_model=RegisterAppResponse,
    summary="Delete a registered app",
)
async def delete_app(
    app_name: str,
    registry: AppRegistry = Depends(get_registry),
    _: None = Depends(check_api_key),
) -> RegisterAppResponse:
    deleted = await registry.delete(app_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not registered.")
    return RegisterAppResponse(appName=app_name, toolCount=0, status="deleted")


@router.get(
    "/apps",
    response_model=list[AppInfo],
    summary="List all registered apps with full config",
)
async def list_apps(
    registry: AppRegistry = Depends(get_registry),
    _: None = Depends(check_api_key),
) -> list[AppInfo]:
    app_names = await registry.list_apps()
    result = []
    for name in app_names:
        reg = await registry.get(name)
        if reg:
            result.append(AppInfo(
                appName=reg.app_name,
                description=reg.description,
                systemPrompt=reg.system_prompt,
                tools=reg.tools,
                state=reg.state,
                llmTemperature=reg.llm_temperature,
                memoryEnabled=reg.memory_enabled,
            ))
    return result


@router.get(
    "/apps/{app_name}",
    response_model=AppInfo,
    summary="Get app registration details",
)
async def get_app(
    app_name: str,
    registry: AppRegistry = Depends(get_registry),
    _: None = Depends(check_api_key),
) -> AppInfo:
    reg = await registry.get(app_name)
    if not reg:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not registered.")
    return AppInfo(
        appName=reg.app_name,
        description=reg.description,
        systemPrompt=reg.system_prompt,
        tools=reg.tools,
        state=reg.state,
        llmTemperature=reg.llm_temperature,
        memoryEnabled=reg.memory_enabled,
    )
