from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field, StrictBool, StrictStr

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.repositories.manual_repository import ManualRepository
from app.repositories.test_run_repository import TestRunRepository
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.parse_repository import ParseRepository
from app.schemas import _utc, FieldRuleOut, StepOut, StepResultOut, StepsOut, SummaryOut, TestCaseOut, TestRunOut
from app.services import llm
from app.services.execution_service import ExecutionService, spawn_executor
from app.services.llm import LLMError
from app.services.parsing_service import ParsingService
from app.services.test_run_service import TestRunService
from app.services.url_check import UrlChecker

router = APIRouter(prefix="/test-runs", tags=["test-runs"])


class RunCreate(BaseModel):
    manual_id: StrictStr
    url: StrictStr


def get_url_checker() -> UrlChecker:  # overridable in tests
    s = get_settings()
    return UrlChecker(s.allow_private_urls, s.url_check_timeout_s)


def get_service(db=Depends(get_db), checker: UrlChecker = Depends(get_url_checker)) -> TestRunService:
    return TestRunService(TestRunRepository(db), ManualRepository(db), checker)


def get_execution_service(db=Depends(get_db)) -> ExecutionService:  # spawner overridable in tests
    return ExecutionService(ExecutionRepository(db), spawn_executor)


def parse_in_background(run_id: str) -> None:
    """Own DB session: the request session is closed by the time this runs."""
    with SessionLocal() as db:
        repo = ParseRepository(db)
        try:
            provider = llm.get_provider()
        except LLMError as e:
            repo.set_status_if(run_id, "failed", ("created", "parsing"), str(e))
            return
        ParsingService(repo, provider, get_settings().parse_chunk_chars).parse_run(run_id)


# sync handlers: FastAPI runs them in a threadpool, so the blocking httpx call doesn't stall the loop
@router.post("", status_code=201, response_model=TestRunOut)
def create_test_run(body: RunCreate, bg: BackgroundTasks, svc: TestRunService = Depends(get_service)):
    run, warning = svc.create(body.manual_id, body.url)
    bg.add_task(parse_in_background, run.id)
    return TestRunOut.from_model(run, warning)


@router.get("/{run_id}", response_model=TestRunOut)
def get_test_run(run_id: str, svc: TestRunService = Depends(get_service)):
    return TestRunOut.from_model(svc.get(run_id))


@router.get("/{run_id}/steps", response_model=StepsOut)
def get_steps(run_id: str, svc: TestRunService = Depends(get_service), db=Depends(get_db)):
    run = svc.get(run_id)
    results = ExecutionRepository(db).results_for_run(run_id)
    summary = SummaryOut()
    cases = []
    for c, st in ParseRepository(db).cases_with_steps(run_id):
        steps = []
        for s in st:
            r = results.get(s.id)
            out = StepOut.model_validate(s, from_attributes=True)
            out.result = StepResultOut.model_validate(r, from_attributes=True) if r else None
            steps.append(out)
            if s.action in ("visit_menu", "submit_form", "click_action"):
                summary.total += 1
                # not visited yet or being visited now both count as pending
                key = r.status if r and r.status in ("passed", "failed", "warning") else "pending"
                setattr(summary, key, getattr(summary, key) + 1)
        cases.append(TestCaseOut(id=c.id, title=c.title, order=c.order, steps=steps))
    rules = [FieldRuleOut.model_validate(r, from_attributes=True) for r in ParseRepository(db).field_rules(run_id)]
    return StepsOut(run_id=run.id, status=run.status, test_cases=cases, summary=summary, note=run.sweep_note,
                    field_rules=rules, started_at=_utc(run.started_at), finished_at=_utc(run.finished_at),
                    max_minutes=run.max_minutes)


class Credentials(BaseModel):
    username: StrictStr
    password: StrictStr


class ExecuteBody(BaseModel):
    credentials: Credentials | None = None
    submit_forms: StrictBool | None = None  # None -> EXEC_SUBMIT_FORMS (default true)
    test_actions: StrictBool | None = None  # None -> EXEC_TEST_ACTIONS (default true)
    validation_depth: Literal["basic", "standard", "thorough"] | None = None  # None -> EXEC_VALIDATION_DEPTH
    max_minutes: Annotated[int, Field(strict=True, ge=1, le=240)] | None = None  # None -> EXEC_OVERALL_TIMEOUT_S
    fast_mode: StrictBool | None = None  # None -> false


@router.post("/{run_id}/execute", status_code=202)
def execute(run_id: str, body: ExecuteBody | None = None, svc: ExecutionService = Depends(get_execution_service)):
    creds = body.credentials.model_dump() if body and body.credentials else None
    svc.execute(run_id, creds, body.submit_forms if body else None, body.validation_depth if body else None,
                body.test_actions if body else None, body.max_minutes if body else None,
                body.fast_mode if body else None)
    return {"id": run_id, "status": "running"}
