from __future__ import annotations

import argparse
import unittest
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

    @patch("zshai.cli.generate_command")
    @patch("zshai.cli.load_config")
    def test_generation_contacts_no_provider_without_consent(self, load_config, generate_command) -> None:
        load_config.return_value = {**DEFAULT_CONFIG, "enabled": True, "provider_cwd_consent": False}
        args = argparse.Namespace(prompt="do something", cwd=".", shell="zsh", json=False, ignore_disabled=False)

        self.assertEqual(cli.cmd_generate(args), 1)
        generate_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
