from __future__ import annotations

import unittest
from pathlib import Path

from chrome_tunnel_gui.tunnel import (
    TunnelConfig,
    build_chrome_command,
    build_ssh_command,
)


class TunnelConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TunnelConfig.from_mapping(
            {
                "backend_host": "192.168.0.220",
                "backend_port": 8000,
                "ssh_user": "gblab-dgx-01",
                "ssh_host": "gblab-dgx-01",
                "chrome_debug_port": 9333,
                "remote_debug_port": 9222,
                "chrome_profile": "",
            }
        )

    def test_builds_ssh_reverse_forward_with_host_alias(self) -> None:
        command = build_ssh_command(self.config, "ssh.exe")

        self.assertEqual(command[-1], "gblab-dgx-01")
        self.assertIn("127.0.0.1:9222:127.0.0.1:9333", command)
        self.assertIn("BatchMode=yes", command)

    def test_falls_back_to_user_at_backend_host(self) -> None:
        values = self.config.to_mapping()
        values["ssh_host"] = ""
        config = TunnelConfig.from_mapping(values)

        self.assertEqual(config.ssh_target, "gblab-dgx-01@192.168.0.220")

    def test_builds_chrome_command_with_dedicated_profile(self) -> None:
        command = build_chrome_command(self.config, Path("C:/Chrome/chrome.exe"))

        self.assertIn("--remote-debugging-port=9333", command)
        self.assertTrue(any(value.startswith("--user-data-dir=") for value in command))
        self.assertEqual(command[-1], "http://192.168.0.220:8000/")

    def test_rejects_invalid_port(self) -> None:
        values = self.config.to_mapping()
        values["remote_debug_port"] = 70000
        with self.assertRaisesRegex(ValueError, "1~65535"):
            TunnelConfig.from_mapping(values)


if __name__ == "__main__":
    unittest.main()
