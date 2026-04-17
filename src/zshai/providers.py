from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import build_system_prompt


class ProviderError(RuntimeError):
    pass


@dataclass
class CommandSuggestion:
    provider: str
    command: str
    rationale: str
    risk: str
    raw: str


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(cleaned[index:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise ProviderError(f"Could not parse JSON object from provider response:\n{cleaned}")


def _normalize_result(provider: str, raw_text: str) -> CommandSuggestion:
    data = _extract_json_object(raw_text)
    command = str(data.get("command", "")).strip()
    rationale = str(data.get("rationale", "")).strip()
    risk = str(data.get("risk", "medium")).strip().lower() or "medium"
    if not command:
        raise ProviderError(f"{provider} returned JSON without a command")
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    return CommandSuggestion(provider=provider, command=command, rationale=rationale, risk=risk, raw=raw_text)


def _user_prompt(prompt: str) -> str:
    return f"Turn this shell intent into a command:\n\n{prompt}\n"


def generate_with_codex(prompt: str, cwd: str | Path, shell: str, config: dict[str, Any]) -> CommandSuggestion:
    codex_command = config["codex"]["command"]
    system_prompt = build_system_prompt(cwd, shell)
    model = config["codex"].get("model", "").strip()
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["command", "rationale", "risk"],
        "properties": {
            "command": {"type": "string"},
            "rationale": {"type": "string"},
            "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        },
    }
    with tempfile.TemporaryDirectory(prefix="zshai-codex-") as temp_dir:
        schema_path = Path(temp_dir) / "schema.json"
        output_path = Path(temp_dir) / "output.txt"
        schema_path.write_text(json.dumps(schema))
        full_prompt = f"{system_prompt}\nUser request:\n{_user_prompt(prompt)}"
        command = [
            codex_command,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-C",
            str(Path(cwd).resolve()),
        ]
        if model:
            command.extend(["-m", model])
        command.append(full_prompt)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ProviderError(result.stderr.strip() or result.stdout.strip() or "codex failed")
        raw = output_path.read_text() if output_path.exists() else result.stdout
    return _normalize_result("codex", raw)


def generate_with_opencode(prompt: str, cwd: str | Path, shell: str, config: dict[str, Any]) -> CommandSuggestion:
    opencode_command = config["opencode"]["command"]
    system_prompt = build_system_prompt(cwd, shell)
    model = config["opencode"].get("model", "").strip()
    agent = config["opencode"].get("agent", "").strip()
    variant = config["opencode"].get("variant", "").strip()
    full_prompt = f"{system_prompt}\nUser request:\n{_user_prompt(prompt)}"
    command = [
        opencode_command,
        "run",
        "--dir",
        str(Path(cwd).resolve()),
        "--format",
        "default",
        full_prompt,
    ]
    if agent:
        command.extend(["--agent", agent])
    if model:
        command.extend(["-m", model])
    if variant:
        command.extend(["--variant", variant])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ProviderError(result.stderr.strip() or result.stdout.strip() or "opencode failed")
    return _normalize_result("opencode", result.stdout.strip())


def generate_with_gemini(prompt: str, cwd: str | Path, shell: str, config: dict[str, Any]) -> CommandSuggestion:
    gemini_config = config["gemini"]
    api_key = os.environ.get(gemini_config["api_key_env"]) or os.environ.get(gemini_config["fallback_api_key_env"])
    if not api_key:
        raise ProviderError(
            f"Missing Gemini API key. Set {gemini_config['api_key_env']} or {gemini_config['fallback_api_key_env']}."
        )

    model = gemini_config["model"].strip()
    base_url = gemini_config["base_url"].rstrip("/")
    system_prompt = build_system_prompt(cwd, shell)
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": _user_prompt(prompt)}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {
                "thinkingLevel": gemini_config["thinking_level"],
            },
        },
    }
    url = f"{base_url}/models/{model}:generateContent"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"Gemini HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Gemini request failed: {exc}") from exc

    parts: list[str] = []
    for candidate in response_data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                parts.append(part["text"])
    raw = "\n".join(parts).strip()
    if not raw:
        raise ProviderError(f"Gemini returned no text parts: {json.dumps(response_data)[:500]}")
    return _normalize_result("gemini", raw)


PROVIDER_FUNCS = {
    "codex": generate_with_codex,
    "opencode": generate_with_opencode,
    "gemini": generate_with_gemini,
}


def generate_command(prompt: str, cwd: str | Path, shell: str, config: dict[str, Any]) -> CommandSuggestion:
    errors: list[str] = []
    for provider in config["provider_priority"]:
        func = PROVIDER_FUNCS.get(provider)
        if not func:
            continue
        try:
            return func(prompt=prompt, cwd=cwd, shell=shell, config=config)
        except FileNotFoundError:
            errors.append(f"{provider}: executable not found")
        except ProviderError as exc:
            errors.append(f"{provider}: {exc}")
    raise ProviderError("All configured providers failed.\n" + "\n".join(errors))
