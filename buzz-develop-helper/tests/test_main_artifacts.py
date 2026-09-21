import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_foundation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifacts
import main_artifacts
import project_init
import project_state
import requirements


class MainArtifactTests(unittest.TestCase):
    setUp = test_foundation.FoundationTests.setUp
    write_config = test_foundation.FoundationTests.write_config

    def project(self, project_id="demo"):
        project_init.create(self.app, project_id, "成果写入试点", "验证一致性与恢复")
        root = (self.projects / project_id).resolve()
        requirements.save_draft(self.app, project_id, "# 需求 v0.1\n\n保持草案。", "missing")
        return root

    def authorization(self, *project_ids):
        return main_artifacts._issue_runtime_main(
            "main-test", "test-runtime", project_ids or ("demo",), runtime_verified=True)

    def preview(self, project_id="demo"):
        return artifacts.preview_register(
            self.app, project_id, "requirements", "requirements", "v0.1",
            "requirements", "方案讨论", "首版需求草案",
            path="docs/requirements.md", set_current=True,
        )

    def apply(self, authorization=None, project_id="demo", preview=None, **extra):
        preview = preview or self.preview(project_id)
        values = {
            "artifact_id": "requirements", "kind": "requirements", "version": "v0.1",
            "producer_role": "requirements", "purpose": "方案讨论",
            "summary": "首版需求草案", "path": "docs/requirements.md", "set_current": True,
            "expected_project_sha256": preview["project_json_precondition"]["sha256"],
            "expected_readme_sha256": preview["proposed_changes"]["readme"]["before_sha256"],
        }
        values.update(extra)
        return main_artifacts.apply_registration(
            authorization or self.authorization(project_id), self.app, project_id, **values)

    def test_main_apply_writes_consistent_registry_and_readme(self):
        root = self.project()
        modes = {name: (root / name).stat().st_mode & 0o777
                 for name in ("project.json", "README.md")}
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        data = json.loads((root / "project.json").read_text())
        version = data["artifact_registry"]["entries"]["requirements"]["versions"][0]
        self.assertEqual(data["artifacts"]["requirements"], "docs/requirements.md")
        self.assertEqual(version["registration"]["actor"]["principal_id"], "main-test")
        self.assertEqual(version["confirmation_ids"], [])
        self.assertEqual(version["document_status"], "Draft")
        self.assertIn(artifacts.MARKER_START, (root / "README.md").read_text())
        self.assertFalse((root / project_state.JOURNAL_NAME).exists())
        self.assertFalse((root / project_state.LOCK_NAME).exists())
        self.assertEqual(
            modes,
            {name: (root / name).stat().st_mode & 0o777
             for name in ("project.json", "README.md")},
        )
        self.assertEqual(artifacts.inspect(self.app, "demo")["status"], "consistent")
        self.assertFalse(result["approval_changed"])
        self.assertFalse(result["handoff_started"])

    def test_untrusted_or_wrong_project_authorization_is_rejected(self):
        root = self.project()
        before = (root / "project.json").read_bytes()
        with self.assertRaisesRegex(PermissionError, "Main capability"):
            self.apply(authorization={"role": "main"})
        with self.assertRaisesRegex(PermissionError, "未授权"):
            self.apply(authorization=self.authorization("other"))
        self.assertEqual(before, (root / "project.json").read_bytes())

    def test_optimistic_project_and_readme_conflicts_do_not_write(self):
        root = self.project()
        preview = self.preview()
        with self.assertRaisesRegex(ValueError, "project.json 乐观摘要冲突"):
            self.apply(preview=preview, expected_project_sha256="0" * 64)
        self.assertFalse((root / project_state.JOURNAL_NAME).exists())
        preview = self.preview()
        readme = root / "README.md"
        readme.write_text(readme.read_text() + "\n外部编辑。\n")
        before_project = (root / "project.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "README.md 乐观摘要冲突"):
            self.apply(preview=preview)
        self.assertEqual(before_project, (root / "project.json").read_bytes())
        self.assertFalse((root / project_state.JOURNAL_NAME).exists())

    def test_interrupted_write_rolls_forward_from_journal(self):
        root = self.project()

        def fail_after_project(stage):
            self.assertEqual(stage, "after-project-json")
            raise RuntimeError("simulated interruption")

        with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
            self.apply(_failure_hook=fail_after_project)
        self.assertTrue((root / project_state.JOURNAL_NAME).is_file())
        self.assertIn("artifact_registry", json.loads((root / "project.json").read_text()))
        self.assertNotIn(artifacts.MARKER_START, (root / "README.md").read_text())
        recovered = main_artifacts.recover_registration(
            self.authorization("demo"), self.app, "demo")
        self.assertEqual(recovered["recovered_files"], ["README.md"])
        self.assertEqual(recovered["already_complete_files"], ["project.json"])
        self.assertFalse((root / project_state.JOURNAL_NAME).exists())
        self.assertEqual(artifacts.inspect(self.app, "demo")["status"], "consistent")

    def test_final_check_failure_keeps_journal_for_recovery(self):
        root = self.project()
        with mock.patch.object(artifacts, "inspect", return_value={"status": "attention_required"}):
            with self.assertRaisesRegex(RuntimeError, "一致性检查未通过"):
                self.apply()
        self.assertTrue((root / project_state.JOURNAL_NAME).is_file())
        recovered = main_artifacts.recover_registration(
            self.authorization("demo"), self.app, "demo")
        self.assertEqual(recovered["recovered_files"], [])
        self.assertEqual(
            recovered["already_complete_files"], ["project.json", "README.md"])
        self.assertFalse((root / project_state.JOURNAL_NAME).exists())

    def test_recovery_refuses_transaction_external_changes(self):
        root = self.project()

        def fail(_stage):
            raise RuntimeError("stop")

        with self.assertRaises(RuntimeError):
            self.apply(_failure_hook=fail)
        readme = root / "README.md"
        readme.write_text("external edit")
        with self.assertRaisesRegex(ValueError, "事务外修改"):
            main_artifacts.recover_registration(
                self.authorization("demo"), self.app, "demo")
        self.assertEqual(readme.read_text(), "external edit")
        self.assertTrue((root / project_state.JOURNAL_NAME).exists())

    def test_mid_transaction_edit_is_not_overwritten(self):
        root = self.project()
        readme = root / "README.md"

        def edit_readme(_stage):
            readme.write_text("mid-transaction edit")

        with self.assertRaisesRegex(RuntimeError, "README.md 在替换前发生变化"):
            self.apply(_failure_hook=edit_readme)
        self.assertEqual(readme.read_text(), "mid-transaction edit")
        self.assertTrue((root / project_state.JOURNAL_NAME).exists())
        with self.assertRaisesRegex(ValueError, "事务外修改"):
            main_artifacts.recover_registration(
                self.authorization("demo"), self.app, "demo")
        self.assertEqual(readme.read_text(), "mid-transaction edit")

    def test_existing_project_state_lock_is_preserved(self):
        root = self.project()
        lock = root / project_state.LOCK_NAME
        lock.write_text("other operation")
        before = (root / "project.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "项目状态写入锁已存在"):
            self.apply()
        self.assertEqual(lock.read_text(), "other operation")
        self.assertEqual(before, (root / "project.json").read_bytes())

    def test_requirements_and_project_init_share_project_state_lock(self):
        root = self.project()
        lock = root / project_state.LOCK_NAME
        lock.write_text("main in progress")
        current = requirements.context(self.app, "demo")["documents"][-1]["sha256"]
        with self.assertRaisesRegex(ValueError, "项目状态写入锁已存在"):
            requirements.save_draft(self.app, "demo", "第二版", current)
        self.assertEqual(lock.read_text(), "main in progress")

        project_init.create(self.app, "other", "另一个项目", "验证公共锁")
        other = self.projects / "other"
        other_lock = other / project_state.LOCK_NAME
        other_lock.write_text("main in progress")
        with self.assertRaisesRegex(ValueError, "项目状态写入锁已存在"):
            project_init.init_git(self.app, "other")
        self.assertEqual(other_lock.read_text(), "main in progress")

    def test_repeat_apply_is_idempotent(self):
        root = self.project()
        first = self.apply()
        preview = self.preview()
        second = self.apply(preview=preview)
        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "unchanged")
        self.assertFalse((root / project_state.JOURNAL_NAME).exists())

    def test_main_mutation_core_has_no_cli(self):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(main_artifacts.__file__))],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("没有 CLI", result.stderr)


if __name__ == "__main__":
    unittest.main()
