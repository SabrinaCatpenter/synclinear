from __future__ import annotations

import json
import os
import tempfile
import unittest

from config import load_config, save_config


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            self.assertIsNone(load_config(repo_root))

    def test_valid_config_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:\\timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["linear_team"], "Studio")
            self.assertEqual(config["linear_project"], "[Studio] Project Ironman")
            self.assertEqual(config["timetable_path"], "C:\\timetable.txt")
            self.assertEqual(config["last_synced_commit"], "de1c2c8")

    def test_malformed_json_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                f.write("{not valid json")

            self.assertIsNone(load_config(repo_root))

    def test_missing_required_key_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump({"linear_team": "Studio"}, f)  # missing linear_project, last_synced_commit

            self.assertIsNone(load_config(repo_root))

    def test_valid_config_with_new_v2_keys_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": ["add-user-auth"],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["known_openspec_changes"], ["add-user-auth"])
            self.assertEqual(config["last_artifact_check_at"], "2026-09-08T00:00:00Z")

    def test_missing_known_openspec_changes_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                    },
                    f,
                )

            self.assertIsNone(load_config(repo_root))

    def test_known_openspec_changes_wrong_type_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": "add-user-auth",
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                    },
                    f,
                )

            self.assertIsNone(load_config(repo_root))

    def test_valid_config_with_advanced_workflow_gaps_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": ["add-widget:gap1"],
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["advanced_workflow_gaps"], ["add-widget:gap1"])

    def test_missing_advanced_workflow_gaps_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                    },
                    f,
                )

            self.assertIsNone(load_config(repo_root))

    def test_valid_config_with_timetable_dir_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                        "timetable_dir": "C:/timelogs",
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["timetable_dir"], "C:/timelogs")

    def test_valid_config_without_timetable_dir_still_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertIsNotNone(config)
            self.assertNotIn("timetable_dir", config)

    def test_timetable_dir_wrong_type_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                        "timetable_dir": 12345,
                    },
                    f,
                )

            self.assertIsNone(load_config(repo_root))


class TestSaveConfig(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as repo_root:
            config = {
                "linear_team": "Studio",
                "linear_project": "[Studio] Project Ironman",
                "timetable_path": "C:\\timetable.txt",
                "last_synced_commit": "abc1234",
                "known_openspec_changes": ["some-change"],
                "last_artifact_check_at": "2026-09-08T00:00:00Z",
                "advanced_workflow_gaps": [],
            }

            save_config(repo_root, config)
            loaded = load_config(repo_root)

            self.assertEqual(loaded, config)

    def test_creates_claude_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as repo_root:
            save_config(
                repo_root,
                {
                    "linear_team": "X",
                    "linear_project": "Y",
                    "timetable_path": "C:\\timetable.txt",
                    "last_synced_commit": "z",
                    "known_openspec_changes": [],
                    "last_artifact_check_at": "2026-09-08T00:00:00Z",
                    "advanced_workflow_gaps": [],
                },
            )

            self.assertTrue(
                os.path.exists(os.path.join(repo_root, ".claude", "synclinear.json"))
            )


if __name__ == "__main__":
    unittest.main()
