import json
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.models import Step, TestCase
from app.repositories.parse_repository import ParseRepository
from app.services.llm.base import LLMError, LLMProvider

Action = Literal["open", "click", "type", "select", "check", "assert_text", "assert_visible", "wait"]


class ParsedStep(BaseModel):
    order: int
    action: Action
    target: str
    value: str | None = None
    expected: str | None = None
    unclear: bool = False


class ParsedCase(BaseModel):
    title: str
    steps: list[ParsedStep]


class ParsedManual(BaseModel):
    test_cases: list[ParsedCase]


class ParsedRule(BaseModel):
    field: str
    rule: str | None = None
    valid: list[str] = []
    invalid: list[str] = []


def clean_rules(raw) -> list[dict]:
    """Lenient: a bad field_rules (or bad item) is dropped, never fails the parse. Examples capped at 5."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        try:
            r = ParsedRule.model_validate(item)
        except ValidationError:
            continue
        if r.field.strip():
            out.append({"field": r.field.strip(), "rule": r.rule, "valid": r.valid[:5], "invalid": r.invalid[:5]})
    return out


SYSTEM_PROMPT = """You convert a QA test manual into structured test cases for an automated browser executor.
Rules:
- Extract ONLY what the manual states. Never invent steps, targets or values.
- Keep the manual's own language (e.g. Bangla) for title, target, value and expected text. The "action" is always English.
- action must be one of: open, click, type, select, check, assert_text, assert_visible, wait.
- Mark anything vague or ambiguous with "unclear": true.
- Keep scenarios and steps in the manual's original order; step "order" starts at 1 within each test case.
- Also extract field-level rules and example values the manual states (e.g. "Phone must be 11 digits starting with 01"): field name as the manual calls it, the rule text, up to 5 valid and up to 5 invalid example values. Do NOT invent rules or examples; use [] when there are none.
- Reply with ONLY one JSON object, no prose, no code fences, exactly of this shape:
{"test_cases":[{"title":str,"steps":[{"order":int,"action":str,"target":str,"value":str|null,"expected":str|null,"unclear":bool}]}],"field_rules":[{"field":str,"rule":str|null,"valid":[str],"invalid":[str]}]}"""


def chunk_text(text: str, limit: int) -> list[str]:
    """Split at paragraph boundaries (blank lines); an oversized paragraph is cut at the char limit."""
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", text.strip()):
        for piece in [para[i:i + limit] for i in range(0, len(para), limit)] or [""]:
            if cur and len(cur) + len(piece) + 2 > limit:
                chunks.append(cur)
                cur = ""
            cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


def _extract_json(raw: str) -> dict:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    a, b = s.find("{"), s.rfind("}")
    return json.loads(s[a:b + 1])


class ParseFailed(Exception):
    """str(exception) becomes the run error."""


class ParsingService:
    def __init__(self, repo: ParseRepository, provider: LLMProvider, chunk_chars: int):
        self.repo, self.provider, self.chunk_chars = repo, provider, chunk_chars

    def _parse_chunk(self, chunk: str) -> tuple[ParsedManual, list[dict]]:
        last = ""
        for _ in range(2):  # one retry on schema mismatch
            raw = self.provider.complete(SYSTEM_PROMPT, f"Manual:\n\n{chunk}")
            try:
                data = _extract_json(raw)
                return ParsedManual.model_validate(data), clean_rules(data.get("field_rules"))
            except (ValueError, ValidationError) as e:  # JSONDecodeError is a ValueError
                last = e.__class__.__name__
        raise ParseFailed(f"The model output did not match the required schema after a retry ({last}).")

    def parse_run(self, run_id: str) -> None:
        run = self.repo.get_run(run_id)
        manual = self.repo.get_manual(run.manual_id) if run else None
        if run is None or manual is None:
            return
        self.repo.set_status_if(run_id, "parsing", ("created", "parsed", "failed", "done"))
        try:
            cases: list[ParsedCase] = []
            rules: list[dict] = []
            for chunk in chunk_text(manual.text, self.chunk_chars):
                parsed, chunk_rules = self._parse_chunk(chunk)
                cases += parsed.test_cases
                rules += chunk_rules
            if not cases:
                raise ParseFailed("No test cases could be extracted from the manual.")
            rows = []
            for ci, c in enumerate(cases, 1):
                tc = TestCase(id=str(uuid.uuid4()), run_id=run_id, title=c.title, order=ci)
                steps = [Step(id=str(uuid.uuid4()), test_case_id=tc.id, order=i, action=s.action,
                              target=s.target, value=s.value, expected=s.expected, unclear=s.unclear)
                         for i, s in enumerate(sorted(c.steps, key=lambda s: s.order), 1)]
                rows.append((tc, steps))
            self.repo.save_parsed(run_id, rows, rules)
        except (ParseFailed, LLMError) as e:
            self.repo.set_status_if(run_id, "failed", ("parsing",), str(e))
        except Exception:  # never leave a run stuck in "parsing"
            self.db_rollback_and_fail(run_id)

    def db_rollback_and_fail(self, run_id: str) -> None:
        self.repo.db.rollback()
        self.repo.set_status_if(run_id, "failed", ("parsing",), "Unexpected error while parsing the manual.")
