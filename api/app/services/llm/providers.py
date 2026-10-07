import json
import os
import shutil
import subprocess
import tempfile

import httpx

from app.services.llm.base import LLMError


def _post(url: str, headers: dict, body: dict, timeout: float, name: str) -> dict:
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.TimeoutException:
        raise LLMError(f"{name} request timed out.")
    except httpx.HTTPError as e:
        raise LLMError(f"{name} request failed: {e.__class__.__name__}.")
    if r.status_code >= 400:
        raise LLMError(f"{name} returned HTTP {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except ValueError:
        raise LLMError(f"{name} returned a non-JSON response.")


def _need_key(key: str, env: str) -> None:
    if not key:
        raise LLMError(f"{env} is not set.")


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def complete(self, system: str, user: str) -> str:
        _need_key(self.api_key, "ANTHROPIC_API_KEY")
        d = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                  {"model": self.model, "max_tokens": 16000, "temperature": 0, "system": system,
                   "messages": [{"role": "user", "content": user}]}, self.timeout, "Anthropic")
        try:
            return "".join(b.get("text", "") for b in d["content"])
        except (KeyError, TypeError):
            raise LLMError("Anthropic response had an unexpected shape.")


class OpenRouterProvider:
    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def complete(self, system: str, user: str) -> str:
        _need_key(self.api_key, "OPENROUTER_API_KEY")
        d = _post("https://openrouter.ai/api/v1/chat/completions",
                  {"Authorization": f"Bearer {self.api_key}"},
                  {"model": self.model, "temperature": 0,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                  self.timeout, "OpenRouter")
        try:
            return d["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("OpenRouter response had an unexpected shape.")


class GeminiProvider:
    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def complete(self, system: str, user: str) -> str:
        _need_key(self.api_key, "GEMINI_API_KEY")
        d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                  {"x-goog-api-key": self.api_key},
                  {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}],
                   "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
                  self.timeout, "Gemini")
        try:
            return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise LLMError("Gemini response had an unexpected shape.")


def resolve_claude() -> str | None:
    """On Windows `claude` is an npm shim (.cmd/.ps1); run the native exe it wraps instead,
    which avoids cmd.exe quoting problems with empty args and multi-line prompts."""
    found = shutil.which("claude")
    if not found:
        return None
    if found.lower().endswith(".exe"):
        return found
    exe = os.path.join(os.path.dirname(found), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
    return exe if os.path.isfile(exe) else found


class ClaudeCliProvider:
    """Local personal use only: uses the logged-in Claude Code account."""

    def __init__(self, model: str, timeout: float):
        self.model, self.timeout = model, timeout

    def complete(self, system: str, user: str) -> str:
        exe = resolve_claude()
        if not exe:
            raise LLMError("The 'claude' CLI was not found on PATH. Install Claude Code and log in.")
        # minimal context: no tools, no MCP, no skills, no user/project/local settings (hooks, plugins),
        # no session files, empty temp cwd (no CLAUDE.md discovery); prompt on stdin
        cmd = [exe, "-p", "--output-format", "json", "--model", self.model, "--tools", "",
               "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
               "--setting-sources", "", "--system-prompt", system]
        try:
            with tempfile.TemporaryDirectory(prefix="claude-cli-") as cwd:
                p = subprocess.run(cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                                   timeout=self.timeout, cwd=cwd)
        except subprocess.TimeoutExpired:
            raise LLMError(f"claude CLI timed out after {self.timeout:g}s.")
        except OSError as e:
            raise LLMError(f"Could not run the 'claude' CLI: {e.__class__.__name__}.")
        try:
            data = json.loads(p.stdout)
        except ValueError:
            data = None
        if p.returncode != 0 or not isinstance(data, dict) or data.get("is_error"):
            detail = (data.get("result") if isinstance(data, dict) else None) or p.stderr.strip() or p.stdout.strip()
            raise LLMError(f"claude CLI failed (exit {p.returncode}); is it logged in? {str(detail)[:200]}")
        if not isinstance(data.get("result"), str):
            raise LLMError("claude CLI output had no 'result' field.")
        return data["result"]
