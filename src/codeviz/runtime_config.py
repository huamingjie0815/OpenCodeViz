from __future__ import annotations

import json
import os
from pathlib import Path


def load_runtime_config(project_root: Path | None = None) -> dict:
    paths: list[Path] = []
    explicit = os.environ.get("CODEVIZ_CONFIG_PATH")
    if explicit:
        paths.append(Path(explicit))
    if project_root is not None:
        paths.append(project_root / ".codeviz" / "config.json")

    for path in paths:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def runtime_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def runtime_api_key(config: dict) -> str:
    direct = os.environ.get("CODEVIZ_API_KEY")
    if direct:
        return direct
    configured = config.get("apiKey", "")
    if configured:
        return configured
    env_name = os.environ.get("CODEVIZ_API_KEY_ENV") or config.get("apiKeyEnv", "")
    if env_name:
        return os.environ.get(env_name, "")
    return ""


def _normalized_mode(value: str, allowed: set[str], default: str) -> str:
    lowered = (value or "").strip().lower()
    return lowered if lowered in allowed else default


def extractor_mode(config: dict) -> str:
    raw = os.environ.get("CODEVIZ_EXTRACTOR_MODE", config.get("extractorMode", "hybrid"))
    return _normalized_mode(raw, {"llm", "ast", "hybrid"}, "hybrid")


def fallback_mode(config: dict) -> str:
    raw = os.environ.get("CODEVIZ_FALLBACK_MODE", config.get("fallbackMode", "auto"))
    return _normalized_mode(raw, {"off", "auto", "always"}, "auto")


DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "google_genai": "gemini-2.0-flash",
}

PROVIDER_ENV_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
}


def resolve_llm_config(config: dict | None = None) -> dict:
    cfg = config or {}
    provider = runtime_value("CODEVIZ_PROVIDER", cfg.get("provider", "openai"))
    model = runtime_value("CODEVIZ_MODEL", cfg.get("model", ""))
    api_key = runtime_api_key(cfg)
    base_url = runtime_value("CODEVIZ_BASE_URL", cfg.get("baseUrl", ""))
    if not model:
        model = DEFAULT_MODELS.get(provider, "gpt-4o-mini")
    return {"provider": provider, "model": model, "api_key": api_key, "base_url": base_url}


def init_llm(config: dict | None = None):
    from langchain.chat_models import init_chat_model

    resolved = resolve_llm_config(config)
    provider = resolved["provider"]
    api_key = resolved["api_key"]
    base_url = resolved["base_url"]
    model = resolved["model"]

    env_var = PROVIDER_ENV_MAP.get(provider)
    if api_key and env_var and not os.environ.get(env_var):
        os.environ[env_var] = api_key

    cfg = config or {}
    max_tokens = int(runtime_value("CODEVIZ_MAX_TOKENS", str(cfg.get("maxTokens", 16384))))

    kwargs: dict = {"model_provider": provider, "max_tokens": max_tokens}
    if base_url:
        kwargs["base_url"] = base_url

    return init_chat_model(model, **kwargs)
