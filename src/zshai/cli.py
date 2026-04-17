from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import CONFIG_PATH, SUPPORTED_PROVIDERS, load_config, normalize_provider_list, save_config
from .providers import ProviderError, generate_command

ZSH_HOOK = r"""
function _zshai_accept_line() {
  local enabled prefix generated mode prompt
  enabled="$(zshai config-get enabled 2>/dev/null)"
  prefix="${ZSHAI_PREFIX_OVERRIDE:-$(zshai config-get prefix 2>/dev/null)}"
  mode="${ZSHAI_MODE_OVERRIDE:-$(zshai config-get mode 2>/dev/null)}"
  [[ -z "$prefix" ]] && prefix="# "
  [[ -z "$mode" ]] && mode="execute"

  if [[ "$enabled" == "False" || "$enabled" == "false" || "$enabled" == "0" ]]; then
    zle .accept-line
    return
  fi

  if [[ "$BUFFER" != ${prefix}* ]]; then
    zle .accept-line
    return
  fi

  prompt="${BUFFER#$prefix}"
  if [[ -z "${prompt// }" ]]; then
    BUFFER=""
    zle redisplay
    return
  fi

  generated="$(zshai generate --cwd "$PWD" --shell zsh --prompt "$prompt")" || return 1
  print -P "%F{39}zshai%f -> $generated"

  case "$mode" in
    confirm)
      BUFFER="$generated"
      zle redisplay
      ;;
    print)
      BUFFER=""
      zle redisplay
      ;;
    *)
      BUFFER="$generated"
      zle .accept-line
      ;;
  esac
}

zle -N accept-line _zshai_accept_line
"""


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2))


def _update_config(mutator) -> dict[str, Any]:
    config = load_config()
    mutator(config)
    save_config(config)
    return config


def _ask(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def _parse_bool(raw: str, default: bool) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"y", "yes", "true", "1", "on"}:
        return True
    if normalized in {"n", "no", "false", "0", "off"}:
        return False
    return default


def cmd_status(_: argparse.Namespace) -> int:
    config = load_config()
    _print_json(
        {
            "version": __version__,
            "config_path": str(CONFIG_PATH),
            "enabled": config["enabled"],
            "prefix": config["prefix"],
            "mode": config["mode"],
            "provider_priority": config["provider_priority"],
            "codex_model": config["codex"]["model"],
            "opencode_agent": config["opencode"]["agent"],
            "opencode_model": config["opencode"]["model"],
            "opencode_variant": config["opencode"]["variant"],
            "gemini_model": config["gemini"]["model"],
            "gemini_thinking_level": config["gemini"]["thinking_level"],
        }
    )
    return 0


def cmd_enable(_: argparse.Namespace) -> int:
    config = _update_config(lambda cfg: cfg.__setitem__("enabled", True))
    print(f"Enabled zshai. Config saved to {CONFIG_PATH}")
    print("If your shell hook is already loaded, '# prompt' interception is active immediately.")
    if not config["enabled"]:
        return 1
    return 0


def cmd_disable(_: argparse.Namespace) -> int:
    _update_config(lambda cfg: cfg.__setitem__("enabled", False))
    print(f"Disabled zshai in {CONFIG_PATH}")
    return 0


def cmd_config_get(args: argparse.Namespace) -> int:
    config = load_config()
    value: Any = config
    for part in args.key.split("."):
        if not isinstance(value, dict) or part not in value:
            return 1
        value = value[part]
    if isinstance(value, (dict, list)):
        print(json.dumps(value))
    else:
        print(value)
    return 0


def _configure_interactive(config: dict[str, Any]) -> dict[str, Any]:
    config["enabled"] = _parse_bool(
        _ask("Enable zshai interception? (y/n)", "y" if config["enabled"] else "n"),
        config["enabled"],
    )
    config["mode"] = _ask("Intercept mode (execute/confirm/print)", config["mode"]).lower()
    config["prefix"] = _ask("Prefix that triggers AI command generation", config["prefix"])

    priority = _ask(
        "Provider priority (comma separated: codex,opencode,gemini)",
        ",".join(config["provider_priority"]),
    )
    parsed_priority = normalize_provider_list(priority)
    if parsed_priority:
        config["provider_priority"] = parsed_priority

    config["codex"]["model"] = _ask("Codex model override (empty keeps CLI default)", config["codex"]["model"])
    config["opencode"]["agent"] = _ask("OpenCode agent", config["opencode"]["agent"])
    config["opencode"]["model"] = _ask("OpenCode model", config["opencode"]["model"])
    config["opencode"]["variant"] = _ask("OpenCode variant (optional)", config["opencode"]["variant"])
    config["gemini"]["model"] = _ask("Gemini model", config["gemini"]["model"])
    config["gemini"]["thinking_level"] = _ask("Gemini thinking level", config["gemini"]["thinking_level"])
    config["gemini"]["api_key_env"] = _ask("Gemini API key env var", config["gemini"]["api_key_env"])
    return config


def cmd_configure(args: argparse.Namespace) -> int:
    config = load_config()
    if args.interactive:
        config = _configure_interactive(config)
    if args.mode:
        config["mode"] = args.mode
    if args.prefix:
        config["prefix"] = args.prefix
    if args.provider_priority:
        parsed = normalize_provider_list(args.provider_priority)
        if parsed:
            config["provider_priority"] = parsed
    if args.opencode_agent:
        config["opencode"]["agent"] = args.opencode_agent
    if args.opencode_model:
        config["opencode"]["model"] = args.opencode_model
    if args.opencode_variant is not None:
        config["opencode"]["variant"] = args.opencode_variant
    if args.codex_model is not None:
        config["codex"]["model"] = args.codex_model
    if args.gemini_model:
        config["gemini"]["model"] = args.gemini_model
    if args.gemini_thinking_level:
        config["gemini"]["thinking_level"] = args.gemini_thinking_level
    if args.gemini_api_key_env:
        config["gemini"]["api_key_env"] = args.gemini_api_key_env
    if args.enabled is not None:
        config["enabled"] = args.enabled
    save_config(config)
    print(f"Saved config to {CONFIG_PATH}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    config = load_config()
    if not config.get("enabled", True) and not args.ignore_disabled:
        print("zshai is disabled. Run `zshai enable` or use `--ignore-disabled`.", file=sys.stderr)
        return 1
    try:
        suggestion = generate_command(prompt=args.prompt, cwd=args.cwd, shell=args.shell, config=config)
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        _print_json(
            {
                "provider": suggestion.provider,
                "command": suggestion.command,
                "rationale": suggestion.rationale,
                "risk": suggestion.risk,
            }
        )
    else:
        print(suggestion.command)
    return 0


def cmd_init_zsh(_: argparse.Namespace) -> int:
    print(ZSH_HOOK.strip())
    return 0


def _binary_status(name: str) -> dict[str, str]:
    path = shutil.which(name)
    return {"ok": "true" if path else "false", "path": path or ""}


def cmd_doctor(_: argparse.Namespace) -> int:
    config = load_config()
    gemini_env = config["gemini"]["api_key_env"]
    fallback_env = config["gemini"]["fallback_api_key_env"]
    report = {
        "config_path": str(CONFIG_PATH),
        "config_exists": str(CONFIG_PATH.exists()).lower(),
        "enabled": str(config["enabled"]).lower(),
        "prefix": config["prefix"],
        "mode": config["mode"],
        "provider_priority": ",".join(config["provider_priority"]),
        "codex": _binary_status(config["codex"]["command"]),
        "opencode": _binary_status(config["opencode"]["command"]),
        "gemini_api_key": {
            "ok": "true" if (os.environ.get(gemini_env) or os.environ.get(fallback_env)) else "false",
            "checked_envs": f"{gemini_env},{fallback_env}",
        },
    }
    _print_json(report)
    healthy = (
        any(item["ok"] == "true" for item in (report["codex"], report["opencode"]))
        or report["gemini_api_key"]["ok"] == "true"
    )
    return 0 if healthy else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zshai", description="Generate shell commands from '# prompt' lines.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status").set_defaults(func=cmd_status)
    subparsers.add_parser("enable").set_defaults(func=cmd_enable)
    subparsers.add_parser("disable").set_defaults(func=cmd_disable)
    subparsers.add_parser("doctor").set_defaults(func=cmd_doctor)
    subparsers.add_parser("init-zsh").set_defaults(func=cmd_init_zsh)

    config_get = subparsers.add_parser("config-get")
    config_get.add_argument("key")
    config_get.set_defaults(func=cmd_config_get)

    configure = subparsers.add_parser("configure")
    configure.add_argument("--interactive", action="store_true")
    configure.add_argument("--mode", choices=["execute", "confirm", "print"])
    configure.add_argument("--prefix")
    configure.add_argument("--provider-priority")
    configure.add_argument("--opencode-agent")
    configure.add_argument("--opencode-model")
    configure.add_argument("--opencode-variant")
    configure.add_argument("--codex-model")
    configure.add_argument("--gemini-model")
    configure.add_argument("--gemini-thinking-level")
    configure.add_argument("--gemini-api-key-env")
    enabled_group = configure.add_mutually_exclusive_group()
    enabled_group.add_argument("--enable", dest="enabled", action="store_true")
    enabled_group.add_argument("--disable", dest="enabled", action="store_false")
    configure.set_defaults(func=cmd_configure, enabled=None)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--prompt", required=True)
    generate.add_argument("--cwd", default=os.getcwd())
    generate.add_argument("--shell", default="zsh")
    generate.add_argument("--json", action="store_true")
    generate.add_argument("--ignore-disabled", action="store_true")
    generate.set_defaults(func=cmd_generate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
