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
                        "last_synced_commit": "de1c2c8",
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["linear_team"], "Studio")
            self.assertEqual(config["linear_project"], "[Studio] Project Ironman")
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


class TestSaveConfig(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as repo_root:
            config = {
                "linear_team": "Studio",
                "linear_project": "[Studio] Project Ironman",
                "last_synced_commit": "abc1234",
            }

            save_config(repo_root, config)
            loaded = load_config(repo_root)

            self.assertEqual(loaded, config)

    def test_creates_claude_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as repo_root:
            save_config(
                repo_root,
                {"linear_team": "X", "linear_project": "Y", "last_synced_commit": "z"},
            )

            self.assertTrue(
                os.path.exists(os.path.join(repo_root, ".claude", "synclinear.json"))
            )


if __name__ == "__main__":
    unittest.main()
