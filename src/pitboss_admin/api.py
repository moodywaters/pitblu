"""FastAPI control plane for pitboss-admin."""

from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pitboss_admin import __version__
from pitboss_admin.adapters.base import DeviceAdapter
from pitboss_admin.adapters.igrill_v202 import BleakIGrillV202Adapter
from pitboss_admin.adapters.simulated import SimulatedIGrillAdapter
from pitboss_admin.auth import AdministratorTokens
from pitboss_admin.configuration import ConfigurationManager, ConfigurationValueError
from pitboss_admin.models import utc_now
from pitboss_admin.service import (
    AdministrationService,
    ResourceNotFoundError,
    StateConflictError,
)
from pitboss_admin.storage import AdministrativeStore, VersionConflictError


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
    selected_adapter = adapter or (
        SimulatedIGrillAdapter(config.config.simulation.probe_count)
        if config.config.simulation.enabled
        else BleakIGrillV202Adapter(
            connect_timeout=config.config.bluetooth.connect_timeout,
            initialise_timeout=config.config.bluetooth.initialise_timeout,
            read_timeout=config.config.bluetooth.read_timeout,
        )
    )
    service = AdministrationService(selected_adapter, database)
    tokens = AdministratorTokens(database)
    bootstrap_token = None
    if config.config.auth.mode == "token" and not tokens.status().configured:
        bootstrap_token = tokens.bootstrap()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        yield
        await service.close()

    app = FastAPI(title="pitboss-admin", version=__version__, lifespan=lifespan)
    app.state.service = service
    app.state.configuration = config
    app.state.tokens = tokens
    app.state.bootstrap_token = bootstrap_token

    if config.config.server.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.config.server.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "If-Match"],
        )

    @app.middleware("http")
    async def correlation(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.correlation_id = request.headers.get("x-correlation-id") or uuid4().hex
        response = await call_next(request)
        response.headers["x-correlation-id"] = request.state.correlation_id
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
        if config.config.auth.mode == "disabled":
            return
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not tokens.verify(token):
            raise AuthenticationError

    @app.exception_handler(Exception)
    async def safe_exception(request: Request, exc: Exception) -> JSONResponse:
        return _error(request, "internal_error", "internal service error", 500)

    protected = Annotated[None, Depends(authenticate)]

    def config_response() -> dict[str, Any]:
        configured, changed_at = database.secret_status("mqtt.password")
        return config.describe() | {
            "secrets": {"mqtt.password": {"configured": configured, "changedAt": changed_at}}
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", dependencies=[Depends(authenticate)])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/v1/status", dependencies=[Depends(authenticate)])
    async def service_status() -> dict[str, object]:
        return {"status": "ok", "version": __version__, "time": utc_now().isoformat()}

    @app.get("/api/v1/bluetooth", dependencies=[Depends(authenticate)])
    async def bluetooth() -> dict[str, object]:
        return {
            "available": True,
            "connected": selected_adapter.is_connected,
            "source": selected_adapter.source.value,
        }

    @app.post("/api/v1/scans", status_code=status.HTTP_202_ACCEPTED)
    async def start_scan(body: ScanRequest, _auth: protected) -> dict[str, object]:
        duration = body.duration or config.config.bluetooth.scan_duration
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
            return {"device": device, "operation": operation}
        return device

    @app.get("/api/v1/devices/{device_id}")
    async def device(device_id: str, _auth: protected) -> dict[str, object]:
        return service.device(device_id)

    @app.patch("/api/v1/devices/{device_id}")
    async def patch_device(
        device_id: str, body: PatchDeviceRequest, _auth: protected
    ) -> dict[str, object]:
        return service.patch_device(device_id, body.friendly_name, body.automatic_reconnection)

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
    async def events(_auth: protected) -> list[object]:
        return []

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

    config: ConfigurationManager = app.state.configuration
    bootstrap_token: str | None = app.state.bootstrap_token
    if bootstrap_token is not None:
        print(f"Initial administrator token (shown once): {bootstrap_token}")
    uvicorn.run(
        app,
        host=config.config.server.bind,
        port=config.config.server.port,
        access_log=False,
    )


class AuthenticationError(Exception):
    pass


app = create_app()
