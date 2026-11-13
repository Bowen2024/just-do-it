import os
from pathlib import Path
import shutil

from solution_test_support import SolutionFixture


class SolutionExplicitPathTests(SolutionFixture):
    def setUp(self):
        super().setUp()
        self.project_a = self.root / "external-a/nested/采购 需求预测"
        self.project_b = self.root / "external-b/another/方案副本"
        self.init_project(self.project_a, "persisted-solution")
        self.init_project(self.project_b, "other-solution")
        self.config["project_path_mode"] = "explicit"
        self.config["projects_root"] = str(self.root / "missing-old-root")
        self.config["project_directories"] = {"stale": "../old-mapping"}
        self.write_config()
        self.connect(allow_save=True)
        self.initialize()

    def prepare_valid(self, project=None):
        project = project or self.project_a
        self.write_requirements_and_prd(project)
        self.confirm_prd(project)
        return self.read_context(project)

    def save(self, read, content=None, profile="Lite", *, project=None, error=False):
        project = project or self.project_a
        return self.call(self.mcp.SAVE_DRAFT, {
            "project_path": str(project),
            "read_id": read["read_receipt"]["read_id"],
            "content": content or self.tech_spec(),
            "profile": profile,
        }, error=error)

    def snapshot(self, root):
        result = {}
        for directory, folders, files in os.walk(root):
            for name in folders + files:
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                result[relative] = "link:" + os.readlink(path) if path.is_symlink() else (
                    path.read_bytes() if path.is_file() else None
                )
        return result

    def test_explicit_full_lifecycle_uses_persistent_identity_and_history(self):
        before_config = (self.foundation / "config/local.json").read_bytes()
        read = self.prepare_valid()
        self.assertEqual(read["project"]["project_id"], "persisted-solution")
        self.assertEqual(read["project"]["project_path"], str(self.project_a))
        self.assertEqual(read["prd_structure"]["status"], "ready_for_review")
        first = self.save(read, self.tech_spec("第一版"))
        self.assertEqual(first["write_outcome"], "saved")
        second = self.save(self.read_context(), self.tech_spec("第二版"), profile="Standard")
        self.assertEqual(second["write_outcome"], "saved")
        history = self.read_context(history_sha256=first["target"]["sha256"])
        self.assertEqual(history["history"]["status"], "present")
        self.assertIn("第一版", history["history"]["content"])
        current = self.call(self.mcp.INSPECT, {
            "project_path": str(self.project_a), "target": "current",
        })
        self.assertEqual(current["structure"]["status"], "pass", current["structure"]["issues"])
        other = self.prepare_valid(self.project_b)
        self.assertEqual(other["project"]["project_id"], "other-solution")
        self.assertFalse((self.project_a / self.project_a.name).exists())
        self.assertEqual((self.foundation / "config/local.json").read_bytes(), before_config)

    def test_missing_confirmation_remains_a_business_rejection(self):
        self.write_requirements_and_prd()
        read = self.read_context()
        self.assertEqual(read["read_receipt"]["save_eligible_at_read"], False)
        self.assertEqual(read["read_receipt"]["ineligible_reasons"], ["prd_confirmation_missing"])
        rejected = self.save(read, error=True)
        self.assertEqual(rejected["error"]["code"], "prd_confirmation_missing")
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_same_content_copy_cannot_consume_another_directory_receipt(self):
        self.prepare_valid()
        shutil.rmtree(self.project_b)
        shutil.copytree(self.project_a, self.project_b)
        copied = self.read_context(self.project_b)
        before_a = self.snapshot(self.project_a)
        before_b = self.snapshot(self.project_b)
        rejected = self.save(copied, project=self.project_a, error=True)
        self.assertEqual(rejected["error"]["code"], "dependency_set_changed")
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertEqual(self.snapshot(self.project_a), before_a)
        self.assertEqual(self.snapshot(self.project_b), before_b)

    def test_same_name_projects_alternate_and_reject_cross_receipt(self):
        first = self.root / "external-a/same/同名项目"
        second = self.root / "external-b/same/同名项目"
        self.init_project(first, "same-name-a")
        self.init_project(second, "same-name-b")
        read_a = self.prepare_valid(first)
        read_b = self.prepare_valid(second)
        current_a = self.read_context(first)
        self.assertEqual(current_a["project"]["project_id"], "same-name-a")
        self.assertEqual(read_b["project"]["project_id"], "same-name-b")
        before_a = self.snapshot(first)
        before_b = self.snapshot(second)
        rejected = self.save(read_b, project=first, error=True)
        self.assertEqual(rejected["error"]["code"], "dependency_set_changed")
        self.assertEqual(self.snapshot(first), before_a)
        self.assertEqual(self.snapshot(second), before_b)
        saved = self.save(read_a, project=first)
        self.assertEqual(saved["write_outcome"], "saved")
        self.assertFalse((second / "docs/tech-spec.md").exists())

    def test_runtime_change_invalidates_existing_receipt(self):
        read = self.prepare_valid()
        self.config["unrelated_probe"] = "changed"
        self.write_config()
        rejected = self.save(read, error=True)
        self.assertEqual(rejected["error"]["code"], "runtime_baseline_changed")
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_explicit_path_rejections_do_not_create_or_modify_business_files(self):
        cases = (
            (self.foundation, "path_not_allowed"),
            (self.solution, "path_not_allowed"),
            (self.upstream, "path_not_allowed"),
            (self.project_a / "docs", "project_not_initialized"),
            (self.root / "missing-parent/project", "path_not_allowed"),
            (self.project_a / "../other", "path_not_allowed"),
        )
        before = self.snapshot(self.root)
        for path, code in cases:
            with self.subTest(path=path, code=code):
                rejected = self.call(self.mcp.READ_CONTEXT, {
                    "project_path": str(path),
                }, error=True)
                self.assertEqual(rejected["error"]["code"], code)
        self.assertEqual(self.snapshot(self.root), before)

    def test_directory_replacement_before_locked_snapshot_is_not_written(self):
        read = self.prepare_valid()
        moved = self.root / "external-a/nested/original-project"
        original_gather = self.server.tools._gather
        replaced = {"done": False}
        read_id = read["read_receipt"]["read_id"]

        def replace_then_gather(project_path):
            if read_id not in self.server.tools.reads and not replaced["done"]:
                replaced["done"] = True
                self.project_a.rename(moved)
                shutil.copytree(moved, self.project_a)
            return original_gather(project_path)

        self.server.tools._gather = replace_then_gather
        rejected = self.save(read, error=True)
        self.assertTrue(replaced["done"])
        self.assertEqual(rejected["error"]["code"], "write_failed")
        self.assertIn("写入锁在操作期间被替换", rejected["error"]["message"])
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertTrue(rejected["read_id_consumed"])
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())
        self.assertFalse((moved / "docs/tech-spec.md").exists())

    def test_directory_replacement_between_reads_invalidates_cached_binding(self):
        self.prepare_valid()
        moved = self.root / "external-a/nested/read-original"
        self.project_a.rename(moved)
        shutil.copytree(moved, self.project_a)
        before_a = self.snapshot(self.project_a)
        before_moved = self.snapshot(moved)
        rejected = self.call(self.mcp.READ_CONTEXT, {
            "project_path": str(self.project_a),
        }, error=True)
        self.assertEqual(rejected["error"]["code"], "binding_changed")
        self.assertEqual(self.snapshot(self.project_a), before_a)
        self.assertEqual(self.snapshot(moved), before_moved)

    def test_input_change_before_locked_snapshot_cannot_overwrite(self):
        read = self.prepare_valid()
        original_gather = self.server.tools._gather
        changed = {"done": False}
        read_id = read["read_receipt"]["read_id"]

        def change_then_gather(project_path):
            if read_id not in self.server.tools.reads and not changed["done"]:
                changed["done"] = True
                with (self.project_a / "README.md").open("a", encoding="utf-8") as stream:
                    stream.write("concurrent change\n")
            return original_gather(project_path)

        self.server.tools._gather = change_then_gather
        rejected = self.save(read, error=True)
        self.assertEqual(rejected["error"]["code"], "dependency_set_changed")
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertTrue(rejected["read_id_consumed"])
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_non_target_input_change_before_replace_cannot_overwrite(self):
        read = self.prepare_valid()
        original_gather = self.server.tools._gather
        calls = {"count": 0}

        def change_before_replace(project_path):
            calls["count"] += 1
            if calls["count"] == 3:
                with (self.project_a / "README.md").open("a", encoding="utf-8") as stream:
                    stream.write("last check change\n")
            return original_gather(project_path)

        self.server.tools._gather = change_before_replace
        rejected = self.save(read, error=True)
        self.assertEqual(calls["count"], 3)
        self.assertEqual(rejected["error"]["code"], "dependency_set_changed")
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertTrue(rejected["read_id_consumed"])
        self.assertFalse((self.project_a / "docs/tech-spec.md").exists())

    def test_directory_replacement_after_target_replace_is_unknown(self):
        read = self.prepare_valid()
        moved = self.root / "external-a/nested/post-write-original"
        solution_module = __import__(type(self.server.tools).__module__, fromlist=["os"])
        real_replace = solution_module.os.replace

        def replace_then_swap(source, destination):
            real_replace(source, destination)
            self.project_a.rename(moved)
            shutil.copytree(moved, self.project_a)

        solution_module.os.replace = replace_then_swap
        try:
            rejected = self.save(read, error=True)
        finally:
            solution_module.os.replace = real_replace
        self.assertEqual(rejected["error"]["code"], "write_failed")
        self.assertIn("写入锁在操作期间被替换", rejected["error"]["message"])
        self.assertEqual(rejected["write_outcome"], "unknown")
        self.assertTrue(rejected["side_effects"]["target_replaced"])
        self.assertTrue((self.project_a / "docs/tech-spec.md").is_file())
        self.assertTrue((moved / "docs/tech-spec.md").is_file())

    def test_legacy_rooted_mode_still_rejects_explicit_outside_project(self):
        self.config["project_path_mode"] = "legacy_rooted"
        self.config["projects_root"] = str(self.projects)
        self.config["project_directories"] = {"meeting-b": "会议助手"}
        self.write_config()
        self.connect(allow_save=True)
        self.initialize()
        before = self.snapshot(self.project_a)
        rejected = self.call(self.mcp.READ_CONTEXT, {
            "project_path": str(self.project_a),
        }, error=True)
        self.assertEqual(rejected["error"]["code"], "path_not_allowed")
        self.assertEqual(self.snapshot(self.project_a), before)
        legacy_a = self.projects / "meeting-helper"
        legacy_b = self.projects / "会议助手"
        self.write_requirements_and_prd(legacy_a)
        self.write_requirements_and_prd(legacy_b)
        self.confirm_prd(legacy_a)
        read_a = self.read_context(legacy_a)
        read_b = self.read_context(legacy_b)
        self.assertEqual(read_a["project"]["project_id"], "meeting-helper")
        self.assertEqual(read_b["project"]["project_id"], "meeting-b")
        cross = self.save(read_b, project=legacy_a, error=True)
        self.assertEqual(cross["error"]["code"], "dependency_set_changed")
        self.assertFalse((legacy_a / "docs/tech-spec.md").exists())
        missing = self.save(read_b, project=legacy_b, error=True)
        self.assertEqual(missing["error"]["code"], "prd_confirmation_missing")
        self.assertFalse((legacy_b / "docs/tech-spec.md").exists())
        saved = self.save(read_a, project=legacy_a)
        self.assertEqual(saved["write_outcome"], "saved")
        read_a = self.read_context(legacy_a)
        with (legacy_a / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("legacy external edit\n")
        stale = self.save(read_a, self.tech_spec("不得覆盖"), project=legacy_a, error=True)
        self.assertEqual(stale["error"]["code"], "dependency_set_changed")
        self.assertEqual(stale["write_outcome"], "not_written")
        read_a = self.read_context(legacy_a)
        second = self.save(read_a, self.tech_spec("旧模式第二版"), project=legacy_a)
        self.assertEqual(second["write_outcome"], "saved")
        history = self.read_context(legacy_a, history_sha256=saved["target"]["sha256"])
        self.assertEqual(history["history"]["status"], "present")
        read_a = self.read_context(legacy_a)
        self.config["legacy_runtime_probe"] = "changed"
        self.write_config()
        drift = self.save(read_a, self.tech_spec("基线变化"), project=legacy_a, error=True)
        self.assertEqual(drift["error"]["code"], "runtime_baseline_changed")
        self.assertEqual(drift["write_outcome"], "not_written")


if __name__ == "__main__":
    import unittest

    unittest.main()
