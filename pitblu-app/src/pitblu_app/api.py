from __future__ import annotations

import asyncio
import contextlib
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pitblu_app import __version__
from pitblu_app.auth import AccessControl, Scope
from pitblu_app.core_client import PitbluCoreClient, ThermometerGateway
from pitblu_app.events import ApplicationEvents
from pitblu_app.models import (
    AssignmentCreate,
    CookCreate,
    CookerProfileCreate,
    CookerProfilePatch,
    CookEventCreate,
    CookPatch,
    DomainError,
    MeasurementCreate,
    MeasurementPatch,
    NamedCreate,
    NamedPatch,
    ShareCreate,
    TelemetryIn,
)
from pitblu_app.service import CookService
from pitblu_app.store import Store, public_row


def create_app(
    *,
    store: Store | None = None,
    core: ThermometerGateway | None = None,
    access: AccessControl | None = None,
    core_retry_seconds: float = 2,
) -> FastAPI:
    owns_store = store is None
    database = store or Store(os.getenv("PITBLU_APP_DATABASE", "pitblu-app.sqlite3"))
    access_control = access or AccessControl.from_environment()
    events = ApplicationEvents()
    service = CookService(database, events, access_control.follower_signing_secret())
    core_task: asyncio.Task[None] | None = None
    core_state: dict[str, Any] = {"available": False, "devices": [], "lastError": None}

    async def ingest_core() -> None:
        assert core is not None
        while True:
            try:
                devices = await core.reconcile()
                core_state.update(available=True, devices=devices, lastError=None)
                for device in devices:
                    for probe in device.get("probes", []):
                        if probe.get("observedAt"):
                            await service.ingest(
                                TelemetryIn(
                                    coreDeviceId=device["deviceId"],
                                    probeChannel=probe["probe"],
                                    temperatureC=probe.get("temperatureC"),
                                    observedAt=probe["observedAt"],
                                    available=bool(
                                        probe.get("available")
                                        and probe.get("fresh")
                                        and probe.get("present", True)
                                    ),
                                    eventId=(
                                        f"reconcile:{device['deviceId']}:{probe['probe']}:"
                                        f"{probe['observedAt']}"
                                    ),
                                )
                            )
                async for event in core.events():
                    kind = event.get("type")
                    if kind == "probe.temperature":
                        await service.ingest(
                            TelemetryIn.model_validate(
                                {
                                    "coreDeviceId": event.get("deviceId"),
                                    "probeChannel": event.get("probe"),
                                    "temperatureC": event.get("data", {}).get("temperatureC"),
                                    "observedAt": event.get("observedAt"),
                                    "available": True,
                                    "eventId": event.get("eventId"),
                                }
                            )
                        )
                    elif kind == "probe.availability":
                        data = event.get("data", {})
                        await service.ingest(
                            TelemetryIn.model_validate(
                                {
                                    "coreDeviceId": event.get("deviceId"),
                                    "probeChannel": event.get("probe"),
                                    "temperatureC": None,
                                    "observedAt": event.get("observedAt"),
                                    "available": bool(data.get("available", False)),
                                    "eventId": event.get("eventId"),
                                }
                            )
                        )
                core_state["available"] = False
                await service.mark_feed_unavailable()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                core_state.update(available=False, lastError=type(exc).__name__)
                await service.mark_feed_unavailable()
                await asyncio.sleep(core_retry_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal core_task
        if core:
            core_task = asyncio.create_task(ingest_core())
        try:
            yield
        finally:
            if core_task:
                core_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await core_task
            if owns_store:
                database.close()

    app = FastAPI(
        title="Pitblu API",
        version=__version__,
        description="API-first cook monitoring and management",
        lifespan=lifespan,
    )
    app.state.store, app.state.service, app.state.events = database, service, events

    def application_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=(
                "Pitblu's API-first cook contract. Operator tokens have full access; display "
                "tokens are read-only; optional integration tokens may add cook events, "
                "acknowledge alerts and invoke lifecycle transitions. Follower URLs are "
                "separate, cook-scoped read-only capabilities."
            ),
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["PitbluBearer"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "opaque",
            "description": "Use the operator, display, or integration token appropriate to the client.",
        }
        for path, path_item in schema.get("paths", {}).items():
            public = (
                path == "/health"
                or path.startswith("/api/v1/follow/")
                or path.startswith("/api/v1/shares/qr/")
            )
            for operation in path_item.values():
                if isinstance(operation, dict) and "responses" in operation:
                    operation["security"] = [] if public else [{"PitbluBearer": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = application_openapi  # type: ignore[method-assign]

    @app.middleware("http")
    async def response_safety(request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied = request.headers.get("x-correlation-id", "")
        request.state.correlation_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied) else uuid4().hex
        )
        public = (
            request.url.path == "/health"
            or request.url.path in {"/", "/display"}
            or request.url.path.startswith("/assets/")
            or request.url.path
            in {
                "/index.html",
                "/manifest.webmanifest",
                "/icon.svg",
                "/favicon-32.png",
                "/apple-touch-icon.png",
                "/pwa-192.png",
                "/pwa-512.png",
                "/pitblu-app-icon.png",
                "/pitblu-header-logo.png",
                "/pitblu-logo.png",
                "/pitblu-home-background.png",
                "/sw.js",
            }
            or request.url.path.startswith("/workbox-")
            or request.url.path.startswith("/follow/")
            or request.url.path.startswith("/api/v1/follow/")
            or request.url.path.startswith("/api/v1/shares/qr/")
        )
        try:
            if not public:
                scope = access_control.authenticate(request)
                request.state.scope = scope
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    integration_actions = (
                        "/events",
                        "/acknowledge",
                        "/start",
                        "/finish-cooking",
                        "/start-rest",
                        "/serve",
                        "/close",
                    )
                    if scope == Scope.DISPLAY or (
                        scope == Scope.INTEGRATION
                        and not request.url.path.endswith(integration_actions)
                    ):
                        raise DomainError(
                            "token does not permit this action", 403, "insufficient_scope"
                        )
            response = await call_next(request)
        except DomainError as exc:
            response = error_response(request, exc.code, str(exc), exc.status)
            if exc.status == 401:
                response.headers["WWW-Authenticate"] = "Bearer"
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        if request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.url.path in {"/sw.js", "/manifest.webmanifest"}:
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; manifest-src 'self'; "
            "worker-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    def error_response(
        request: Request, code: str, message: str, status_code: int, details: Any = None
    ) -> JSONResponse:
        error: dict[str, Any] = {
            "code": code,
            "message": message,
            "correlationId": request.state.correlation_id,
        }
        if details is not None:
            error["details"] = details
        return JSONResponse({"error": error}, status_code)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(request, exc.code, str(exc), exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "location": error.get("loc"),
                "message": error.get("msg"),
                "type": error.get("type"),
            }
            for error in exc.errors()
        ]
        return error_response(
            request, "validation_error", "request validation failed", 422, details
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
        return error_response(request, "internal_error", "internal service error", 500)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/v1/system", tags=["system"])
    async def system() -> dict[str, Any]:
        active = database.one(
            "SELECT id,name,state FROM cooks WHERE state IN ('active','cooking_finished','resting','served')"
        )
        latest = database.one("SELECT id,name,state FROM cooks ORDER BY created_at DESC LIMIT 1")
        return {
            "product": "Pitblu",
            "version": __version__,
            "core": core_state,
            "activeCook": public_row(active) if active else None,
            "latestCook": public_row(latest) if latest else None,
        }

    @app.get("/api/v1/cooks", tags=["cooks"])
    async def cooks() -> list[dict[str, Any]]:
        return service.cooks()

    @app.get("/api/v1/cooker-profiles", tags=["cookers"])
    async def cooker_profiles() -> list[dict[str, Any]]:
        return service.cooker_profiles()

    @app.post("/api/v1/cooker-profiles", status_code=201, tags=["cookers"])
    async def create_cooker_profile(body: CookerProfileCreate) -> dict[str, Any]:
        return await service.create_cooker_profile(body)

    @app.patch("/api/v1/cooker-profiles/{profile_id}", tags=["cookers"])
    async def patch_cooker_profile(profile_id: str, body: CookerProfilePatch) -> dict[str, Any]:
        return await service.patch_cooker_profile(profile_id, body)

    @app.post("/api/v1/cooks", status_code=201, tags=["cooks"])
    async def create_cook(body: CookCreate) -> dict[str, Any]:
        return await service.create_cook(body)

    @app.get("/api/v1/cooks/{cook_id}", tags=["cooks"])
    async def cook(cook_id: str) -> dict[str, Any]:
        return service.cook(cook_id)

    @app.patch("/api/v1/cooks/{cook_id}", tags=["cooks"])
    async def patch_cook(cook_id: str, body: CookPatch) -> dict[str, Any]:
        return await service.patch_cook(cook_id, body)

    @app.post("/api/v1/cooks/{cook_id}/start", tags=["cooks"])
    async def start(cook_id: str) -> dict[str, Any]:
        return await service.transition(cook_id, "start")

    @app.post("/api/v1/cooks/{cook_id}/finish-cooking", tags=["cooks"])
    async def finish(cook_id: str) -> dict[str, Any]:
        return await service.transition(cook_id, "finish")

    @app.post("/api/v1/cooks/{cook_id}/start-rest", tags=["cooks"])
    async def rest(cook_id: str) -> dict[str, Any]:
        return await service.transition(cook_id, "rest")

    @app.post("/api/v1/cooks/{cook_id}/serve", tags=["cooks"])
    async def serve(cook_id: str) -> dict[str, Any]:
        return await service.transition(cook_id, "serve")

    @app.post("/api/v1/cooks/{cook_id}/close", tags=["cooks"])
    async def close(cook_id: str) -> dict[str, Any]:
        return await service.transition(cook_id, "close")

    @app.post("/api/v1/cooks/{cook_id}/cookers", status_code=201, tags=["cookers"])
    async def add_cooker(cook_id: str, body: NamedCreate) -> dict[str, Any]:
        return await service.add_named("cookers", cook_id, body)

    @app.get("/api/v1/cookers/{cooker_id}", tags=["cookers"])
    async def cooker(cooker_id: str) -> dict[str, Any]:
        return public_row(database.require("cookers", cooker_id))

    @app.patch("/api/v1/cookers/{cooker_id}", tags=["cookers"])
    async def patch_cooker(cooker_id: str, body: NamedPatch) -> dict[str, Any]:
        return await service.patch_named("cookers", cooker_id, body)

    @app.post("/api/v1/cooks/{cook_id}/food-items", status_code=201, tags=["food items"])
    async def add_food(cook_id: str, body: NamedCreate) -> dict[str, Any]:
        return await service.add_named("food_items", cook_id, body)

    @app.get("/api/v1/food-items/{food_id}", tags=["food items"])
    async def food(food_id: str) -> dict[str, Any]:
        return public_row(database.require("food_items", food_id))

    @app.patch("/api/v1/food-items/{food_id}", tags=["food items"])
    async def patch_food(food_id: str, body: NamedPatch) -> dict[str, Any]:
        return await service.patch_named("food_items", food_id, body)

    @app.post("/api/v1/cooks/{cook_id}/measurements", status_code=201, tags=["measurements"])
    async def add_measurement(cook_id: str, body: MeasurementCreate) -> dict[str, Any]:
        return await service.add_measurement(cook_id, body)

    @app.get("/api/v1/measurements/{measurement_id}", tags=["measurements"])
    async def measurement(measurement_id: str) -> dict[str, Any]:
        return service.measurement(measurement_id)

    @app.patch("/api/v1/measurements/{measurement_id}", tags=["measurements"])
    async def patch_measurement(measurement_id: str, body: MeasurementPatch) -> dict[str, Any]:
        return await service.patch_measurement(measurement_id, body)

    @app.post("/api/v1/cooks/{cook_id}/assignments", status_code=201, tags=["probe assignments"])
    async def assign(cook_id: str, body: AssignmentCreate) -> dict[str, Any]:
        return await service.assign(cook_id, body)

    @app.delete("/api/v1/assignments/{assignment_id}", tags=["probe assignments"])
    async def end_assignment(assignment_id: str) -> dict[str, Any]:
        return await service.end_assignment(assignment_id)

    @app.get("/api/v1/cooks/{cook_id}/assignments", tags=["probe assignments"])
    async def assignments(cook_id: str) -> list[dict[str, Any]]:
        return service.assignments(cook_id)

    @app.get("/api/v1/cooks/{cook_id}/telemetry", tags=["telemetry"])
    async def telemetry(
        cook_id: str,
        start: str | None = Query(None),
        end: str | None = Query(None),
        max_points: int | None = Query(None, alias="maxPoints", ge=2, le=10000),
    ) -> list[dict[str, Any]]:
        return service.telemetry(cook_id, start, end, max_points)

    @app.get("/api/v1/cooks/{cook_id}/events", tags=["cook events"])
    async def cook_events(cook_id: str) -> list[dict[str, Any]]:
        return [
            public_row(x)
            for x in database.all(
                "SELECT * FROM cook_events WHERE cook_id=? ORDER BY occurred_at", (cook_id,)
            )
        ]

    @app.post("/api/v1/cooks/{cook_id}/events", status_code=201, tags=["cook events"])
    async def add_event(
        cook_id: str,
        body: CookEventCreate,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, Any]:
        return await service.add_event(cook_id, body, idempotency_key)

    @app.get("/api/v1/alerts", tags=["alerts"])
    async def alerts(
        cook_id: str | None = Query(None, alias="cookId"), active: bool = False
    ) -> list[dict[str, Any]]:
        return service.alerts(cook_id, active)

    @app.get("/api/v1/alerts/{alert_id}", tags=["alerts"])
    async def alert(alert_id: str) -> dict[str, Any]:
        return public_row(database.require("alerts", alert_id))

    @app.post("/api/v1/alerts/{alert_id}/acknowledge", tags=["alerts"])
    async def acknowledge(alert_id: str) -> dict[str, Any]:
        return await service.acknowledge(alert_id)

    @app.post("/api/v1/cooks/{cook_id}/shares", status_code=201, tags=["sharing"])
    async def create_share(cook_id: str, _body: ShareCreate) -> dict[str, Any]:
        share, token = service.create_share(cook_id)
        return share | {"token": token, "followerPath": f"/follow/{token}"}

    @app.get("/api/v1/cooks/{cook_id}/shares", tags=["sharing"])
    async def shares(cook_id: str) -> list[dict[str, Any]]:
        return service.shares(cook_id)

    @app.get("/api/v1/cooks/{cook_id}/default-share", tags=["sharing"])
    async def default_share(cook_id: str) -> dict[str, Any]:
        return service.ensure_default_share(cook_id)

    @app.post("/api/v1/cooks/{cook_id}/default-share/regenerate", tags=["sharing"])
    async def regenerate_default_share(cook_id: str) -> dict[str, Any]:
        return service.regenerate_default_share(cook_id)

    @app.delete("/api/v1/shares/{share_id}", status_code=204, tags=["sharing"])
    async def revoke_share(share_id: str) -> None:
        service.revoke_share(share_id)

    @app.get("/api/v1/shares/qr/{token}", tags=["sharing"])
    async def share_qr(token: str, request: Request) -> Response:
        service.follower_cook(token)
        import qrcode  # type: ignore[import-untyped]
        import qrcode.image.svg  # type: ignore[import-untyped]

        target = str(request.base_url).rstrip("/") + f"/follow/{token}"
        image = qrcode.make(target, image_factory=qrcode.image.svg.SvgPathImage)
        return Response(image.to_string(), media_type="image/svg+xml")

    @app.get("/api/v1/follow/{token}", tags=["sharing"])
    async def follower(token: str) -> dict[str, Any]:
        return service.follower_cook(token)

    @app.get("/api/v1/follow/{token}/telemetry", tags=["sharing"])
    async def follower_telemetry(
        token: str,
        start: str | None = Query(None),
        end: str | None = Query(None),
        max_points: int | None = Query(1000, alias="maxPoints", ge=2, le=2000),
    ) -> list[dict[str, Any]]:
        return service.follower_telemetry(token, start, end, max_points)

    @app.get("/api/v1/follow/{token}/events", tags=["sharing"])
    async def follower_events(token: str) -> list[dict[str, Any]]:
        return service.follower_events(token)

    @app.get("/api/v1/follow/{token}/stream", tags=["sharing"])
    async def follower_stream(token: str) -> StreamingResponse:
        cook_id = service.follower_share(token)["cook_id"]

        def belongs_to_cook(event: dict[str, Any]) -> bool:
            data = event["data"]
            event_cook_id = data.get("cookId")
            if event["type"].startswith("cook."):
                event_cook_id = data.get("id", event_cook_id)
            return event_cook_id == cook_id

        return StreamingResponse(
            events.stream(belongs_to_cook),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/v1/events", tags=["live events"])
    async def live_events() -> StreamingResponse:
        return StreamingResponse(
            events.stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    static = Path(__file__).with_name("static")
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/follow/{token}", include_in_schema=False)
    async def ui() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/display", include_in_schema=False)
    async def display_ui() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/{asset_name}", include_in_schema=False)
    async def pwa_asset(asset_name: str) -> FileResponse:
        if not re.fullmatch(
            r"(?:index\.html|manifest\.webmanifest|icon\.svg|favicon-32\.png|apple-touch-icon\.png|pwa-(?:192|512)\.png|pitblu-app-icon\.png|pitblu-header-logo\.png|pitblu-logo\.png|pitblu-home-background\.png|sw\.js|workbox-[a-zA-Z0-9_-]+\.js)",
            asset_name,
        ):
            raise DomainError("resource not found", 404, "not_found")
        path = static / asset_name
        if not path.is_file():
            raise DomainError("resource not found", 404, "not_found")
        return FileResponse(path)

    return app


def run() -> None:
    import uvicorn

    core_url = os.getenv("PITBLU_CORE_URL", "http://127.0.0.1:8080")
    core = PitbluCoreClient(core_url, os.getenv("PITBLU_CORE_TOKEN"))
    uvicorn.run(
        create_app(core=core),
        host=os.getenv("PITBLU_APP_BIND", "0.0.0.0"),
        port=int(os.getenv("PITBLU_APP_PORT", "8081")),
    )
