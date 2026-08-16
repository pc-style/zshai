# zshai

`zshai` turns a zsh line that starts with `# ` into an AI-generated shell command. The command is inserted into your prompt for review by default; press Enter again to run it.

```zsh
# find all files with convex in their name
```

Instead of treating that line as a shell comment, `zshai` intercepts it, sends the prompt to one of your configured AI providers, and then either executes the resulting command, inserts it into your prompt, or just prints it.

## Supported providers

- `codex` via the local `codex` CLI
- `opencode` via the local `opencode` CLI
- `gemini` via the Gemini Developer API

Default behavior:

- provider priority: `codex,opencode,gemini`
- opencode agent: `zen`
- opencode model: `big-pickle`
- Gemini model: `gemini-3.1-flash-lite-preview`
- Gemini thinking level: `medium`
- intercept mode: `confirm` (never executes the generated command automatically)

## Install

### Manual install from this repo

```bash
git clone https://github.com/pc-style/zshai.git
cd zshai
./install.sh
```

The installer:

- creates a dedicated virtualenv under `~/.local/share/zshai`
- installs the `zshai` CLI into `~/.local/bin/zshai`
- can add `~/.local/bin` to your `PATH`
- can add the zsh hook to `~/.zshrc`
- can run `zshai configure --interactive`

### Global install with `uv tool install`

From a local checkout:

```bash
cd /path/to/zshai
uv tool install .
```

From a GitHub repo:

```bash
uv tool install git+https://github.com/pc-style/zshai.git
```

After a `uv tool install`, add the zsh hook to your shell config:

```bash
echo 'eval "$(zshai init-zsh)"' >> ~/.zshrc
source ~/.zshrc
```

Then run:

```bash
zshai configure --interactive
zshai consent
zshai doctor
```

## Usage

Once the hook is loaded:

```zsh
# find all files with convex in their name
```

Useful commands:

```bash
zshai status
zshai enable
zshai disable
zshai configure --interactive
zshai doctor
zshai generate --prompt "find all files with convex in their name"
zshai init-zsh
```

## Configuration

`zshai` supports both `AI_PRIOVIDERS` and `AI_PROVIDERS` for provider priority. Values can be comma, colon, or space separated:

```bash
export AI_PRIOVIDERS="opencode,gemini,codex"
```

Other useful overrides:

```bash
export ZSHAI_MODE=confirm
export ZSHAI_OPENCODE_AGENT=zen
export ZSHAI_OPENCODE_MODEL=big-pickle
export ZSHAI_GEMINI_MODEL=gemini-3.1-flash-lite-preview
export ZSHAI_GEMINI_THINKING_LEVEL=medium
export GEMINI_API_KEY=...
```

## Hook modes

- `confirm`: generate a command and insert it into your prompt buffer
- `print`: generate a command and print it without executing
- `execute`: generate a command and run it immediately (**explicit opt-in; generated commands can be destructive**)

## Trust boundary and consent

AI output is untrusted shell text. The default `confirm` mode only inserts it into the editable prompt; inspect it before pressing Enter. `execute` mode removes that safety boundary and should only be enabled when you intentionally accept the risk. Unknown or missing mode values also fall back to confirmation rather than execution.

Generating a suggestion sends your prompt plus current-directory context to the selected provider. Context includes the resolved directory path, up to 20 entry names, available tools, platform/user/host details, and git branch/dirty status. Depending on priority and availability, that provider is Codex, OpenCode, or Google's Gemini API. Provider tools and services have their own data handling policies. On first use, generation is blocked until you review this boundary and run `zshai consent` (or grant consent during `zshai configure --interactive`). No provider is contacted when consent is declined. Remove `provider_cwd_consent` from the config or set it to `false` to revoke consent.
