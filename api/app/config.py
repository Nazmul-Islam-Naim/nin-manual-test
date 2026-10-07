import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_dir: Path
    max_upload_bytes: int
    cors_origins: list[str]
    allow_private_urls: bool
    url_check_timeout_s: float
    llm_provider: str
    anthropic_api_key: str
    anthropic_model: str
    openrouter_api_key: str
    openrouter_model: str
    gemini_api_key: str
    gemini_model: str
    claude_cli_model: str
    claude_cli_timeout_s: float
    parse_chunk_chars: int
    llm_http_timeout_s: float
    exec_headed: bool
    exec_slow_mo_ms: int
    max_menus: int
    exec_page_timeout_s: float
    exec_overall_timeout_s: float
    exec_submit_forms: bool
    max_forms_per_page: int
    max_forms: int
    exec_validation_depth: str
    max_cases_per_form: int
    max_cases: int
    exec_test_actions: bool
    max_actions_per_page: int
    max_actions: int
    action_deny_extra: tuple[str, ...]


def _depth(v: str) -> str:
    v = v.strip().lower()
    return v if v in ("basic", "standard", "thorough") else "thorough"  # bad env value -> default


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/app.db"),
        storage_dir=Path(os.getenv("STORAGE_DIR", "./storage")),
        max_upload_bytes=int(float(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
        allow_private_urls=os.getenv("ALLOW_PRIVATE_URLS", "true").strip().lower() in ("1", "true", "yes"),
        url_check_timeout_s=float(os.getenv("URL_CHECK_TIMEOUT_S", "10")),
        llm_provider=os.getenv("LLM_PROVIDER", "claude_cli").strip().lower(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        claude_cli_model=os.getenv("CLAUDE_CLI_MODEL", "sonnet"),
        claude_cli_timeout_s=float(os.getenv("CLAUDE_CLI_TIMEOUT_S", "600")),
        parse_chunk_chars=int(os.getenv("PARSE_CHUNK_CHARS", "12000")),
        llm_http_timeout_s=float(os.getenv("LLM_HTTP_TIMEOUT_S", "120")),
        exec_headed=os.getenv("EXEC_HEADED", "true").strip().lower() in ("1", "true", "yes"),
        exec_slow_mo_ms=int(os.getenv("EXEC_SLOW_MO_MS", "300")),
        max_menus=int(os.getenv("MAX_MENUS", "30")),
        exec_page_timeout_s=float(os.getenv("EXEC_PAGE_TIMEOUT_S", "15")),
        exec_overall_timeout_s=float(os.getenv("EXEC_OVERALL_TIMEOUT_S", "3600")),
        exec_submit_forms=os.getenv("EXEC_SUBMIT_FORMS", "true").strip().lower() in ("1", "true", "yes"),
        max_forms_per_page=int(os.getenv("MAX_FORMS_PER_PAGE", "5")),
        max_forms=int(os.getenv("MAX_FORMS", "50")),
        exec_validation_depth=_depth(os.getenv("EXEC_VALIDATION_DEPTH", "thorough")),
        max_cases_per_form=int(os.getenv("MAX_CASES_PER_FORM", "25")),
        max_cases=int(os.getenv("MAX_CASES", "200")),
        exec_test_actions=os.getenv("EXEC_TEST_ACTIONS", "true").strip().lower() in ("1", "true", "yes"),
        max_actions_per_page=int(os.getenv("MAX_ACTIONS_PER_PAGE", "15")),
        max_actions=int(os.getenv("MAX_ACTIONS", "150")),
        action_deny_extra=tuple(w.strip().lower() for w in os.getenv("ACTION_DENY_EXTRA", "").split(",") if w.strip()),
    )
