import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from app.config import get_settings
from app.errors import AppError
from app.repositories.execution_repository import ExecutionRepository

API_ROOT = Path(__file__).resolve().parents[2]


def spawn_executor(run_id: str, credentials: dict | None, submit_forms: bool | None = None,
                   validation_depth: str | None = None, test_actions: bool | None = None,
                   fast_mode: bool | None = None) -> None:
    """Separate process (own event loop, own desktop window). Credentials go via stdin only."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(API_ROOT), os.environ.get("PYTHONPATH")]))}
    p = subprocess.Popen([sys.executable, "-m", "app.services.executor", run_id], stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    p.stdin.write(json.dumps({"credentials": credentials, "submit_forms": submit_forms,
                               "validation_depth": validation_depth,
                               "test_actions": test_actions, "fast_mode": fast_mode}).encode())
    p.stdin.close()


class ExecutionService:
    def __init__(self, repo: ExecutionRepository, spawn: Callable[..., None]):
        self.repo, self.spawn = repo, spawn

    def execute(self, run_id: str, credentials: dict | None, submit_forms: bool | None = None,
                validation_depth: str | None = None, test_actions: bool | None = None,
                max_minutes: int | None = None, fast_mode: bool | None = None) -> None:
        run = self.repo.get_run(run_id)
        if run is None:
            raise AppError(404, "test_run_not_found", "Test run not found.")
        if run.status == "running":  # parsing may continue concurrently (it never touches the sweep)
            raise AppError(409, "run_busy", "This run is already running.")
        limit = max_minutes or max(1, round(get_settings().exec_overall_timeout_s / 60))
        self.repo.start(run_id, limit)
        try:
            self.spawn(run_id, credentials, submit_forms, validation_depth, test_actions, fast_mode)
        except OSError as e:
            self.repo.set_status(run_id, "failed", f"Could not start the executor: {e}")
            raise AppError(500, "executor_start_failed", "Could not start the executor.")
