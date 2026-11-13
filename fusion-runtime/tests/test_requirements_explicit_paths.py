import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest
from unittest import mock

import test_requirements_cursor_tools as fixtures
import cursor_mcp as mcp
from test_requirements_prd_tools import PRD_BODY


class RequirementsExplicitPathTests(unittest.TestCase):
    def setUp(self):
        fixtures.CursorToolsTests.setUp(self)
        self.external_a = self.root / "external-a"
        self.external_b = self.root / "external-b"
        self.external_a.mkdir()
        self.external_b.mkdir()
        self.config["project_path_mode"] = "explicit"
        self.config["projects_root"] = str(self.root / "old-root-does-not-exist")
        self.config["project_directories"] = {"stale": "../not-a-direct-child"}
        self.write_config()
        self.connect()

    write_config = fixtures.CursorToolsTests.write_config
    new_tools = fixtures.CursorToolsTests.new_tools
    meta = staticmethod(fixtures.CursorToolsTests.meta)
    rpc = fixtures.CursorToolsTests.rpc
    call = fixtures.CursorToolsTests.call

    def connect(self, **options):
        options.setdefault("allow_initialize", True)
        options.setdefault("allow_save", True)
        self.server = mcp.McpServer(mcp.SharedProjectTools(
            foundation=self.foundation, clock=lambda: self.now, **options))

    def operation(self, tool_name, path, *, error=False, **arguments):
        return self.call(tool_name, {"project_path": str(path), **arguments}, error=error)

    def initialize(self, path, project_id=None, *, error=False):
        arguments = {"name": path.name, "purpose": "显式目录隔离测试"}
        if project_id is not None:
            arguments["project_id"] = project_id
        return self.operation(mcp.PROJECT_INITIALIZE, path, error=error, **arguments)

    def read(self, path, **arguments):
        return self.operation(mcp.READ_CONTEXT, path, **arguments)

    def save(self, path, content, receipt, *, error=False):
        return self.operation(mcp.SAVE_DRAFT, path, content=content, read_id=receipt["read_id"], error=error)

    def save_prd(self, path, content, receipt, *, error=False):
        return self.operation(mcp.SAVE_PRD_DRAFT, path, content=content,
                              read_id=receipt["read_id"], error=error)

    def snapshot(self, base):
        if not os.path.lexists(base):
            return None
        result = {}
        for directory, folders, files in os.walk(base):
            for name in folders + files:
                path = Path(directory) / name
                key = path.relative_to(base).as_posix()
                if path.is_symlink():
                    result[key] = "link:" + os.readlink(path)
                elif path.is_file():
                    result[key] = path.read_bytes()
                else:
                    result[key] = None
        return result

    def binding(self, path, project_id=None):
        return mcp.project_binding.bind_project(
            self.foundation, str(path), allow_uninitialized=True,
            requested_project_id=project_id)

    def test_full_explicit_lifecycle_history_recovery_and_repeat_initialization(self):
        path = self.external_a / "多级目录" / "客户 A" / "采购 需求预测"
        path.parent.mkdir(parents=True)
        before_config = (self.foundation / "config/local.json").read_bytes()
        state = self.operation(mcp.PROJECT_INSPECT, path)
        self.assertEqual(state["status"], "not_created")
        self.assertFalse(path.exists())
        created = self.initialize(path, "custom-req")
        self.assertEqual(created["project_id"], "custom-req")
        self.assertTrue(created["identity_persisted"])
        self.assertFalse((path / path.name).exists())
        self.assertFalse((path / ".git").exists())
        metadata = json.loads((path / "project.json").read_text(encoding="utf-8"))
        initial = metadata["dependencies"]["initialization_binding"]
        self.assertEqual(initial["project_path"], str(path))
        self.assertEqual(initial["project_id"], "custom-req")
        first = self.save(path, "# 需求\n第一版", self.read(path))
        second = self.save(path, "# 需求\n第二版", self.read(path))
        history = self.read(path, history_sha256=first["sha256"])
        self.assertEqual(history["history"]["content"], first["document"]["content"])
        prd = self.save_prd(path, PRD_BODY, self.read(path))
        self.assertTrue(prd["verified"])
        recovered = self.read(path, include_recovery=True)
        self.assertEqual(recovered["recovery"]["project"]["status"], "present")
        self.assertEqual(recovered["recovery"]["prd"]["source"]["requirements_sha256"], second["sha256"])
        updated = self.operation(
            mcp.UPDATE_INFO, path, read_id=recovered["read_id"], changes={"project_type": "web"})
        self.assertEqual(updated["write_outcome"], "saved")
        stale = self.save(path, "不得写入", recovered, error=True)
        self.assertEqual(stale["write_outcome"], "not_written")
        current = self.read(path)
        unchanged = self.save(path, "# 需求\n第二版", current)
        self.assertFalse(unchanged["changed"])
        before = self.snapshot(path)
        repeated = self.initialize(path, "custom-req")
        self.assertFalse(repeated["changed"])
        conflict = self.initialize(path, "different-id", error=True)
        self.assertEqual(conflict["reason"], "identity_conflict")
        self.assertEqual(self.snapshot(path), before)
        self.assertEqual((self.foundation / "config/local.json").read_bytes(), before_config)

    def test_interleaved_same_name_projects_and_cross_project_receipts_are_isolated(self):
        first = self.external_a / "演示"
        second = self.external_b / "演示"
        self.initialize(first)
        self.initialize(second)
        first_read = self.read(first)
        second_read = self.read(second)
        self.assertNotEqual(first_read["project_id"], second_read["project_id"])
        before_first = self.snapshot(first)
        before_second = self.snapshot(second)
        for operation in (
            lambda: self.save(second, "cross-save", first_read, error=True),
            lambda: self.save_prd(second, PRD_BODY, first_read, error=True),
            lambda: self.operation(mcp.UPDATE_INFO, second, read_id=first_read["read_id"],
                                   changes={"project_type": "web"}, error=True),
        ):
            failure = operation()
            self.assertEqual(failure["write_outcome"], "not_written")
        self.assertEqual(self.snapshot(first), before_first)
        self.assertEqual(self.snapshot(second), before_second)
        self.assertTrue(self.save(first, "A 正文", first_read)["verified"])
        self.assertTrue(self.save(second, "B 正文", second_read)["verified"])
        self.assertEqual(self.read(first)["documents"][-1]["content"].splitlines()[-1], "A 正文")
        self.assertEqual(self.read(second)["documents"][-1]["content"].splitlines()[-1], "B 正文")

    def test_same_id_clone_requires_new_read_and_never_shares_receipt(self):
        original = self.external_a / "same-id"
        clone = self.external_b / "same-id-clone"
        self.initialize(original, "shared-id")
        self.save(original, "共同正文", self.read(original))
        shutil.copytree(original, clone)
        original_read = self.read(original)
        clone_read = self.read(clone)
        self.assertEqual(original_read["project_id"], clone_read["project_id"])
        self.assertNotEqual(original_read["read_id"], clone_read["read_id"])
        failure = self.save(clone, "cross-clone", original_read, error=True)
        self.assertEqual(failure["write_outcome"], "not_written")
        self.assertTrue(self.save(clone, "副本独立正文", clone_read)["verified"])
        self.assertEqual(self.read(original)["documents"][-1]["content"].splitlines()[-1], "共同正文")

    def test_root_replacement_invalidates_read_without_touching_either_copy(self):
        path = self.external_a / "replace-me"
        self.initialize(path)
        receipt = self.read(path)
        moved = self.external_a / "replace-original"
        path.rename(moved)
        path.mkdir()
        shutil.copytree(moved, path, dirs_exist_ok=True)
        before_original = self.snapshot(moved)
        before_replacement = self.snapshot(path)
        failure = self.save(path, "blocked", receipt, error=True)
        self.assertIn("目录身份", failure["error"])
        self.assertEqual(failure["write_outcome"], "not_written")
        self.assertEqual(self.snapshot(moved), before_original)
        self.assertEqual(self.snapshot(path), before_replacement)

    def test_external_edit_and_runtime_change_preserve_content_and_invalidate_receipt(self):
        path = self.external_a / "external-edit"
        self.initialize(path)
        receipt = self.read(path)
        target = path / "docs/requirements.md"
        target.parent.mkdir()
        target.write_text("external content", encoding="utf-8")
        conflict = self.save(path, "overwrite", receipt, error=True)
        self.assertEqual(conflict["write_outcome"], "not_written")
        self.assertEqual(target.read_text(encoding="utf-8"), "external content")
        receipt = self.read(path)
        self.config["unrelated_runtime_change"] = True
        self.write_config()
        before = self.snapshot(path)
        failure = self.save(path, "runtime-change", receipt, error=True)
        self.assertEqual(failure["reason"], "runtime_baseline_changed")
        self.assertEqual(self.snapshot(path), before)

    def test_nonempty_directories_missing_parents_and_foreign_locks_are_not_adopted(self):
        cases = {
            "ordinary": ("notes.md",),
            "hidden": (".hidden",),
            "ds-store": (".DS_Store",),
            "code": ("src/main.py",),
            "foreign-lock": (".project-state.lock",),
            "git": (),
        }
        for name, members in cases.items():
            with self.subTest(name=name):
                path = self.external_a / name
                path.mkdir()
                for member in members:
                    target = path / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("keep", encoding="utf-8")
                if name == "git":
                    (path / ".git").mkdir()
                before = self.snapshot(path)
                failure = self.initialize(path, error=True)
                self.assertEqual(failure["write_outcome"], "not_written")
                self.assertEqual(self.snapshot(path), before)
        missing = self.external_a / "missing-parent" / "child"
        failure = self.initialize(missing, error=True)
        self.assertEqual(failure["write_outcome"], "not_written")
        self.assertFalse((self.external_a / "missing-parent").exists())

    def test_prepare_creation_requires_trusted_binding_and_detects_drift(self):
        path = self.external_a / "prepared"
        bound = self.binding(path, "prepared-id")
        operation = {"operation_id": "0" * 64, "request_digest": "1" * 64}
        prepared = mcp.project_init.prepare_creation(
            self.foundation, "prepared-id", "准备计划", "隔离测试",
            created_at="2026-11-04T00:00:00+00:00", binding=operation,
            project_binding=bound)
        mcp.project_init.verify_prepared_creation(self.foundation, prepared, project_binding=bound)
        with self.assertRaisesRegex(ValueError, "受信 binding"):
            mcp.project_init.verify_prepared_creation(self.foundation, prepared)
        tampered = dict(prepared)
        tampered["extra"] = True
        with self.assertRaisesRegex(ValueError, "准备计划格式"):
            mcp.project_init.verify_prepared_creation(self.foundation, tampered, project_binding=bound)
        applied = mcp.project_init.apply_prepared_creation(self.foundation, prepared, project_binding=bound)
        self.assertEqual(applied["status"], "local_files_ready")
        other = self.external_a / "prepared-drift"
        other_binding = self.binding(other, "prepared-drift")
        drifted = mcp.project_init.prepare_creation(
            self.foundation, "prepared-drift", "准备计划", "隔离测试",
            created_at="2026-11-04T00:00:00+00:00", binding=operation,
            project_binding=other_binding)
        initializer = self.foundation / "file_tools/project_init.py"
        original_initializer = initializer.read_bytes()
        try:
            initializer.write_bytes(original_initializer + b"\n# controlled drift\n")
            with self.assertRaises(ValueError):
                mcp.project_init.verify_prepared_creation(
                    self.foundation, drifted, project_binding=other_binding)
            self.assertFalse(other.exists())
        finally:
            initializer.write_bytes(original_initializer)
        self.config["project_path_mode"] = "legacy_rooted"
        self.config["projects_root"] = str(self.projects)
        self.config["project_directories"] = {}
        self.write_config()
        with self.assertRaisesRegex(ValueError, "运行基线"):
            mcp.project_init.verify_prepared_creation(
                self.foundation, drifted, project_binding=other_binding)
        self.assertFalse(other.exists())

    def test_legacy_prepared_creation_and_low_level_binding_contract_remain_compatible(self):
        self.config.pop("project_path_mode")
        self.config["projects_root"] = str(self.projects)
        self.config["project_directories"] = {}
        self.write_config()
        operation = {"operation_id": "2" * 64, "request_digest": "3" * 64}
        prepared = mcp.project_init.prepare_creation(
            self.foundation, "legacy-new", "旧模式", "兼容测试",
            created_at="2026-11-04T00:00:00+00:00", binding=operation)
        result = mcp.project_init.apply_prepared_creation(self.foundation, prepared)
        self.assertEqual(result["status"], "local_files_ready")
        legacy = mcp.project_binding.bind_project(self.foundation, str(self.projects / "legacy-new"))
        context = mcp.requirements.context(
            self.foundation, "legacy-new", expected_root=self.projects / "legacy-new",
            directory_name="legacy-new", binding=legacy)
        self.assertEqual(context["project_path"], str(self.projects / "legacy-new"))
        with self.assertRaisesRegex(ValueError, "目录名称"):
            mcp.requirements.context(
                self.foundation, "legacy-new", directory_name="wrong", binding=legacy)
        self.config["project_path_mode"] = "legacy_rooted"
        self.write_config()
        command = [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "file_tools/requirements.py"),
                   "--foundation", str(self.foundation), "context", "legacy-new"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_cli_requires_project_path_and_low_level_expected_root_is_not_locator(self):
        path = self.external_a / "cli-project"
        base = [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "file_tools/project_init.py"),
                "--foundation", str(self.foundation), "new", "cli-id",
                "--name", "CLI", "--purpose", "显式 CLI 测试", "--apply"]
        missing = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("受信 binding", missing.stderr)
        self.assertFalse(path.exists())
        applied = subprocess.run([*base, "--project-path", str(path)], capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        context_command = [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "file_tools/requirements.py"),
                           "--foundation", str(self.foundation), "context", "cli-id",
                           "--project-path", str(path)]
        context = subprocess.run(context_command, capture_output=True, text=True)
        self.assertEqual(context.returncode, 0, context.stderr)
        self.assertEqual(json.loads(context.stdout)["project_path"], str(path))
        save_command = [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "file_tools/requirements.py"),
                        "--foundation", str(self.foundation), "save-draft", "cli-id",
                        "--expected-sha", "missing", "--apply", "--project-path", str(path)]
        saved = subprocess.run(save_command, input="CLI 正文", capture_output=True, text=True)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        with self.assertRaisesRegex(ValueError, "受信 binding"):
            mcp.requirements.context(self.foundation, "cli-id", expected_root=path)
        bound = self.binding(path)
        with self.assertRaisesRegex(ValueError, "固定的目录"):
            mcp.requirements.context(
                self.foundation, "cli-id", expected_root=self.external_a / "other", binding=bound)
        help_result = subprocess.run(
            [sys.executable, "-B", str(fixtures.TOOLS_ROOT / "file_tools/requirements.py"),
             "context", "--help"], capture_output=True, text=True)
        self.assertIn("--project-path", help_result.stdout)

    def test_documents_work_inside_parent_git_repo_but_nested_git_init_still_fails(self):
        repository = self.external_a / "parent-repo"
        repository.mkdir()
        initialized = subprocess.run(["git", "init", "--template=", "-q", str(repository)],
                                     capture_output=True, text=True)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        path = repository / "project"
        self.initialize(path)
        saved = self.save(path, "仓库内文档", self.read(path))
        self.assertTrue(saved["verified"])
        before = (path / "project.json").read_bytes()
        bound = self.binding(path)
        with self.assertRaisesRegex(ValueError, "实际 Git 根不匹配"):
            mcp.project_init.init_git(self.foundation, path.name, binding=bound)
        self.assertEqual((path / "project.json").read_bytes(), before)
        self.assertFalse((path / ".git").exists())

    def test_legacy_documents_inside_parent_git_repo_remain_available(self):
        self.config["projects_root"] = str(self.projects)
        initialized = subprocess.run(["git", "init", "--template=", "-q", str(self.projects)],
                                     capture_output=True, text=True)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        for mode in ("L0", "L1"):
            with self.subTest(mode=mode):
                identifier = "voice-meetup" if mode == "L0" else "legacy-second"
                path = self.project if mode == "L0" else self.projects / "legacy-second"
                if mode == "L1":
                    path.mkdir()
                    self.config["project_path_mode"] = "legacy_rooted"
                else:
                    self.config.pop("project_path_mode")
                self.config["project_directories"] = {identifier: path.name}
                self.write_config()
                result = mcp.project_init.initialize_existing(
                    self.foundation, identifier, "旧项目", "Git 解耦")
                self.assertFalse(result["git_initialized"])
                saved = mcp.requirements.save_draft(self.foundation, identifier, "旧模式仓库内文档", "missing")
                self.assertTrue(saved["changed"])

    def test_real_permission_denials_do_not_redirect_or_report_success(self):
        if hasattr(os, "geteuid"):
            self.assertNotEqual(os.geteuid(), 0, "高权限环境不能形成真实权限拒绝，应记为 BLOCKED")
        parent = self.external_a / "denied-parent"
        parent.mkdir()
        target = parent / "new-project"
        parent.chmod(0o500)
        try:
            failure = self.initialize(target, error=True)
            self.assertEqual(failure["write_outcome"], "unknown")
            self.assertFalse(target.exists())
        finally:
            parent.chmod(0o700)
        path = self.external_a / "denied-project"
        self.initialize(path)
        receipt = self.read(path)
        path.chmod(0o500)
        try:
            failure = self.save(path, "denied", receipt, error=True)
            self.assertEqual(failure["write_outcome"], "unknown")
            self.assertFalse((path / "docs").exists())
        finally:
            path.chmod(0o700)
        metadata = path / "project.json"
        before = self.snapshot(path)
        metadata.chmod(0)
        try:
            failure = self.read(path, error=True)
            self.assertIn("不可读", failure["error"])
        finally:
            metadata.chmod(0o600)
        self.assertEqual(self.snapshot(path), before)
        saved = self.save(path, "initial", self.read(path))
        document = path / "docs/requirements.md"
        document.chmod(0)
        try:
            failure = self.read(path, error=True)
            self.assertTrue(failure)
        finally:
            document.chmod(0o600)
        self.assertEqual(document.read_bytes(), saved["document"]["content"].encode("utf-8"))

    def test_normal_directory_timestamp_change_does_not_invalidate_binding(self):
        path = self.external_a / "timestamp-change"
        self.initialize(path)
        receipt = self.read(path)
        original_identity = self.server.tools.projects[path].binding.root_identity
        (path / "unrelated.txt").write_text("ordinary activity", encoding="utf-8")
        saved = self.save(path, "时间戳变化仍可保存", receipt)
        self.assertTrue(saved["verified"])
        self.assertEqual(self.server.tools.projects[path].binding.root_identity, original_identity)

    def test_concurrent_creation_has_one_creator_and_never_overwrites_competitor(self):
        path = self.external_a / "concurrent"
        barrier = threading.Barrier(2)
        original = mcp.project_init.write_creation_files

        def raced(target, files):
            barrier.wait(timeout=5)
            return original(target, files)

        def create():
            tools = mcp.SharedProjectTools(
                foundation=self.foundation, allow_initialize=True, allow_save=True)
            server = mcp.McpServer(tools)
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "_meta": self.meta(), "name": mcp.PROJECT_INITIALIZE,
                "arguments": {"project_path": str(path), "name": "竞争", "purpose": "隔离测试",
                              "project_id": "race-id"}}}
            response = server.handle(request)
            return json.loads(response["result"]["content"][0]["text"]), response["result"]["isError"]

        with mock.patch.object(mcp.project_init, "write_creation_files", side_effect=raced):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: create(), range(2)))
        self.assertEqual(sum(not is_error for _, is_error in results), 1, results)
        self.assertEqual(sum(is_error for _, is_error in results), 1, results)
        failure = next(result for result, is_error in results if is_error)
        self.assertEqual(failure["write_outcome"], "unknown")
        metadata = json.loads((path / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project_id"], "race-id")

    def test_root_change_between_adapter_and_kernel_is_rejected_before_write(self):
        path = self.external_a / "kernel-race"
        self.initialize(path)
        receipt = self.read(path)
        moved = self.external_a / "kernel-race-original"
        original_save = mcp.requirements.save_draft

        def replace_then_save(*args, **kwargs):
            path.rename(moved)
            path.mkdir()
            shutil.copytree(moved, path, dirs_exist_ok=True)
            return original_save(*args, **kwargs)

        with mock.patch.object(mcp.requirements, "save_draft", side_effect=replace_then_save):
            failure = self.save(path, "blocked", receipt, error=True)
        self.assertIn("目录身份", failure["error"])
        self.assertFalse((path / "docs").exists())
        self.assertFalse((moved / "docs").exists())


if __name__ == "__main__":
    unittest.main()
