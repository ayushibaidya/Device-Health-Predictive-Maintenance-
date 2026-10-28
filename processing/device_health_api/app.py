"""FastAPI application factory. All data-store connections stay server-side."""

import json
import sys
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

import redis
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from device_health_ingestion.errors import TransientProcessingError
from device_health_ingestion.latest import LatestState, configured_cache
from device_health_ingestion.queries import TelemetryQueries, time_bound
from device_health_ingestion.store import database_dsn

from .models import (
    DeviceDetail,
    DevicePage,
    ErrorResponse,
    FleetSummary,
    HistoryPage,
    Liveness,
    Readiness,
)

DeviceId = Annotated[str, Path(min_length=1, pattern=r"^[^\x00]+$")]
PageLimit = Annotated[int, Query(ge=1, le=1000)]


def get_queries(request: Request):
    queries = request.app.state.queries_factory(request.app.state.dsn)
    try:
        yield queries
    finally:
        queries.close()


Queries = Annotated[TelemetryQueries, Depends(get_queries)]


def error_response(status, code, message):
    body = ErrorResponse(error={"code": code, "message": message})
    return JSONResponse(status_code=status, content=body.model_dump())


def create_app(*, dsn=None, cache_factory=configured_cache, queries_factory=TelemetryQueries):
    @asynccontextmanager
    async def lifespan(app):
        try:
            app.state.dsn = dsn if dsn is not None else database_dsn()
            app.state.cache = cache_factory()
        except ValueError:
            raise RuntimeError("Invalid data-store configuration") from None
        app.state.queries_factory = queries_factory
        try:
            yield
        finally:
            if app.state.cache is not None:
                app.state.cache.close()

    app = FastAPI(
        title="Device Health API",
        version="1.0.0",
        lifespan=lifespan,
        description="Read-only access to simulated device data. Local development API.",
        responses={status: {"model": ErrorResponse} for status in (404, 422, 500, 503)},
    )

    @app.middleware("http")
    async def sanitize_unexpected_errors(request, call_next):
        try:
            return await call_next(request)
        except Exception as error:
            # Catch before the server middleware so Uvicorn cannot log a driver traceback.
            print(
                json.dumps({"event": "api_request_failed", "error_type": type(error).__name__}),
                file=sys.stderr,
                flush=True,
            )
            return error_response(500, "internal_error", "An internal error occurred.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_, error):
        messages = {
            404: ("not_found", "The requested resource was not found."),
            405: ("method_not_allowed", "The HTTP method is not allowed."),
            422: ("invalid_request", "Request parameters are invalid."),
            503: ("service_unavailable", "Durable storage is unavailable."),
        }
        code, message = messages.get(error.status_code, ("http_error", "Request failed."))
        response = error_response(error.status_code, code, message)
        if error.headers:
            response.headers.update(error.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_, __):
        return error_response(422, "invalid_request", "Request parameters are invalid.")

    @app.exception_handler(TransientProcessingError)
    async def storage_unavailable(_, __):
        return error_response(503, "service_unavailable", "Durable storage is unavailable.")

    @app.get("/health/live", response_model=Liveness, tags=["Health"])
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", response_model=Readiness, tags=["Health"])
    def ready(request: Request, queries: Queries):
        if not queries.ready():
            raise HTTPException(503)
        cache = request.app.state.cache
        cache_status = "disabled"
        if cache is not None:
            try:
                cache_status = "up" if cache.client.ping() else "degraded"
            except redis.RedisError:
                cache_status = "degraded"
        return {"status": "ready", "database": "up", "cache": cache_status}

    prefix = "/api/v1"

    @app.get(prefix + "/fleet/summary", response_model=FleetSummary, tags=["Fleet"])
    def fleet_summary(queries: Queries):
        return {"data_mode": "simulated", **queries.fleet_summary()}

    @app.get(
        prefix + "/devices",
        response_model=DevicePage,
        response_model_exclude_unset=True,
        tags=["Devices"],
    )
    def devices(
        queries: Queries,
        limit: PageLimit = 100,
        after_device: Annotated[str, Query(pattern=r"^[^\x00]*$")] = "",
    ):
        readings = queries.latest_page(after_device=after_device, limit=limit)
        next_device = None
        if len(readings) == limit:
            candidate = readings[-1].event["device_id"]
            if queries.latest_page(after_device=candidate, limit=1):
                next_device = candidate
        return {
            "data_mode": "simulated",
            "items": [row.as_dict() for row in readings],
            "next_after_device": next_device,
        }

    @app.get(
        prefix + "/devices/{device_id}",
        response_model=DeviceDetail,
        response_model_exclude_unset=True,
        tags=["Devices"],
    )
    def device(device_id: DeviceId, request: Request, queries: Queries):
        reading = LatestState(queries, request.app.state.cache).get(device_id)
        if reading is None:
            raise HTTPException(404)
        return {"data_mode": "simulated", **reading.as_dict()}

    @app.get(
        prefix + "/devices/{device_id}/telemetry",
        response_model=HistoryPage,
        response_model_exclude_unset=True,
        tags=["Devices"],
    )
    def history(
        device_id: DeviceId,
        queries: Queries,
        limit: PageLimit = 100,
        run_id: UUID | None = None,
        start: str | None = None,
        end: str | None = None,
        before: Annotated[int | None, Query(gt=0)] = None,
    ):
        # Validate all bounds before querying durable storage, using the existing parser.
        try:
            low, high = time_bound(start), time_bound(end)
            if low is not None and high is not None and low > high:
                raise ValueError("reversed range")
        except (ValueError, OverflowError):
            raise HTTPException(422) from None
        if queries.latest(device_id) is None:
            raise HTTPException(404)
        page = queries.history(
            device_id,
            run_id=str(run_id) if run_id else None,
            start=start,
            end=end,
            limit=limit,
            before=before,
        )
        return {"data_mode": "simulated", **page}

    return app
