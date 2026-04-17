from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from datetime import datetime
from pathlib import Path


def _git_summary(cwd: Path) -> str:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return "not a git repository"

        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip() or "detached-head"
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return f"git branch: {branch}; dirty: {'yes' if dirty else 'no'}"
    except FileNotFoundError:
        return "git unavailable"


def _list_tools() -> str:
    tools = ["rg", "fd", "find", "git", "jq", "python3", "node", "npm", "brew", "sed", "awk"]
    available = [tool for tool in tools if shutil.which(tool)]
    return ", ".join(available) if available else "none detected"


def _dir_preview(cwd: Path) -> str:
    try:
        names = sorted(entry.name for entry in cwd.iterdir())[:20]
    except OSError:
        return "unavailable"
    return ", ".join(names) if names else "(empty directory)"


def build_system_prompt(cwd: str | Path, shell: str = "zsh") -> str:
    cwd_path = Path(cwd).resolve()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    prompt = f"""You are a shell command generator for an interactive {shell} session.
Return exactly one JSON object with this shape:
{{"command":"...", "rationale":"...", "risk":"low|medium|high"}}

Rules:
- The command must be valid for zsh on this machine.
- Return only JSON. No markdown, no prose, no code fences.
- Prefer a single command. A short command chain is allowed when needed.
- Prefer installed/common tools. Prefer `rg` over `grep` when appropriate.
- The command will run in the user's current shell, so builtins like `cd` and `export` are allowed.
- Do not use placeholders like <path> or YOUR_FILE.
- Avoid destructive commands unless the user explicitly asked for them.
- Avoid `sudo`, `rm -rf`, `git reset --hard`, and similar commands unless explicitly requested.
- If the request is ambiguous, make a sensible assumption and encode it in the command.
- Keep rationale short.

Useful system context:
- current time: {now}
- current directory: {cwd_path}
- shell: {shell}
- user: {os.environ.get("USER", "unknown")}
- host: {socket.gethostname()}
- platform: {platform.platform()}
- machine: {platform.machine()}
- visible directory entries: {_dir_preview(cwd_path)}
- available tools: {_list_tools()}
- {_git_summary(cwd_path)}
"""
    return prompt
