from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (register tables)
from sqlalchemy import inspect, text

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.repositories.execution_repository import ExecutionRepository
from app.errors import register_error_handlers
from app.routers import manuals, test_runs


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    # create_all never alters existing tables: add newer test_runs columns to older DBs
    cols = {c["name"] for c in inspect(engine).get_columns("test_runs")}
    with engine.begin() as conn:
        for col in ("error", "sweep_note"):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE test_runs ADD COLUMN {col} TEXT"))
        for col, typ in (("started_at", "DATETIME"), ("finished_at", "DATETIME"), ("max_minutes", "INTEGER")):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE test_runs ADD COLUMN {col} {typ}"))
    cols = {c["name"] for c in inspect(engine).get_columns("step_results")}
    with engine.begin() as conn:
        for col, typ in (("error_type", "VARCHAR(32)"), ("page_url", "TEXT"), ("details", "JSON")):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE step_results ADD COLUMN {col} {typ}"))
    if "meta" not in {c["name"] for c in inspect(engine).get_columns("steps")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE steps ADD COLUMN meta JSON"))
    with SessionLocal() as db:
        ExecutionRepository(db).fail_stale_running()
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Manual input API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
register_error_handlers(app)
app.include_router(manuals.router)
app.include_router(test_runs.router)
