import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import FieldRule, Manual, Step, TestCase, TestRun


class ParseRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_run(self, run_id: str) -> TestRun | None:
        return self.db.get(TestRun, run_id)

    def get_manual(self, manual_id: str) -> Manual | None:
        return self.db.get(Manual, manual_id)

    def set_status_if(self, run_id: str, status: str, expected: tuple[str, ...], error: str | None = None) -> bool:
        """Compare-and-set: only change the status when it is currently one of `expected` (never clobbers running)."""
        res = self.db.execute(update(TestRun).where(TestRun.id == run_id, TestRun.status.in_(expected))
                              .values(status=status, error=error))
        self.db.commit()
        return res.rowcount == 1

    def save_parsed(self, run_id: str, rows: list[tuple[TestCase, list[Step]]],
                    rules: list[dict] | None = None) -> None:
        """Adds cases after any existing ones (a concurrent sweep case may exist); status -> parsed only if still parsing."""
        base = self.db.scalar(select(func.max(TestCase.order)).where(TestCase.run_id == run_id)) or 0
        for tc, steps in rows:
            tc.order += base
            self.db.add(tc)
            self.db.add_all(steps)
        self.db.execute(delete(FieldRule).where(FieldRule.run_id == run_id))  # replaced on re-parse
        # id starts with the position so reading ordered by id keeps the manual's order
        self.db.add_all(FieldRule(id=f"{n:08x}-{str(uuid.uuid4())[9:]}", run_id=run_id, **r)
                        for n, r in enumerate(rules or []))
        self.db.execute(update(TestRun).where(TestRun.id == run_id, TestRun.status == "parsing")
                        .values(status="parsed", error=None))
        self.db.commit()

    def cases_with_steps(self, run_id: str) -> list[tuple[TestCase, list[Step]]]:
        cases = self.db.scalars(select(TestCase).where(TestCase.run_id == run_id).order_by(TestCase.order)).all()
        return [(c, list(self.db.scalars(select(Step).where(Step.test_case_id == c.id).order_by(Step.order))))
                for c in cases]

    def field_rules(self, run_id: str) -> list[FieldRule]:
        return list(self.db.scalars(select(FieldRule).where(FieldRule.run_id == run_id).order_by(FieldRule.id)))

    def has_manual_cases(self, run_id: str) -> bool:
        """True once the manual parse saved its cases (anything except the executor's own sweep case)."""
        return self.db.scalar(select(func.count()).select_from(TestCase)
                              .where(TestCase.run_id == run_id, TestCase.title != "Menu sweep")) > 0
