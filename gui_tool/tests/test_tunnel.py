from __future__ import annotations

import os
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

from gui_tool.devtools import (
    DevToolsConfig,
    DevToolsRunner,
    PortInUseError,
    build_chrome_command,
    build_ssh_command,
    find_devtools,
    is_port_free,
    probe_devtools,
    suggest_free_port,
)


class DevToolsConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DevToolsConfig.from_mapping(
            {
                "backend_host": "192.168.0.220",
                "backend_port": 8000,
                "ssh_target": "gblab-dgx-01",
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

    def test_uses_user_at_host_as_ssh_target(self) -> None:
        values = self.config.to_mapping()
        values["ssh_target"] = "gblab-dgx-01@192.168.0.220"
        config = DevToolsConfig.from_mapping(values)

        self.assertEqual(config.ssh_target, "gblab-dgx-01@192.168.0.220")

    def test_rejects_empty_ssh_target(self) -> None:
        values = self.config.to_mapping()
        values["ssh_target"] = ""

        with self.assertRaisesRegex(ValueError, "SSH 대상"):
            build_ssh_command(DevToolsConfig.from_mapping(values), "ssh.exe")

    def test_builds_chrome_command_with_dedicated_profile(self) -> None:
        command = build_chrome_command(self.config, Path("C:/Chrome/chrome.exe"))

        self.assertIn("--remote-debugging-port=9333", command)
        self.assertTrue(any(value.startswith("--user-data-dir=") for value in command))
        self.assertEqual(command[-1], "http://192.168.0.220:8000/")

    def test_ignores_legacy_start_url_and_uses_backend_url(self) -> None:
        values = self.config.to_mapping()
        values["start_url"] = "https://legacy.example.test/"

        config = DevToolsConfig.from_mapping(values)
        command = build_chrome_command(config, Path("C:/Chrome/chrome.exe"))

        self.assertEqual(command[-1], "http://192.168.0.220:8000/")
        self.assertNotIn("start_url", config.to_mapping())

    def test_local_mode_allows_empty_ssh_settings(self) -> None:
        config = DevToolsConfig.from_mapping(
            {
                "backend_host": "",
                "backend_port": "",
                "ssh_target": "",
                "chrome_debug_port": 9333,
                "remote_debug_port": "",
                "chrome_profile": "",
            }
        )

        self.assertEqual(config.launch_url, "about:blank")
        self.assertEqual(config.remote_debug_port, 0)

    def test_runs_local_without_starting_ssh(self) -> None:
        runner = DevToolsRunner()
        events: list[tuple[str, object]] = []
        with (
            patch.object(runner, "_prepare_devtools", return_value={"Browser": "Chrome"}),
            patch.object(runner, "_wait_for_stop", return_value=0),
            patch.object(runner, "_close_chrome"),
            patch.object(runner, "_run_tunnel") as run_tunnel,
        ):
            self.assertEqual(
                runner.run_local(self.config, lambda event, payload: events.append((event, payload))),
                0,
            )

        self.assertIn(("state", "로컬 DevTools 실행 중"), events)
        run_tunnel.assert_not_called()

    def test_rejects_invalid_port(self) -> None:
        values = self.config.to_mapping()
        values["remote_debug_port"] = 70000
        with self.assertRaisesRegex(ValueError, "1~65535"):
            DevToolsConfig.from_mapping(values)

    def test_blank_optional_port_survives_a_save_and_reload(self) -> None:
        values = self.config.to_mapping()
        values["backend_port"] = ""

        saved = DevToolsConfig.from_mapping(values).to_mapping()
        self.assertEqual(saved["backend_port"], 0)

        # 앱이 쓴 0을 다시 읽지 못하면 GUI가 두 번 다시 열리지 않는다.
        reloaded = DevToolsConfig.from_mapping(saved)
        self.assertEqual(reloaded.backend_port, 0)
        self.assertEqual(reloaded.launch_url, "about:blank")

    def test_rejects_boolean_and_fractional_ports(self) -> None:
        for bad in (True, 9222.5, "port"):
            values = self.config.to_mapping()
            values["chrome_debug_port"] = bad
            with self.assertRaisesRegex(ValueError, "정수", msg=f"{bad!r} was accepted"):
                DevToolsConfig.from_mapping(values)


class DevToolsProbeTests(unittest.TestCase):
    def test_finds_devtools_on_ipv6_loopback(self) -> None:
        # 127.0.0.1이 이미 점유되어 있으면 Chrome은 [::1]에 바인딩한다.
        def fake_probe(host: str, port: int, timeout: float) -> dict[str, object] | None:
            return {"Browser": "Chrome/150"} if host == "[::1]" else None

        with patch("gui_tool.devtools.probe_devtools", side_effect=fake_probe):
            found = find_devtools(9222)

        self.assertEqual(found, ("[::1]", {"Browser": "Chrome/150"}))

    def test_rejects_a_json_service_that_is_not_devtools(self) -> None:
        class _Response:
            def read(self, *_: object) -> bytes:
                return b'{"hello": "world"}'

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, *_: object) -> None:
                return None

        with patch("gui_tool.devtools._DIRECT_OPENER") as opener:
            opener.open.return_value = _Response()
            self.assertIsNone(probe_devtools("127.0.0.1", 9222))

    def test_detects_an_occupied_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
            held.bind(("127.0.0.1", 0))
            held.listen(1)
            port = held.getsockname()[1]

            self.assertFalse(is_port_free(port))

        self.assertTrue(is_port_free(port))

    def test_port_in_use_error_names_the_owner_and_suggests_a_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
            held.bind(("127.0.0.1", 0))
            held.listen(1)
            port = held.getsockname()[1]

            error = PortInUseError(port)

        # 점유자가 이 테스트 프로세스(python)로 지목되어야 한다. 이름 없는
        # "다른 프로세스" 오류는 사용자가 자기 충돌로 오해하게 만든다.
        self.assertIsNotNone(error.owner)
        self.assertEqual(error.owner[0], os.getpid())
        self.assertIn("python", str(error))
        self.assertIn(f"pid {os.getpid()}", str(error))
        # python.exe는 앱 소유 Chrome이 아니다.
        self.assertFalse(error.owned_by_app)
        self.assertIn("종료하지 않습니다", str(error))
        # 빠져나갈 길(빈 포트)이 반드시 제시되어야 한다.
        self.assertIsNotNone(error.suggested_port)
        self.assertNotEqual(error.suggested_port, port)
        self.assertTrue(is_port_free(error.suggested_port))

    def test_suggest_free_port_skips_the_occupied_one(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
            held.bind(("127.0.0.1", 0))
            held.listen(1)
            occupied = held.getsockname()[1]

            suggested = suggest_free_port(occupied - 1)

            self.assertIsNotNone(suggested)
            self.assertNotEqual(suggested, occupied)


if __name__ == "__main__":
    unittest.main()
