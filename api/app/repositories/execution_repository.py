import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import Step, StepResult, TestCase, TestRun

SWEEP_TITLE = "Menu sweep"


class ExecutionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_run(self, run_id: str) -> TestRun | None:
        return self.db.get(TestRun, run_id)

    def set_status(self, run_id: str, status: str, error: str | None = None) -> None:
        run = self.db.get(TestRun, run_id)
        run.status, run.error = status, error
        if status in ("done", "failed"):
            run.finished_at = datetime.utcnow()
        self.db.commit()

    def start(self, run_id: str, max_minutes: int | None = None) -> None:
        """Mark running and drop the previous sweep (re-run replaces it)."""
        self._clear_sweep(run_id)
        run = self.db.get(TestRun, run_id)
        run.status, run.error, run.sweep_note = "running", None, None
        run.started_at, run.finished_at, run.max_minutes = datetime.utcnow(), None, max_minutes
        self.db.commit()

    def begin(self, run_id: str, default_minutes: int) -> None:
        """Executor start: stamp started_at; keep the limit chosen at execute time, else store the effective one."""
        run = self.db.get(TestRun, run_id)
        run.started_at, run.finished_at = datetime.utcnow(), None
        run.max_minutes = run.max_minutes or default_minutes
        self.db.commit()

    def pending_count(self, run_id: str) -> int:
        """Sweep steps without a final result (not visited yet)."""
        q = (select(func.count()).select_from(Step).join(TestCase, TestCase.id == Step.test_case_id)
             .outerjoin(StepResult, StepResult.step_id == Step.id)
             .where(TestCase.run_id == run_id, TestCase.title == SWEEP_TITLE,
                    Step.action.in_(("visit_menu", "submit_form", "click_action")),
                    StepResult.status.is_(None) | StepResult.status.notin_(("passed", "failed", "warning"))))
        return self.db.scalar(q) or 0

    def _clear_sweep(self, run_id: str) -> None:
        case_ids = select(TestCase.id).where(TestCase.run_id == run_id, TestCase.title == SWEEP_TITLE)
        step_ids = select(Step.id).where(Step.test_case_id.in_(case_ids))
        self.db.execute(delete(StepResult).where(StepResult.step_id.in_(step_ids)))
        self.db.execute(delete(Step).where(Step.test_case_id.in_(case_ids)))
        self.db.execute(delete(TestCase).where(TestCase.id.in_(case_ids)))

    def create_sweep(self, run_id: str, menus: list[tuple[str, str | None]], note: str | None) -> list[str]:
        order = len(self.db.scalars(select(TestCase.id).where(TestCase.run_id == run_id)).all()) + 1
        tc = TestCase(id=str(uuid.uuid4()), run_id=run_id, title=SWEEP_TITLE, order=order)
        steps = [Step(id=str(uuid.uuid4()), test_case_id=tc.id, order=i, action="visit_menu", target=label,
                      value=href, expected=None, unclear=False) for i, (label, href) in enumerate(menus, 1)]
        self.db.add(tc)
        self.db.flush()
        self.db.add_all(steps)
        self.db.get(TestRun, run_id).sweep_note = note
        self.db.commit()
        return [s.id for s in steps]

    def set_note(self, run_id: str, note: str | None) -> None:
        self.db.get(TestRun, run_id).sweep_note = note
        self.db.commit()

    def group_end(self, menu_step_id: str) -> str:
        """Id of the last step that belongs to a menu (the menu step plus its form/case/action steps)."""
        anchor = self.db.get(Step, menu_step_id)
        later = self.db.scalars(select(Step).where(Step.test_case_id == anchor.test_case_id, Step.order > anchor.order)
                                .order_by(Step.order))
        last = anchor
        for s in later:
            if s.action == "visit_menu":
                break
            last = s
        return last.id

    def add_form_steps(self, after_step_id: str, rows: list[tuple], action: str = "submit_form") -> list[str]:
        """Insert steps (submit_form, or click_action) right after the given step; later steps shift.
        row = (target, value[, expected[, meta]])"""
        anchor = self.db.get(Step, after_step_id)
        self.db.execute(update(Step).where(Step.test_case_id == anchor.test_case_id, Step.order > anchor.order)
                        .values(order=Step.order + len(rows)))
        steps = []
        for i, (t, v, *rest) in enumerate(rows, 1):
            steps.append(Step(id=str(uuid.uuid4()), test_case_id=anchor.test_case_id, order=anchor.order + i,
                              action=action, target=t, value=v, expected=rest[0] if rest else None,
                              unclear=False, meta=rest[1] if len(rest) > 1 else None))
        self.db.add_all(steps)
        self.db.commit()
        return [s.id for s in steps]

    def save_result(self, step_id: str, **fields) -> None:
        row = self.db.scalar(select(StepResult).where(StepResult.step_id == step_id))
        if row is None:
            row = StepResult(id=str(uuid.uuid4()), step_id=step_id, console_errors=0, failed_requests=0)
            self.db.add(row)
        for k, v in fields.items():
            setattr(row, k, v)
        self.db.commit()

    def results_for_run(self, run_id: str) -> dict[str, StepResult]:
        q = (select(StepResult).join(Step, Step.id == StepResult.step_id)
             .join(TestCase, TestCase.id == Step.test_case_id).where(TestCase.run_id == run_id))
        return {r.step_id: r for r in self.db.scalars(q)}

    def fail_stale_running(self) -> None:
        run_ids = select(TestRun.id).where(TestRun.status == "running")
        step_ids = (select(Step.id).join(TestCase, TestCase.id == Step.test_case_id)
                    .where(TestCase.run_id.in_(run_ids)))
        self.db.execute(update(StepResult).where(StepResult.status == "running", StepResult.step_id.in_(step_ids))
                        .values(status="failed", error="Interrupted", error_type="interrupted"))
        self.db.execute(update(TestRun).where(TestRun.status == "running").values(status="failed", error="Interrupted",
                                                                                   finished_at=datetime.utcnow()))
        self.db.commit()
