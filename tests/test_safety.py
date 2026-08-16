from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zshai import cli
from zshai.config import DEFAULT_CONFIG


class SafetyDefaultsTest(unittest.TestCase):
    def test_default_requires_confirmation_and_consent(self) -> None:
        self.assertEqual(DEFAULT_CONFIG["mode"], "confirm")
        self.assertFalse(DEFAULT_CONFIG["provider_cwd_consent"])

    def test_hook_only_executes_for_explicit_execute_mode(self) -> None:
        self.assertIn('[[ -z "$mode" ]] && mode="confirm"', cli.ZSH_HOOK)
        self.assertIn("    execute)\n      BUFFER=\"$generated\"\n      zle .accept-line", cli.ZSH_HOOK)
        self.assertIn("    *)\n      BUFFER=\"$generated\"\n      zle redisplay", cli.ZSH_HOOK)

    @unittest.skipUnless(shutil.which("zsh"), "zsh is required to exercise the hook")
    def test_hook_does_not_execute_generated_command_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "executed"
            generated = f"touch {shlex.quote(str(marker))}"
            script = (
                "typeset -a zle_calls\n"
                "function zle() { zle_calls+=(\"$*\") }\n"
                "function zshai() {\n"
                "  if [[ \"$1\" == config-get ]]; then\n"
                "    [[ \"$2\" == enabled ]] && print true\n"
                "    [[ \"$2\" == prefix ]] && print '# '\n"
                "    return\n"
                "  fi\n"
                f"  [[ \"$1\" == generate ]] && print -r -- {shlex.quote(generated)}\n"
                "}\n"
                + cli.ZSH_HOOK
                + "\nzle_calls=()\n"
                "BUFFER='# make marker'\n"
                "_zshai_accept_line\n"
                "print -r -- \"BUFFER=$BUFFER\"\n"
                "printf 'ZLE=%s\\n' \"${zle_calls[@]}\"\n"
            )

            result = subprocess.run(["zsh", "-f"], input=script, text=True, capture_output=True, check=True)

            self.assertFalse(marker.exists())
            self.assertIn(f"BUFFER={generated}", result.stdout)
            self.assertIn("ZLE=redisplay", result.stdout)
            self.assertNotIn("ZLE=.accept-line", result.stdout)

    @patch("zshai.cli.generate_command")
    @patch("zshai.cli.load_config")
    def test_generation_contacts_no_provider_without_consent(self, load_config, generate_command) -> None:
        load_config.return_value = {**DEFAULT_CONFIG, "enabled": True, "provider_cwd_consent": False}
        args = argparse.Namespace(prompt="do something", cwd=".", shell="zsh", json=False, ignore_disabled=False)

        self.assertEqual(cli.cmd_generate(args), 1)
        generate_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
