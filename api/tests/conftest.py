import os
import tempfile

_tmp = tempfile.mkdtemp()
# must be set before importing app (settings and engine are created at import time)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["MAX_UPLOAD_MB"] = "1"
os.environ["EXEC_HEADED"] = "false"  # never open a visible window in tests
os.environ["EXEC_SLOW_MO_MS"] = "0"
os.environ["EXEC_TEST_ACTIONS"] = "false"  # action sweep is enabled per test
os.environ["EXEC_VALIDATION_DEPTH"] = "basic"  # keeps older form tests fast; matrix tests pass a depth

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class FakeProvider:
    """Replaces every LLM provider: no real LLM/network calls in tests. Set .replies (str or Exception)."""

    def __init__(self):
        self.replies, self.calls = [], []

    def complete(self, system, user):
        self.calls.append(user)
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def llm_fake(monkeypatch):
    from app.services import llm
    fake = FakeProvider()
    fake.replies = ['{"test_cases":[{"title":"T","steps":[{"order":1,"action":"open","target":"home"}]}]}']
    monkeypatch.setattr(llm, "get_provider", lambda: fake)
    return fake


@pytest.fixture
def client():
    with TestClient(app) as c:  # context manager runs lifespan (creates tables)
        yield c
