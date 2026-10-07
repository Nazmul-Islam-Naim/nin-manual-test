import uuid
from datetime import datetime, timezone

from app.errors import AppError
from app.models import TestRun
from app.repositories.manual_repository import ManualRepository
from app.repositories.test_run_repository import TestRunRepository
from app.services.url_check import UrlChecker, normalize_url


class TestRunService:
    __test__ = False  # not a pytest class

    def __init__(self, runs: TestRunRepository, manuals: ManualRepository, checker: UrlChecker):
        self.runs, self.manuals, self.checker = runs, manuals, checker

    def create(self, manual_id: str, url: str) -> tuple[TestRun, str | None]:
        if self.manuals.get(manual_id) is None:
            raise AppError(404, "manual_not_found", "Manual not found.")
        base_url = normalize_url(url)
        warning = self.checker.check(base_url)
        run = self.runs.add(TestRun(
            id=str(uuid.uuid4()), manual_id=manual_id, base_url=base_url, status="created",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        return run, warning

    def get(self, run_id: str) -> TestRun:
        run = self.runs.get(run_id)
        if run is None:
            raise AppError(404, "test_run_not_found", "Test run not found.")
        return run
