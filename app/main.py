import logging
import re

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import DatabaseError
from app.models import GaugeInstallation, Reading, UserPatch, parse_date
from app.repository import NotFound, Repository

app = FastAPI(title="ЭнергоСбыт", version="1.0.0")
repository = Repository()
logger = logging.getLogger(__name__)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    loc = exc.errors()[0]["loc"]
    name = str(loc[-1]) if len(loc) > 1 else "body"
    kind = "parameter" if loc and loc[0] == "query" else "field"
    return JSONResponse({"message": f'invalid "{name}" {kind}'}, status_code=400)


@app.exception_handler(NotFound)
async def not_found(request: Request, exc: NotFound):
    return JSONResponse({"message": "Not found"}, status_code=404)


@app.exception_handler(DatabaseError)
async def database_error(request: Request, exc: DatabaseError):
    logger.error("ClickHouse request failed", exc_info=True)
    return JSONResponse({"message": "Database unavailable"}, status_code=503)


def integer(value, name, *, minimum=0, kind="parameter"):
    if (
        len(value) > 20
        or not re.fullmatch(r"[0-9]+", value)
        or not minimum <= int(value) <= 2**64 - 1
    ):
        raise HTTPException(400, f'invalid "{name}" {kind}')
    return int(value)


def ident(value):
    return integer(value, "id", minimum=1)


def day_parameter(value, name):
    try:
        return parse_date(value)
    except (ValueError, TypeError):
        raise HTTPException(400, f'invalid "{name}" parameter') from None


@app.get("/ping", response_class=Response)
def ping():
    return Response(status_code=200)


@app.get("/users/{id}")
def user(id: str):
    value = repository.entity("dim_users", ident(id))
    return {key: value[key] for key in ("id", "fio", "phone", "phone_prev")}


@app.patch("/users/{id}", status_code=204, response_class=Response)
def patch_user(id: str, changes: UserPatch):
    repository.update_user(ident(id), changes.model_dump(exclude_unset=True))
    return Response(status_code=204)


@app.get("/realty/{id}")
def realty(id: str):
    value = repository.entity("dim_realty", ident(id))
    return {key: val for key, val in value.items() if key != "created_at"}


@app.post("/realty/{id}/readings", status_code=201, response_class=Response)
def post_reading(id: str, reading: Reading):
    repository.add_reading(ident(id), reading.model_dump(mode="json"))
    return Response(status_code=201)


@app.get("/realty/{id}/readings")
def readings(id: str, date_from: str | None = None, date_to: str | None = None):
    start, end = day_parameter(date_from, "date_from"), day_parameter(date_to, "date_to")
    if start > end:
        raise HTTPException(400, 'invalid "date_to" parameter')
    rows = repository.readings(ident(id), start, end)
    return {"readings": rows, "count": len(rows)}


@app.get("/realty/{id}/invoices")
def invoices(id: str, limit: str = "10", offset: str = "0"):
    return repository.invoices(ident(id), integer(limit, "limit"), integer(offset, "offset"))


@app.get("/tariffs")
def tariff(date: str | None = None):
    day = day_parameter(date, "date").isoformat()
    return repository.tariff(day)


@app.post("/realty/{id}/gauges", status_code=201, response_class=Response)
def install_gauge(id: str, installation: GaugeInstallation):
    repository.install_gauge(ident(id), installation.gauge_id)
    return Response(status_code=201)
