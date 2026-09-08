"""FastAPI control plane for pitboss-admin."""

import asyncio
import contextlib
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.types import Receive, Scope, Send

from pitboss_admin import __version__
from pitboss_admin.adapters.base import DeviceAdapter
from pitboss_admin.adapters.igrill_v202 import BleakIGrillV202Adapter
from pitboss_admin.adapters.simulated import SimulatedIGrillAdapter
from pitboss_admin.auth import AdministratorTokens
from pitboss_admin.configuration import ConfigurationManager, ConfigurationValueError
from pitboss_admin.diagnostics import HostDiagnostics
from pitboss_admin.events import EventBus, EventType, TelemetryEvent
from pitboss_admin.models import utc_now
from pitboss_admin.mqtt import MqttPublisher, MqttSettings
from pitboss_admin.security import RateLimit, RequestBounds
from pitboss_admin.service import (
    AdministrationService,
    ResourceNotFoundError,
    StateConflictError,
)
from pitboss_admin.storage import AdministrativeStore, VersionConflictError
from pitboss_admin.telemetry import TelemetryState


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScanRequest(_RequestModel):
    duration: float | None = Field(None, gt=0, le=60)


class RegisterDeviceRequest(_RequestModel):
    discovery_id: str = Field(alias="discoveryId", min_length=1)
    friendly_name: str | None = Field(None, alias="friendlyName", max_length=100)
    connect: bool = False
    automatic_reconnection: bool = Field(True, alias="automaticReconnection")


class PatchDeviceRequest(_RequestModel):
    discovery_id: str | None = Field(None, alias="discoveryId", min_length=1)
    friendly_name: str | None = Field(None, alias="friendlyName", max_length=100)
    automatic_reconnection: bool | None = Field(None, alias="automaticReconnection")


class ConfigPatchRequest(_RequestModel):
    values: dict[str, Any]


class SecretRequest(_RequestModel):
    value: str = Field(min_length=1, max_length=4096)


def _error(
    request: Request,
    code: str,
    message: str,
    http_status: int,
    details: Any = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "correlationId": request.state.correlation_id,
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=http_status)


def _validation_details(exc: RequestValidationError) -> list[dict[str, object]]:
    """Return useful validation fields without echoing request values or secrets."""
    return [
        {
            "type": error.get("type"),
            "location": error.get("loc"),
            "message": error.get("msg"),
        }
        for error in exc.errors()
    ]


def create_app(
    *,
    adapter: DeviceAdapter | None = None,
    store: AdministrativeStore | None = None,
    configuration: ConfigurationManager | None = None,
) -> FastAPI:
    database = store or AdministrativeStore()
    config = configuration or ConfigurationManager(database)
    startup = config.config.model_copy(deep=True)
    selected_adapter = adapter or (
        SimulatedIGrillAdapter(config.config.simulation.probe_count, clock=utc_now)
        if config.config.simulation.enabled
        else BleakIGrillV202Adapter(
            connect_timeout=config.config.bluetooth.connect_timeout,
            initialise_timeout=config.config.bluetooth.initialise_timeout,
            read_timeout=config.config.bluetooth.read_timeout,
            battery_interval=config.config.polling.battery_interval,
        )
    )
    events = EventBus(persist=database.append_event)
    telemetry = TelemetryState(events, stale_after=config.config.polling.stale_after)
    service = AdministrationService(
        selected_adapter,
        database,
        telemetry,
        poll_interval=config.config.polling.probe_interval,
        degraded_after=config.config.polling.degraded_after_failures,
        reconnect_after=config.config.polling.forced_reconnect_after,
        stable_after=config.config.polling.stable_backoff_reset,
        scan_duration=config.config.bluetooth.scan_duration,
        missing_scan_interval=config.config.bluetooth.missing_scan_interval,
        connected_scan_interval=config.config.bluetooth.connected_scan_interval,
    )
    tokens = AdministratorTokens(database)
    host_diagnostics = HostDiagnostics()
    authentication_limit = RateLimit(startup.security.auth_requests_per_minute)
    mutation_limit = RateLimit(startup.security.mutations_per_minute)
    authentication_jobs: set[asyncio.Task[bool]] = set()
    sse_clients = 0
    bootstrap_token = None
    if config.config.auth.mode == "token" and not tokens.status().configured:
        bootstrap_token = tokens.bootstrap()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        await service.start()
        mqtt_task: asyncio.Task[None] | None = None
        if config.config.mqtt.enabled:
            mqtt = MqttPublisher(
                MqttSettings(
                    host=config.config.mqtt.host,
                    port=config.config.mqtt.port,
                    username=config.config.mqtt.username,
                    password=database.get_secret("mqtt.password"),
                    tls=config.config.mqtt.tls,
                    base_topic=config.config.mqtt.base_topic,
                    qos=config.config.mqtt.qos,
                    source=selected_adapter.source,
                    heartbeat=config.config.polling.availability_heartbeat,
                    stable_after=config.config.polling.stable_backoff_reset,
                )
            )
            mqtt_task = asyncio.create_task(mqtt.run(events))
            _app.state.mqtt = mqtt
        await events.publish(
            TelemetryEvent(
                type=EventType.SERVICE_AVAILABILITY,
                sequence=1,
                source=selected_adapter.source,
                data={"available": True},
            )
        )
        try:
            yield
        finally:
            await service.close()
            await events.publish(
                TelemetryEvent(
                    type=EventType.SERVICE_AVAILABILITY,
                    sequence=2,
                    source=selected_adapter.source,
                    data={"available": False},
                )
            )
            if mqtt_task is not None:
                if mqtt.state != "connected":
                    mqtt_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(mqtt_task, timeout=15)

    app = FastAPI(
        title="pitboss-admin",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.service = service
    app.state.configuration = config
    app.state.tokens = tokens
    app.state.events = events
    app.state.mqtt = None
    app.state.bootstrap_token = bootstrap_token
    app.add_middleware(RequestBounds, maximum_bytes=startup.security.maximum_body_bytes)

    if config.config.server.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.config.server.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "If-Match", "X-Correlation-ID"],
            expose_headers=["ETag", "X-Correlation-ID", "Retry-After"],
        )

    @app.middleware("http")
    async def correlation(request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied = request.headers.get("x-correlation-id", "")
        request.state.correlation_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied) else uuid4().hex
        )
        response = await call_next(request)
        response.headers["x-correlation-id"] = request.state.correlation_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(
            request,
            "validation_error",
            "request validation failed",
            422,
            _validation_details(exc),
        )

    @app.exception_handler(ResourceNotFoundError)
    async def not_found(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
        return _error(request, "not_found", str(exc), 404)

    @app.exception_handler(StateConflictError)
    async def conflict(request: Request, exc: StateConflictError) -> JSONResponse:
        return _error(request, "state_conflict", str(exc), 409)

    @app.exception_handler(ValidationError)
    async def config_validation(request: Request, exc: ValidationError) -> JSONResponse:
        return _error(request, "validation_error", "configuration validation failed", 422)

    @app.exception_handler(ConfigurationValueError)
    async def config_value_error(request: Request, exc: ConfigurationValueError) -> JSONResponse:
        return _error(request, "validation_error", str(exc), 422)

    @app.exception_handler(AuthenticationError)
    async def authentication_error(request: Request, _exc: AuthenticationError) -> JSONResponse:
        return _error(request, "authentication_required", "valid bearer token required", 401)

    async def authenticate(request: Request) -> None:
        if startup.auth.mode != "disabled":
            if retry := authentication_limit.retry_after():
                raise ThrottledError(retry)
            authorization = request.headers.get("authorization", "")
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer":
                raise AuthenticationError
            if len(authentication_jobs) >= 2:
                raise ThrottledError(1)
            job = asyncio.create_task(asyncio.to_thread(tokens.verify, token))
            authentication_jobs.add(job)

            def finished(completed: asyncio.Task[bool]) -> None:
                authentication_jobs.discard(completed)
                if not completed.cancelled():
                    completed.exception()

            job.add_done_callback(finished)
            # A disconnected caller must not free a slot while its hash still runs.
            valid = await asyncio.shield(job)
            if not valid:
                raise AuthenticationError
        if request.method in {"POST", "PATCH", "PUT", "DELETE"} and (
            retry := mutation_limit.retry_after()
        ):
            raise ThrottledError(retry)

    @app.exception_handler(ThrottledError)
    async def throttled(request: Request, exc: ThrottledError) -> JSONResponse:
        response = _error(request, "rate_limited", "retry later", 429)
        response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(Exception)
    async def safe_exception(request: Request, exc: Exception) -> JSONResponse:
        return _error(request, "internal_error", "internal service error", 500)

    protected = Annotated[None, Depends(authenticate)]

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi(_auth: protected) -> dict[str, Any]:
        return app.openapi()

    @app.get("/docs", include_in_schema=False)
    async def docs(_auth: protected) -> HTMLResponse:
        return get_swagger_ui_html(openapi_url="/openapi.json", title="pitboss-admin API")

    @app.get("/redoc", include_in_schema=False)
    async def redoc(_auth: protected) -> HTMLResponse:
        return get_redoc_html(openapi_url="/openapi.json", title="pitboss-admin API")

    def config_response() -> dict[str, Any]:
        configured, changed_at = database.secret_status("mqtt.password")
        return config.describe() | {
            "secrets": {"mqtt.password": {"configured": configured, "changedAt": changed_at}}
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", dependencies=[Depends(authenticate)])
    async def ready(response: Response) -> dict[str, str]:
        mqtt = app.state.mqtt
        if mqtt is not None and mqtt.state != "connected":
            response.status_code = 503
            return {"status": "not_ready"}
        return {"status": "ready"}

    @app.get("/api/v1/status", dependencies=[Depends(authenticate)])
    async def service_status() -> dict[str, object]:
        mqtt_status = (
            app.state.mqtt.status() if app.state.mqtt is not None else {"state": "disabled"}
        )
        return {
            "status": "degraded" if mqtt_status["state"] not in {"connected", "disabled"} else "ok",
            "version": __version__,
            "time": utc_now().isoformat(),
            "mqtt": mqtt_status,
            "deviceRuntime": service.diagnostics(),
            "sessionId": events.session_id,
            "host": await host_diagnostics.snapshot(),
        }

    @app.get("/api/v1/diagnostics", dependencies=[Depends(authenticate)])
    async def diagnostics() -> dict[str, object]:
        return await service_status()

    @app.get("/api/v1/events/operations", dependencies=[Depends(authenticate)])
    async def operational_events() -> list[dict[str, object]]:
        return database.recent_events()

    @app.get("/api/v1/bluetooth", dependencies=[Depends(authenticate)])
    async def bluetooth() -> dict[str, object]:
        host = await host_diagnostics.snapshot()
        return {
            "available": (
                True if selected_adapter.source.value == "simulated" else host["bluetoothPowered"]
            ),
            "connected": selected_adapter.is_connected,
            "source": selected_adapter.source.value,
        }

    @app.post("/api/v1/scans", status_code=status.HTTP_202_ACCEPTED)
    async def start_scan(body: ScanRequest, _auth: protected) -> dict[str, object]:
        duration = body.duration or startup.bluetooth.scan_duration
        return service.start_scan(duration)

    @app.get("/api/v1/scans/{scan_id}")
    async def scan_result(scan_id: str, _auth: protected) -> dict[str, object]:
        return service.scan_result(scan_id)

    @app.get("/api/v1/devices")
    async def devices(_auth: protected) -> list[dict[str, object]]:
        return service.devices()

    @app.post("/api/v1/devices", status_code=status.HTTP_201_CREATED)
    async def register_device(body: RegisterDeviceRequest, _auth: protected) -> dict[str, object]:
        device = service.register(
            body.discovery_id, body.friendly_name, body.automatic_reconnection
        )
        if body.connect:
            operation = service.start_connection_operation(str(device["deviceId"]), "connect")
            return {
                "device": service.device(str(device["deviceId"])),
                "operation": operation,
            }
        return device

    @app.get("/api/v1/devices/{device_id}")
    async def device(device_id: str, _auth: protected) -> dict[str, object]:
        return service.device(device_id)

    @app.patch("/api/v1/devices/{device_id}")
    async def patch_device(
        device_id: str, body: PatchDeviceRequest, _auth: protected
    ) -> dict[str, object]:
        return service.patch_device(
            device_id,
            body.friendly_name,
            body.automatic_reconnection,
            body.discovery_id,
            update_friendly_name="friendly_name" in body.model_fields_set,
        )

    @app.delete("/api/v1/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_device(device_id: str, _auth: protected) -> Response:
        await service.delete_device(device_id)
        return Response(status_code=204)

    @app.post("/api/v1/devices/{device_id}/{action}", status_code=status.HTTP_202_ACCEPTED)
    async def connection_operation(
        device_id: str,
        action: Literal["connect", "disconnect", "reconnect"],
        _auth: protected,
    ) -> dict[str, object]:
        return service.start_connection_operation(device_id, action)

    @app.get("/api/v1/devices/{device_id}/probes")
    async def probes(device_id: str, _auth: protected) -> list[dict[str, object]]:
        return service.probes(device_id)

    @app.get("/api/v1/devices/{device_id}/battery")
    async def battery(device_id: str, _auth: protected) -> dict[str, object] | None:
        return service.battery(device_id)

    @app.get("/api/v1/operations")
    async def operations(_auth: protected) -> list[dict[str, object]]:
        return service.operations()

    @app.get("/api/v1/operations/{operation_id}")
    async def operation(operation_id: str, _auth: protected) -> dict[str, object]:
        return service.operation(operation_id)

    @app.get("/api/v1/events")
    async def recent_events(_auth: protected) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json", by_alias=True) for event in events.recent()]

    @app.get("/api/v1/events/stream")
    async def event_stream(_auth: protected) -> StreamingResponse:
        nonlocal sse_clients
        if sse_clients >= startup.security.maximum_sse_clients:
            raise ThrottledError(5)
        sse_clients += 1

        class LimitedStream(StreamingResponse):
            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                nonlocal sse_clients
                try:
                    await super().__call__(scope, receive, send)
                finally:
                    sse_clients -= 1

        return LimitedStream(
            events.stream(heartbeat=startup.polling.availability_heartbeat),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/config")
    async def get_config(response: Response, _auth: protected) -> dict[str, Any]:
        response.headers["etag"] = f'"{config.version}"'
        return config_response()

    @app.get("/api/v1/config/schema")
    async def config_schema(_auth: protected) -> dict[str, Any]:
        return config_response()

    @app.post("/api/v1/config/validate")
    async def validate_config(body: ConfigPatchRequest, _auth: protected) -> dict[str, bool]:
        config.validate_patch(body.values)
        return {"valid": True}

    @app.patch("/api/v1/config")
    async def patch_config(
        body: ConfigPatchRequest,
        response: Response,
        _auth: protected,
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    ) -> dict[str, Any]:
        if if_match is None:
            raise StateConflictError("If-Match header required")
        try:
            expected = int(if_match.strip('"'))
        except ValueError as exc:
            raise StateConflictError("configuration version is invalid") from exc
        try:
            if body.values.get("auth.mode") == "token" and not tokens.status().configured:
                raise StateConflictError("rotate an administrator token before enabling token mode")
            config.update(body.values, expected)
        except VersionConflictError as exc:
            raise StateConflictError(
                f"configuration version conflict; current version is {exc.current_version}"
            ) from exc
        response.headers["etag"] = f'"{config.version}"'
        await events.publish(
            TelemetryEvent(
                type=EventType.CONFIGURATION,
                sequence=config.version,
                source=selected_adapter.source,
                data={"version": config.version, "settings": sorted(body.values)},
            )
        )
        return config_response()

    @app.put("/api/v1/config/secrets/{secret_name}")
    async def put_secret(
        secret_name: Literal["mqtt.password"], body: SecretRequest, _auth: protected
    ) -> dict[str, object]:
        changed_at = utc_now().isoformat()
        database.put_secret(secret_name, body.value, changed_at)
        return {"name": secret_name, "configured": True, "changedAt": changed_at}

    @app.delete("/api/v1/config/secrets/{secret_name}")
    async def delete_secret(
        secret_name: Literal["mqtt.password"], _auth: protected
    ) -> dict[str, object]:
        database.delete_secret(secret_name)
        return {"name": secret_name, "configured": False, "changedAt": None}

    @app.post("/api/v1/auth/token/rotate")
    async def rotate_token(_auth: protected) -> dict[str, str]:
        return {"token": tokens.rotate()}

    return app


def run() -> None:
    """Run the native development server using the effective startup configuration."""
    import uvicorn

    from pitboss_admin.deployment import startup_configuration
    from pitboss_admin.server import GracefulServer

    database_path = Path(os.environ.get("PITBOSS_DATABASE_PATH", "pitboss-admin.sqlite3"))
    store = AdministrativeStore(database_path)
    try:
        configuration = startup_configuration(store, os.environ)
        application = create_app(store=store, configuration=configuration)
        config: ConfigurationManager = application.state.configuration
        bootstrap_token: str | None = application.state.bootstrap_token
        if bootstrap_token is not None:
            print(f"Initial administrator token (shown once): {bootstrap_token}")
        server_config = uvicorn.Config(
            application,
            host=config.config.server.bind,
            port=config.config.server.port,
            access_log=False,
            timeout_graceful_shutdown=15,
        )
        GracefulServer(server_config, application.state.events).run()
    except Exception:
        raise SystemExit(
            "Service startup/runtime failed; inspect safe configuration and diagnostics."
        ) from None
    finally:
        store.close()


class AuthenticationError(Exception):
    pass


class ThrottledError(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
