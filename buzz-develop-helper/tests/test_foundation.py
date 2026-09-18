"""All mutations are confined to disposable test fixtures, never real upstream."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_foundation.py"
spec = importlib.util.spec_from_file_location("foundation", SCRIPT)
foundation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(foundation)


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="buzz-foundation-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "fusion"
        self.upstream = self.root / "source"
        self.projects = self.root / "projects"
        for directory in (self.app / "config", self.app / "upstream", self.upstream, self.projects):
            directory.mkdir(parents=True)
        self.source = self.upstream / "rules.md"
        self.source.write_text("original", encoding="utf-8")
        self.config = {"schema_version": 1, "upstream_root": str(self.upstream),
                       "projects_root": str(self.projects)}
        self.write_config()
        self.link = self.app / "upstream/develop-helper"
        self.link.symlink_to(self.upstream, target_is_directory=True)
        self.lock = self.app / "upstream-lock.json"
        self.lock.write_text(json.dumps(foundation.snapshot(self.upstream)), encoding="utf-8")

    def write_config(self):
        (self.app / "config/local.json").write_text(json.dumps(self.config), encoding="utf-8")

    def test_success_is_read_only_and_does_not_claim_runtime_security(self):
        before = self.source.stat().st_mtime_ns
        result = foundation.check(self.app)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["runtime_readonly_enforced"])
        self.assertEqual(self.source.read_text(), "original")
        self.assertEqual(before, self.source.stat().st_mtime_ns)

    def test_changed_source_fails_without_refreshing_lock(self):
        before = self.lock.read_bytes()
        self.source.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "漂移"):
            foundation.check(self.app)
        self.assertEqual(before, self.lock.read_bytes())

    def test_new_file_fails(self):
        (self.upstream / "new.md").write_text("new")
        with self.assertRaisesRegex(ValueError, "漂移"):
            foundation.check(self.app)

    def test_deleted_file_fails(self):
        self.source.unlink()
        with self.assertRaisesRegex(ValueError, "漂移"):
            foundation.check(self.app)

    def test_broken_link_fails(self):
        self.link.unlink()
        self.link.symlink_to(self.root / "absent")
        with self.assertRaises(OSError):
            foundation.check(self.app)

    def test_wrong_link_target_fails(self):
        self.link.unlink()
        self.link.symlink_to(self.projects)
        with self.assertRaisesRegex(ValueError, "不一致"):
            foundation.check(self.app)

    def test_regular_directory_not_accepted_as_link(self):
        self.link.unlink()
        self.link.mkdir()
        with self.assertRaisesRegex(ValueError, "不是软链"):
            foundation.check(self.app)

    def test_relative_config_path_fails(self):
        self.config["projects_root"] = "../projects"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "绝对路径"):
            foundation.check(self.app)

    def test_overlapping_project_root_fails(self):
        self.config["projects_root"] = str(self.root)
        self.write_config()
        with self.assertRaisesRegex(ValueError, "互相包含"):
            foundation.check(self.app)

    def test_missing_project_directory_fails(self):
        self.projects.rmdir()
        with self.assertRaises(OSError):
            foundation.check(self.app)

    def test_invalid_lock_fails(self):
        self.lock.write_text('{"schema_version": 99}')
        with self.assertRaisesRegex(ValueError, "锁定格式"):
            foundation.check(self.app)

    def test_internal_link_is_not_followed(self):
        external = self.root / "external.txt"
        external.write_text("private")
        (self.upstream / "reference").symlink_to(external)
        before = foundation.snapshot(self.upstream)
        external.write_text("different")
        self.assertEqual(before, foundation.snapshot(self.upstream))

    def test_projects_and_dependencies_are_excluded(self):
        before = foundation.snapshot(self.upstream)
        for name in ("Projects_Repo", "node_modules", ".venv", ".git"):
            directory = self.upstream / name
            directory.mkdir()
            (directory / "ignored").write_text("not part of source lock")
        self.assertEqual(before, foundation.snapshot(self.upstream))

    def test_cli_returns_nonzero_on_failure(self):
        self.source.write_text("changed")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "check",
                                 "--foundation", str(self.app)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
