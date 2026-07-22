from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui_tool import cleanup


class PortOwnerTests(unittest.TestCase):
    def test_finds_this_process_as_owner_of_its_own_listener(self) -> None:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
            held.bind(("127.0.0.1", 0))
            held.listen(1)
            port = held.getsockname()[1]

            owner = cleanup.port_owner(port)

        self.assertIsNotNone(owner)
        pid, image = owner
        self.assertEqual(pid, os.getpid())
        self.assertIn("python", image)

    def test_returns_none_for_a_free_port(self) -> None:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]

        self.assertIsNone(cleanup.port_owner(free_port))


class OpenHandleTests(unittest.TestCase):
    def test_finds_this_process_holding_a_file_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Local State"
            path.write_text("{}", encoding="utf-8")
            with path.open("r", encoding="utf-8"):
                pids = cleanup.pids_with_open_handles([path])

        self.assertIn(os.getpid(), pids)

    def test_reports_nothing_for_unheld_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unheld.txt"
            path.write_text("x", encoding="utf-8")

            self.assertEqual(cleanup.pids_with_open_handles([path]), set())

    def test_profile_scan_ignores_non_chrome_holders(self) -> None:
        # 이 테스트 프로세스(python.exe)가 파일을 쥐고 있어도 chrome.exe가
        # 아니므로 회수 대상으로 잡히면 안 된다.
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            lock = profile / "Local State"
            lock.write_text("{}", encoding="utf-8")
            with lock.open("r", encoding="utf-8"):
                found = cleanup.processes_using_profile(profile)

        self.assertEqual(found, ())


class ProcessIdentityTests(unittest.TestCase):
    def test_identifies_this_process(self) -> None:
        identity = cleanup.process_identity(os.getpid())

        self.assertIsNotNone(identity)
        image, created_at = identity
        self.assertTrue(image.endswith(".exe"))
        self.assertGreater(created_at, 0)

    def test_returns_none_for_dead_pid(self) -> None:
        self.assertIsNone(cleanup.process_identity(0))
        self.assertIsNone(cleanup.process_identity(-1))

    def test_tracked_process_matches_only_the_same_process(self) -> None:
        tracked = cleanup.TrackedProcess.capture("chrome", os.getpid())

        self.assertIsNotNone(tracked)
        self.assertTrue(tracked.still_ours)

        # pid는 Windows에서 재사용된다. 생성 시각이 다르면 남의 프로세스다.
        recycled = cleanup.TrackedProcess(
            kind=tracked.kind,
            pid=tracked.pid,
            image=tracked.image,
            created_at=tracked.created_at + 1,
        )
        self.assertFalse(recycled.still_ours)


class SessionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        patcher = patch.object(cleanup, "temp_root", lambda: self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._directory.cleanup)

    def _state(self, port: int, owner_pid: int, **kwargs: object) -> cleanup.SessionState:
        return cleanup.SessionState(
            port=port,
            owner_pid=owner_pid,
            user_data_dir=kwargs.get("user_data_dir", ""),
            owns_chrome=bool(kwargs.get("owns_chrome", False)),
            processes=tuple(kwargs.get("processes", ())),
        )

    def test_round_trips_through_disk(self) -> None:
        tracked = cleanup.TrackedProcess("ssh", 4321, "ssh.exe", 987654321)
        cleanup.write_session_state(self._state(9333, 111, processes=(tracked,)))

        states = cleanup.read_session_states()

        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].port, 9333)
        self.assertEqual(states[0].processes, (tracked,))

    def test_discards_unreadable_session_file(self) -> None:
        (self.root / f"{cleanup.SESSION_PREFIX}9222.json").write_text("{ not json", encoding="utf-8")

        self.assertEqual(cleanup.read_session_states(), [])

    def test_skips_sessions_whose_owner_is_alive(self) -> None:
        dead = cleanup.TrackedProcess("chrome", 5555, "chrome.exe", 42)
        cleanup.write_session_state(self._state(9333, 222, processes=(dead,)))

        leftovers = cleanup.find_leftovers(owner_is_alive=lambda pid: True)

        self.assertEqual(leftovers, [])
        # 소유자가 살아 있으면 세션 파일도 지우지 않는다.
        self.assertTrue(cleanup.session_path(9333).is_file())

    def test_drops_session_file_when_nothing_is_left(self) -> None:
        gone = cleanup.TrackedProcess("chrome", 5555, "chrome.exe", 42)
        cleanup.write_session_state(self._state(9333, 222, processes=(gone,)))

        leftovers = cleanup.find_leftovers(owner_is_alive=lambda pid: False)

        self.assertEqual(leftovers, [])
        self.assertFalse(cleanup.session_path(9333).is_file())

    def test_reports_live_process_from_a_dead_owner(self) -> None:
        mine = cleanup.TrackedProcess.capture("chrome", os.getpid())
        cleanup.write_session_state(self._state(9333, 222, processes=(mine,)))

        leftovers = cleanup.find_leftovers(owner_is_alive=lambda pid: False)

        self.assertEqual(len(leftovers), 1)
        self.assertEqual(leftovers[0].processes, (mine,))
        self.assertIn("9333", leftovers[0].describe())

    def test_reports_orphan_profile_directory(self) -> None:
        (self.root / f"{cleanup.PROFILE_PREFIX}9401").mkdir()

        leftovers = cleanup.find_leftovers(owner_is_alive=lambda pid: False)

        self.assertEqual(len(leftovers), 1)
        self.assertEqual(leftovers[0].port, 9401)
        self.assertEqual(leftovers[0].processes, ())

    def test_keeps_profile_directory_claimed_by_a_live_session(self) -> None:
        (self.root / f"{cleanup.PROFILE_PREFIX}9402").mkdir()
        cleanup.write_session_state(self._state(9402, 333))

        leftovers = cleanup.find_leftovers(owner_is_alive=lambda pid: True)

        self.assertEqual(leftovers, [])

    def test_clean_never_kills_a_recycled_pid(self) -> None:
        recycled = cleanup.TrackedProcess("chrome", os.getpid(), "chrome.exe", 1)
        leftover = cleanup.Leftover(port=9333, processes=(recycled,), profile_dir=None)
        messages: list[str] = []

        with patch.object(cleanup, "terminate_tree") as terminate:
            killed, removed = cleanup.clean_leftovers([leftover], messages.append)

        terminate.assert_not_called()
        self.assertEqual((killed, removed), (0, 0))
        self.assertTrue(any("건너뜀" in message for message in messages))

    def test_clean_removes_orphan_directory(self) -> None:
        path = self.root / f"{cleanup.PROFILE_PREFIX}9403"
        path.mkdir()
        (path / "Local State").write_text("{}", encoding="utf-8")
        leftover = cleanup.Leftover(port=9403, processes=(), profile_dir=path)

        killed, removed = cleanup.clean_leftovers([leftover])

        self.assertEqual((killed, removed), (0, 1))
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
