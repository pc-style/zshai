from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("ZSHAI_CONFIG_DIR", Path.home() / ".config" / "zshai"))
CONFIG_PATH = CONFIG_DIR / "config.json"
SUPPORTED_PROVIDERS = ("codex", "opencode", "gemini")

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "prefix": "# ",
    "mode": "execute",
    "provider_priority": ["codex", "opencode", "gemini"],
    "codex": {
        "command": "codex",
        "model": "",
    },
    "opencode": {
        "command": "opencode",
        "agent": "zen",
        "model": "big-pickle",
        "variant": "",
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "fallback_api_key_env": "GOOGLE_API_KEY",
        "model": "gemini-3.1-flash-lite-preview",
        "thinking_level": "medium",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_provider_list(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = raw.replace(":", ",").replace(" ", ",").split(",")
    seen: list[str] = []
    for item in items:
        name = item.strip().lower()
        if name and name in SUPPORTED_PROVIDERS and name not in seen:
            seen.append(name)
    return seen


def load_config() -> dict[str, Any]:
    data = deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        file_data = json.loads(CONFIG_PATH.read_text())
        data = _merge(data, file_data)

    env_priority = os.environ.get("AI_PRIOVIDERS") or os.environ.get("AI_PROVIDERS")
    if env_priority:
        parsed = normalize_provider_list(env_priority)
        if parsed:
            data["provider_priority"] = parsed

    if os.environ.get("ZSHAI_MODE"):
        data["mode"] = os.environ["ZSHAI_MODE"].strip().lower()
    if os.environ.get("ZSHAI_PREFIX"):
        data["prefix"] = os.environ["ZSHAI_PREFIX"]

    if os.environ.get("ZSHAI_CODEX_MODEL"):
        data["codex"]["model"] = os.environ["ZSHAI_CODEX_MODEL"]

    if os.environ.get("ZSHAI_OPENCODE_AGENT"):
        data["opencode"]["agent"] = os.environ["ZSHAI_OPENCODE_AGENT"]
    if os.environ.get("ZSHAI_OPENCODE_MODEL"):
        data["opencode"]["model"] = os.environ["ZSHAI_OPENCODE_MODEL"]
    if os.environ.get("ZSHAI_OPENCODE_VARIANT"):
        data["opencode"]["variant"] = os.environ["ZSHAI_OPENCODE_VARIANT"]

    if os.environ.get("ZSHAI_GEMINI_MODEL"):
        data["gemini"]["model"] = os.environ["ZSHAI_GEMINI_MODEL"]
    if os.environ.get("ZSHAI_GEMINI_THINKING_LEVEL"):
        data["gemini"]["thinking_level"] = os.environ["ZSHAI_GEMINI_THINKING_LEVEL"]
    if os.environ.get("ZSHAI_GEMINI_API_KEY_ENV"):
        data["gemini"]["api_key_env"] = os.environ["ZSHAI_GEMINI_API_KEY_ENV"]

    data["provider_priority"] = normalize_provider_list(data.get("provider_priority")) or list(
        DEFAULT_CONFIG["provider_priority"]
    )
    return data


def save_config(config: dict[str, Any]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    return CONFIG_PATH
