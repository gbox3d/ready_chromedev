from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gui_tool.profiles import DEFAULT_CONFIG, DEFAULT_PROFILE_NAME, ProfileStore


class ProfileStoreTests(unittest.TestCase):
    def test_creates_default_yaml_and_round_trips_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.yaml"
            store = ProfileStore(path)
            store.load()

            self.assertTrue(path.is_file())
            self.assertEqual(store.active_profile, DEFAULT_PROFILE_NAME)
            self.assertEqual(store.profiles[DEFAULT_PROFILE_NAME], DEFAULT_CONFIG)

            store.save_profile("second", DEFAULT_CONFIG)
            reloaded = ProfileStore(path)
            reloaded.load()

            self.assertEqual(reloaded.active_profile, "second")
            self.assertIn("second", reloaded.profiles)

    def test_does_not_delete_last_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.yaml")
            store.load()
            with self.assertRaisesRegex(ValueError, "마지막 프로파일"):
                store.delete_profile(DEFAULT_PROFILE_NAME)


if __name__ == "__main__":
    unittest.main()
