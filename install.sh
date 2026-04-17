#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${ZSHAI_INSTALL_ROOT:-$HOME/.local/share/zshai}"
VENV_DIR="$INSTALL_ROOT/venv"
BIN_DIR="${ZSHAI_BIN_DIR:-$HOME/.local/bin}"
ZSHRC_PATH="${ZDOTDIR:-$HOME}/.zshrc"
WRAPPER_PATH="$BIN_DIR/zshai"
HOOK_BEGIN="# >>> zshai >>>"
HOOK_END="# <<< zshai <<<"

say() {
  printf '%s\n' "${1-}"
}

ask_yes_no() {
  local prompt="$1"
  local default="${2:-y}"
  local answer
  local suffix="[Y/n]"
  [[ "$default" == "n" ]] && suffix="[y/N]"
  read -r -p "$prompt $suffix " answer
  answer="${answer:-$default}"
  [[ "$answer" =~ ^[Yy]$ ]]
}

append_hook() {
  mkdir -p "$(dirname "$ZSHRC_PATH")"
  touch "$ZSHRC_PATH"
  if grep -Fq "$HOOK_BEGIN" "$ZSHRC_PATH"; then
    say "zsh hook already present in $ZSHRC_PATH"
    return
  fi
  cat >>"$ZSHRC_PATH" <<EOF

$HOOK_BEGIN
if command -v zshai >/dev/null 2>&1; then
  eval "\$(zshai init-zsh)"
fi
$HOOK_END
EOF
  say "Added zsh hook to $ZSHRC_PATH"
}

ensure_path_line() {
  mkdir -p "$(dirname "$ZSHRC_PATH")"
  touch "$ZSHRC_PATH"
  if grep -Fq 'export PATH="$HOME/.local/bin:$PATH"' "$ZSHRC_PATH"; then
    return
  fi
  printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >>"$ZSHRC_PATH"
  say "Added ~/.local/bin to PATH in $ZSHRC_PATH"
}

main() {
  say "Installing zshai from $PROJECT_DIR"
  command -v python3 >/dev/null 2>&1 || { say "python3 is required"; exit 1; }

  mkdir -p "$INSTALL_ROOT" "$BIN_DIR"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
  "$VENV_DIR/bin/python" -m pip install "$PROJECT_DIR"

  cat >"$WRAPPER_PATH" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/zshai" "\$@"
EOF
  chmod +x "$WRAPPER_PATH"
  say "Installed CLI wrapper at $WRAPPER_PATH"

  if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    if ask_yes_no "Add $BIN_DIR to your PATH in $ZSHRC_PATH?" y; then
      ensure_path_line
    else
      say "Skipping PATH update. Make sure $BIN_DIR is on PATH before using zshai."
    fi
  fi

  if ask_yes_no "Add the zshai hook to $ZSHRC_PATH?" y; then
    append_hook
  fi

  if ask_yes_no "Run interactive zshai configuration now?" y; then
    "$WRAPPER_PATH" configure --interactive
  fi

  say
  say "Install complete."
  say "Next steps:"
  say "  1. Restart zsh or run: source \"$ZSHRC_PATH\""
  say "  2. Check health with: zshai doctor"
  say "  3. Try: # find all files with convex in their name"
}

main "$@"
