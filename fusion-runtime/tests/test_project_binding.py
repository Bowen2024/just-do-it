import json
import os
from pathlib import Path
import shutil

from ui_test_support import UiFixture, tree_snapshot


class ProjectBindingTests(UiFixture):
    def binding_module(self):
        return self.load_foundation_module("project_binding")

    def spare(self):
        fixture = UiFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def enable_explicit(self):
        self.config["project_path_mode"] = "explicit"
        self.config["projects_root"] = str(self.root / "old-root-does-not-exist")
        self.config["project_directories"] = {"invalid": "../not-a-direct-child"}
        self.write_config()

    def test_explicit_mode_uses_persistent_identity_and_ignores_legacy_locations(self):
        self.enable_explicit()
        binding = self.binding_module().bind_project(self.foundation, str(self.project_p1))
        self.assertEqual(binding.mode, "explicit")
        self.assertEqual(binding.root, self.project_p1.resolve())
        self.assertEqual(binding.project_id, "procurement-demo")
        self.assertEqual(binding.identity_source, "persisted")
        self.assertEqual(binding.state, "initialized")
        self.connect()
        runtime = self.server.tools.runtime
        self.assertIsNone(runtime.projects_root)
        self.assertEqual(runtime.project_path_mode, "explicit")
        self.assertEqual(len(self.mcp.load_shared.__globals__["SHARED_MODULES"]), 10)
        self.assertEqual(
            Path(runtime.modules.project_binding.__file__).resolve(),
            (self.foundation / "file_tools/project_binding.py").resolve(),
        )

    def test_invalid_modes_are_rejected_without_fallback(self):
        check = self.load_foundation_module("check_foundation")
        for value in ("unknown", "", None, True, False, 1, [], {}):
            with self.subTest(value=value):
                self.config["project_path_mode"] = value
                self.write_config()
                with self.assertRaisesRegex(ValueError, "project_path_mode"):
                    check.check(self.foundation)
                loader = self.load_mcp(suffix="invalid-mode")
                with self.assertRaises(Exception) as caught:
                    loader.load_shared(self.foundation)
                self.assertEqual(caught.exception.code, "foundation_invalid")

    def test_legacy_rooted_mode_retains_existing_root_contract(self):
        self.config["project_path_mode"] = "legacy_rooted"
        self.write_config()
        bound = self.binding_module().bind_project(self.foundation, str(self.project_p1))
        self.assertEqual(bound.mode, "legacy_rooted")
        self.assertEqual(bound.project_id, "procurement-demo")
        self.connect()
        self.assertEqual(self.server.runtime.projects_root, self.projects.resolve())

    def test_legacy_modes_reject_outside_and_grandchild_without_writes(self):
        for mode in ("L0", "L1"):
            with self.subTest(mode=mode):
                fixture = self.spare()
                if mode == "L1":
                    fixture.config["project_path_mode"] = "legacy_rooted"
                    fixture.write_config()
                binding = fixture.load_foundation_module("project_binding")
                direct = binding.bind_project(fixture.foundation, str(fixture.project_p1))
                self.assertEqual(direct.project_id, "procurement-demo")
                outside = fixture.outside / "采购演示"
                grandchild = fixture.projects / "nested" / "采购演示"
                for target in (outside, grandchild):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(fixture.project_p1, target)
                before_projects = tree_snapshot(fixture.projects)
                before_outside = tree_snapshot(fixture.outside)
                before_config = (fixture.foundation / "config/local.json").read_bytes()
                for target in (outside, grandchild):
                    with self.subTest(mode=mode, target=target):
                        with self.assertRaisesRegex(ValueError, "业务根目录下的直接子目录"):
                            binding.bind_project(fixture.foundation, str(target))
                self.assertEqual(tree_snapshot(fixture.projects), before_projects)
                self.assertEqual(tree_snapshot(fixture.outside), before_outside)
                self.assertEqual((fixture.foundation / "config/local.json").read_bytes(), before_config)

    def test_legacy_mapping_must_match_persistent_identity(self):
        for mode in ("L0", "L1"):
            with self.subTest(mode=mode):
                fixture = self.spare()
                fixture.config["project_directories"] = {
                    "other-id": fixture.project_p1.name,
                    "meeting-b": fixture.project_p2.name,
                }
                if mode == "L1":
                    fixture.config["project_path_mode"] = "legacy_rooted"
                fixture.write_config()
                before = tree_snapshot(fixture.projects)
                with self.assertRaisesRegex(ValueError, "目录映射与持久身份冲突"):
                    fixture.load_foundation_module("project_binding").bind_project(
                        fixture.foundation, str(fixture.project_p1))
                self.assertEqual(tree_snapshot(fixture.projects), before)

    def test_ui_new_shared_module_missing_and_drift_are_detected(self):
        target = self.foundation / "file_tools/project_binding.py"
        original = target.read_bytes()
        for mutation in ("changed", "missing"):
            with self.subTest(mutation=mutation):
                if mutation == "changed":
                    target.write_bytes(original + b"\n# drift\n")
                else:
                    target.unlink()
                loader = self.load_mcp(suffix=f"binding-{mutation}")
                with self.assertRaises(Exception) as caught:
                    loader.load_shared(self.foundation)
                self.assertEqual(
                    caught.exception.code,
                    "dependency_changed" if mutation == "changed" else "dependency_missing",
                )
                target.write_bytes(original)

    def test_invalid_paths_and_root_symlinks_are_rejected_without_writes(self):
        binding = self.binding_module()
        file_target = self.root / "not-a-directory"
        file_target.write_text("sentinel", encoding="utf-8")
        link = self.projects / "linked-project"
        link.symlink_to(self.project_p1, target_is_directory=True)
        broken = self.projects / "broken-project"
        broken.symlink_to(self.root / "missing-target", target_is_directory=True)
        cases = (
            "", "relative/project", "~/project", str(self.projects / "../escape"),
            str(self.projects / "bad\nname"), None, 3, str(file_target), str(link), str(broken),
        )
        before = tree_snapshot(self.projects)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    binding.bind_project(self.foundation, value, allow_uninitialized=True)
        self.assertEqual(tree_snapshot(self.projects), before)
        self.assertEqual(file_target.read_text(encoding="utf-8"), "sentinel")

    def test_metadata_types_json_schema_and_identity_fail_closed(self):
        for case in ("symlink", "hardlink", "directory", "json", "schema", "identity", "fifo"):
            with self.subTest(case=case):
                fixture = self.spare()
                metadata = fixture.project_p1 / "project.json"
                original = metadata.read_bytes()
                metadata.unlink()
                if case == "symlink":
                    other = fixture.root / "metadata-copy.json"
                    other.write_bytes(original)
                    metadata.symlink_to(other)
                elif case == "hardlink":
                    other = fixture.root / "metadata-copy.json"
                    other.write_bytes(original)
                    os.link(other, metadata)
                elif case == "directory":
                    metadata.mkdir()
                elif case == "json":
                    metadata.write_text("{broken", encoding="utf-8")
                elif case == "schema":
                    metadata.write_text('{"schema_version":2,"project_id":"procurement-demo"}', encoding="utf-8")
                elif case == "identity":
                    metadata.write_text('{"schema_version":1,"project_id":"BAD"}', encoding="utf-8")
                elif hasattr(os, "mkfifo"):
                    os.mkfifo(metadata)
                else:
                    metadata.write_bytes(original)
                before = tree_snapshot(fixture.project_p1)
                with self.assertRaises(ValueError):
                    fixture.load_foundation_module("project_binding").bind_project(
                        fixture.foundation, str(fixture.project_p1))
                self.assertEqual(tree_snapshot(fixture.project_p1), before)

    def test_uninitialized_states_and_explicit_initialized_promotion(self):
        binding = self.binding_module()
        missing = self.projects / "多级 项目"
        suggested = binding.bind_project(self.foundation, str(missing), allow_uninitialized=True)
        self.assertEqual(suggested.state, "missing")
        self.assertEqual(suggested.identity_source, "path_digest")
        self.assertTrue(suggested.project_id.startswith("req-"))
        self.assertFalse(missing.exists())
        missing.mkdir()
        empty = binding.bind_project(self.foundation, str(missing), allow_uninitialized=True)
        self.assertEqual(empty.state, "empty")
        (missing / "project.json").write_text(
            json.dumps({"schema_version": 1, "project_id": empty.project_id}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "bind_initialized"):
            binding.revalidate(empty)
        promoted = binding.bind_initialized(empty)
        self.assertEqual(promoted.state, "initialized")
        self.assertEqual(promoted.identity_source, "persisted")
        binding.revalidate(promoted, require_initialized=True)
        nonempty = self.projects / "nonempty"
        nonempty.mkdir()
        (nonempty / "sentinel").write_text("keep", encoding="utf-8")
        state = binding.bind_project(self.foundation, str(nonempty), allow_uninitialized=True)
        self.assertEqual(state.state, "nonempty_uninitialized")
        with self.assertRaises(ValueError):
            binding.bind_initialized(state)
        with self.assertRaises(ValueError):
            binding.bind_project(self.foundation, str(self.root / "missing-parent/project"),
                                 allow_uninitialized=True)

    def test_requested_id_only_applies_to_new_projects(self):
        binding = self.binding_module()
        new = self.projects / "new-project"
        created = binding.bind_project(
            self.foundation, str(new), allow_uninitialized=True, requested_project_id="custom-id")
        self.assertEqual(created.project_id, "custom-id")
        with self.assertRaisesRegex(ValueError, "持久身份冲突"):
            binding.bind_project(
                self.foundation, str(self.project_p1), requested_project_id="different-id")

    def test_revalidation_detects_root_and_parent_rebinding(self):
        binding = self.binding_module()
        original = binding.bind_project(self.foundation, str(self.project_p1))
        moved = self.projects / "moved-original"
        self.project_p1.rename(moved)
        self.project_p1.mkdir()
        shutil.copytree(moved, self.project_p1, dirs_exist_ok=True)
        with self.assertRaisesRegex(ValueError, "目录身份"):
            binding.revalidate(original)
        self.assertEqual(tree_snapshot(moved), tree_snapshot(self.project_p1))

        fixture = self.spare()
        other = binding.bind_project(fixture.foundation, str(fixture.project_p1))
        real_parent = fixture.root / "real-parent"
        fixture.projects.rename(real_parent)
        fixture.projects.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            binding.revalidate(other)

    def test_atomic_metadata_replace_is_allowed_but_identity_change_is_not(self):
        binding = self.binding_module()
        bound = binding.bind_project(self.foundation, str(self.project_p1))
        metadata = self.project_p1 / "project.json"
        data = json.loads(metadata.read_text(encoding="utf-8"))
        temporary = self.project_p1 / "project.json.tmp"
        data["name"] = "原子替换仍然合法"
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, metadata)
        binding.revalidate(bound, require_initialized=True)
        data["project_id"] = "different-id"
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, metadata)
        with self.assertRaisesRegex(ValueError, "持久身份"):
            binding.revalidate(bound)

    def test_environment_and_shared_source_drift_invalidate_binding(self):
        binding = self.binding_module()
        bound = binding.bind_project(self.foundation, str(self.project_p1))
        self.config["unrelated_runtime_change"] = True
        self.write_config()
        with self.assertRaisesRegex(ValueError, "运行基线"):
            binding.revalidate(bound)

        fixture = self.spare()
        other = fixture.load_foundation_module("project_binding").bind_project(
            fixture.foundation, str(fixture.project_p1))
        source = fixture.foundation / "file_tools/project_binding.py"
        source.write_bytes(source.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "运行基线"):
            fixture.load_foundation_module("project_binding").revalidate(other)

    def test_protected_installation_upstream_and_custom_roots_are_rejected(self):
        binding = self.binding_module()
        custom = self.root / "custom-protected"
        custom.mkdir()
        targets = (
            self.foundation, self.foundation.parent, self.foundation / "child",
            self.ui, self.upstream, custom, custom / "child",
        )
        for target in targets:
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "不得与工具或上游目录重叠"):
                    binding.bind_project(
                        self.foundation, str(target), allow_uninitialized=True, protected_roots=(custom,))

    def test_binding_fingerprint_uses_path_not_only_project_id(self):
        self.enable_explicit()
        binding = self.binding_module()
        first = binding.bind_project(self.foundation, str(self.project_p1))
        again = binding.bind_project(self.foundation, str(self.project_p1))
        clone = self.projects / "same-id-clone"
        shutil.copytree(self.project_p1, clone)
        other = binding.bind_project(self.foundation, str(clone))
        self.assertEqual(first.project_id, other.project_id)
        self.assertEqual(binding.binding_fingerprint(first), binding.binding_fingerprint(again))
        self.assertNotEqual(binding.binding_fingerprint(first), binding.binding_fingerprint(other))

    def test_minimal_identity_does_not_replace_full_project_validation(self):
        binding = self.binding_module()
        minimal = self.projects / "minimal"
        minimal.mkdir()
        (minimal / "project.json").write_text(
            '{"schema_version":1,"project_id":"minimal"}', encoding="utf-8")
        bound = binding.bind_project(self.foundation, str(minimal))
        self.assertEqual(bound.state, "initialized")
        project_init = self.load_foundation_module("project_init")
        with self.assertRaisesRegex(ValueError, "基础文件缺失"):
            project_init.load_project(minimal, "minimal")
