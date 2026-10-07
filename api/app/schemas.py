from datetime import datetime, timezone

from pydantic import BaseModel

from app.models import Manual, TestRun


def _utc(d: datetime | None) -> str | None:
    return d.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if d else None


def _iso(m) -> str:
    return _utc(m.created_at)


class ManualCreated(BaseModel):
    id: str
    source_type: str
    original_filename: str | None
    char_count: int
    created_at: str

    @classmethod
    def from_model(cls, m: Manual) -> "ManualCreated":
        return cls(id=m.id, source_type=m.source_type, original_filename=m.original_filename,
                   char_count=len(m.text), created_at=_iso(m))


class ManualOut(ManualCreated):
    text: str

    @classmethod
    def from_model(cls, m: Manual) -> "ManualOut":
        return cls(id=m.id, source_type=m.source_type, original_filename=m.original_filename,
                   char_count=len(m.text), text=m.text, created_at=_iso(m))


class TestRunOut(BaseModel):
    id: str
    manual_id: str
    base_url: str
    status: str
    error: str | None = None
    created_at: str
    warning: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    max_minutes: int | None = None

    @classmethod
    def from_model(cls, r: TestRun, warning: str | None = None) -> "TestRunOut":
        return cls(id=r.id, manual_id=r.manual_id, base_url=r.base_url, status=r.status, error=r.error,
                   created_at=_iso(r), warning=warning, started_at=_utc(r.started_at),
                   finished_at=_utc(r.finished_at), max_minutes=r.max_minutes)


class ConsoleMessage(BaseModel):
    type: str
    text: str
    location: str | None = None


class FailedRequest(BaseModel):
    method: str
    url: str
    status: int


class ResultDetails(BaseModel):
    console_messages: list[ConsoleMessage] = []
    failed_requests: list[FailedRequest] = []
    excerpt: str | None = None


class StepResultOut(BaseModel):
    status: str
    error: str | None
    http_status: int | None
    console_errors: int
    failed_requests: int
    duration_ms: int | None
    error_type: str | None = None
    page_url: str | None = None
    details: ResultDetails | None = None


class StepMeta(BaseModel):
    kind: str
    category: str
    field: str | None = None
    form: str | None = None
    source: str = "auto"


class StepOut(BaseModel):
    id: str
    order: int
    action: str
    target: str
    value: str | None
    expected: str | None
    unclear: bool
    result: StepResultOut | None = None
    meta: StepMeta | None = None


class TestCaseOut(BaseModel):
    id: str
    title: str
    order: int
    steps: list[StepOut]


class SummaryOut(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    warning: int = 0
    pending: int = 0


class FieldRuleOut(BaseModel):
    field: str
    rule: str | None = None
    valid: list[str] = []
    invalid: list[str] = []


class StepsOut(BaseModel):
    run_id: str
    status: str
    test_cases: list[TestCaseOut]
    summary: SummaryOut
    note: str | None = None
    field_rules: list[FieldRuleOut] = []
    started_at: str | None = None
    finished_at: str | None = None
    max_minutes: int | None = None
