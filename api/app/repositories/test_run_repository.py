from sqlalchemy.orm import Session

from app.models import TestRun


class TestRunRepository:
    __test__ = False  # not a pytest class

    def __init__(self, db: Session):
        self.db = db

    def add(self, run: TestRun) -> TestRun:
        self.db.add(run)
        self.db.commit()
        return run

    def get(self, run_id: str) -> TestRun | None:
        return self.db.get(TestRun, run_id)
