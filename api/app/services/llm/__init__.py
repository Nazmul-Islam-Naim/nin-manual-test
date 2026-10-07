from app.config import get_settings
from app.services.llm.base import LLMError, LLMProvider
from app.services.llm.providers import (AnthropicProvider, ClaudeCliProvider, GeminiProvider,
                                        OpenRouterProvider)


def get_provider() -> LLMProvider:  # tests replace this
    s = get_settings()
    name = s.llm_provider
    if name == "claude_cli":
        return ClaudeCliProvider(s.claude_cli_model, s.claude_cli_timeout_s)
    if name == "anthropic":
        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model, s.llm_http_timeout_s)
    if name == "openrouter":
        return OpenRouterProvider(s.openrouter_api_key, s.openrouter_model, s.llm_http_timeout_s)
    if name == "gemini":
        return GeminiProvider(s.gemini_api_key, s.gemini_model, s.llm_http_timeout_s)
    raise LLMError(f"Unknown LLM_PROVIDER '{name}'. Use claude_cli, anthropic, openrouter or gemini.")


__all__ = ["LLMError", "LLMProvider", "get_provider"]
