import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_foundation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import project_init as project


class ProjectTests(unittest.TestCase):
    setUp = test_foundation.FoundationTests.setUp
    write_config = test_foundation.FoundationTests.write_config

    def create(self):
        return project.create(self.app, "demo", "中文试点", "验证项目共享")

    def test_plan_never_writes(self):
        result = project.plan(self.app, "demo", "中文试点", "验证项目共享")
        self.assertEqual(result["status"], "planned")
        self.assertFalse((self.projects / "demo").exists())
        self.assertFalse(result["github"]["authentication_checked"])

    def test_minimal_files_and_pending_remote(self):
        result = self.create()
        target = self.projects / "demo"
        self.assertEqual({p.name for p in target.iterdir()}, {"README.md", ".gitignore", "project.json"})
        self.assertFalse(result["git_initialized"])
        self.assertEqual(result["recorded_steps"]["github_repository"]["status"], "pending")
        self.assertIn("中文试点", (target / "README.md").read_text())
        data = json.loads((target / "project.json").read_text())
        self.assertIsNone(data["artifacts"]["requirements"])
        self.assertIsNone(data["github"]["url"])

    def test_duplicate_preserves_changes(self):
        self.create()
        readme = self.projects / "demo/README.md"
        readme.write_text("user edits")
        with self.assertRaisesRegex(ValueError, "占用"):
            self.create()
        self.assertEqual(readme.read_text(), "user edits")

    def test_invalid_ids_fail_before_creation(self):
        for identifier in ("../escape", "a/b", "../", "Demo", "-demo", "a" * 65, ""):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                project.plan(self.app, identifier, "Name", "Purpose")
        self.assertEqual(list(self.projects.iterdir()), [])

    def test_occupied_file_and_broken_link(self):
        target = self.projects / "demo"
        target.write_text("existing")
        with self.assertRaises(ValueError):
            self.create()
        target.unlink()
        target.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "软链"):
            self.create()

    def test_parent_git_repository_blocks_creation(self):
        result = project.git(self.projects, "init", "--template=", "-b", "main")
        self.assertEqual(result.returncode, 0)
        with self.assertRaisesRegex(ValueError, "父目录属于已有仓库"):
            self.create()
        self.assertFalse((self.projects / "demo").exists())

    def test_git_initialization_and_repeat_no_commit_or_remote(self):
        self.create()
        first = project.init_git(self.app, "demo")
        second = project.init_git(self.app, "demo")
        self.assertTrue(first["git_initialized"])
        self.assertTrue(second["git_state_matches_record"])
        target = self.projects / "demo"
        self.assertNotEqual(project.git(target, "rev-parse", "--verify", "HEAD").returncode, 0)
        self.assertEqual(project.git(target, "remote").stdout, "")
        self.assertEqual(project.git(target, "diff", "--cached", "--name-only").stdout, "")
        for path in ("materials/customer.txt", ".env", "secret.key", "node_modules/a.js"):
            self.assertEqual(project.git(target, "check-ignore", path).returncode, 0)

    def test_git_failure_is_recorded_and_retry_preserves_readme(self):
        self.create()
        original = project.git

        def fail_init(path, *args):
            if args[0] == "init":
                return subprocess.CompletedProcess([], 1, "", "failure")
            return original(path, *args)

        with patch.object(project, "git", side_effect=fail_init):
            with self.assertRaisesRegex(ValueError, "Git 初始化失败"):
                project.init_git(self.app, "demo")
        target = self.projects / "demo"
        data = json.loads((target / "project.json").read_text())
        self.assertEqual(data["initialization"]["local_git"]["status"], "failed")
        before = (target / "README.md").read_bytes()
        self.assertTrue(project.init_git(self.app, "demo")["git_initialized"])
        self.assertEqual(before, (target / "README.md").read_bytes())

    def test_stale_lock_is_not_removed(self):
        self.create()
        lock = self.projects / "demo/.project-init.lock"
        lock.write_text("other process")
        with self.assertRaisesRegex(ValueError, "锁已存在"):
            project.init_git(self.app, "demo")
        self.assertEqual(lock.read_text(), "other process")

    def test_metadata_symlink_is_rejected(self):
        self.create()
        metadata = self.projects / "demo/project.json"
        metadata.unlink()
        metadata.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "基础文件"):
            project.init_git(self.app, "demo")
        self.assertEqual(self.source.read_text(), "original")

    def test_wrong_project_identity_is_rejected(self):
        self.create()
        metadata = self.projects / "demo/project.json"
        data = json.loads(metadata.read_text())
        data["project_id"] = "someone-else"
        metadata.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "身份"):
            project.inspect(self.app, "demo")

    def test_upstream_drift_blocks_new_project(self):
        self.source.write_text("changed")
        with self.assertRaisesRegex(ValueError, "漂移"):
            self.create()
        self.assertEqual(list(self.projects.iterdir()), [])

    def test_cli_new_without_apply_is_only_preview(self):
        result = subprocess.run([sys.executable, "-B", project.__file__, "--foundation",
                                 str(self.app), "new", "demo", "--name", "中文试点",
                                 "--purpose", "验证共享"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "planned")
        self.assertFalse((self.projects / "demo").exists())

    def test_partial_creation_is_preserved_for_inspection(self):
        original = Path.open

        def fail_ignore(path, *args, **kwargs):
            if path == (self.projects / "demo/.gitignore").resolve() and args and args[0] == "x":
                raise PermissionError("test failure")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", fail_ignore):
            with self.assertRaisesRegex(ValueError, "部分创建失败"):
                self.create()
        self.assertTrue((self.projects / "demo/README.md").is_file())
        with self.assertRaisesRegex(ValueError, "基础文件缺失"):
            project.inspect(self.app, "demo")
        with self.assertRaisesRegex(ValueError, "占用"):
            self.create()


if __name__ == "__main__":
    unittest.main()
