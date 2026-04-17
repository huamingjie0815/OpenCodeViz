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
