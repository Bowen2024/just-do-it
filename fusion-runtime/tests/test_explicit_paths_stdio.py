import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest

from explicit_path_test_support import ExplicitStdioFixture
from test_requirements_prd_tools import PRD_BODY
from test_ui_accept import APP, candidate_files, request_id
from test_ui_recovery import RecoveryFixture
from ui_test_support import tree_snapshot


class ExplicitPathStdioTests(ExplicitStdioFixture):
    interrupt_accept = RecoveryFixture.interrupt_accept
    transaction_id = RecoveryFixture.transaction_id

    def test_clean_explicit_start_discovers_exact_capabilities_and_persistent_ids(self):
        expected = {
            "requirements": [
                "requirements_project_inspect", "requirements_read_context",
                "requirements_inspect_prd",
            ],
            "solution": ["solution_read_context", "solution_inspect"],
            "ui": ["ui_read_context", "ui_inspect", "ui_read_history"],
        }
        for role, names in expected.items():
            with self.subTest(role=role, enabled=False):
                child = self.spawn_role(role)
                self.assertEqual(set(child.tools()), set(names))
                self.assertEqual(len(child.tools()), len(names))
                child.close()
        child = self.spawn_role("requirements", initialize=True)
        self.assertEqual(set(child.tools()), {
            "requirements_project_inspect", "requirements_project_initialize",
            "requirements_read_context", "requirements_inspect_prd",
        })
        child.close()
        child = self.spawn_role("requirements", save=True)
        self.assertEqual(set(child.tools()), {
            "requirements_project_inspect", "requirements_read_context",
            "requirements_save_draft", "requirements_inspect_prd",
            "requirements_save_prd_draft", "requirements_project_update_info",
        })
        child.close()
        child = self.spawn_role("requirements", initialize=True, save=True)
        self.assertEqual(len(child.tools()), 7)
        child.close()
        child = self.spawn_role("solution", save=True)
        self.assertEqual(child.tools(), [
            "solution_read_context", "solution_inspect", "solution_save_tech_spec_draft",
        ])
        child.close()
        child = self.spawn_role("ui", write=True)
        self.assertEqual(child.tools(), [
            "ui_read_context", "ui_inspect", "ui_read_history", "ui_prepare_revision",
            "ui_accept_revision", "ui_recover_revision",
        ])
        child.close()
        for role in expected:
            child = self.spawn_role(role)
            tool = {
                "requirements": "requirements_read_context",
                "solution": "solution_read_context",
                "ui": "ui_read_context",
            }[role]
            for project, identifier in ((self.project_p1, "persisted-a"),
                                        (self.project_p2, "persisted-b")):
                payload = child.ok(tool, {"project_path": str(project)})
                project_payload = payload.get("project", payload)
                self.assertEqual(project_payload["project_id"], identifier)
                self.assertEqual(project_payload["project_path"], str(project))
            child.close()

    def test_requirements_prd_history_recovery_and_info_flow(self):
        child = self.spawn_role("requirements", initialize=True, save=True)
        target = self.root / "external-c/多级目录/客户 A/采购 需求预测"
        target.parent.mkdir(parents=True)
        inspected = child.ok("requirements_project_inspect", {"project_path": str(target)})
        self.assertEqual(inspected["status"], "not_created")
        self.assertFalse(target.exists())
        created = child.ok("requirements_project_initialize", {
            "project_path": str(target), "name": target.name,
            "purpose": "真实 stdio 隔离测试", "project_id": "stdio-flow",
        })
        self.assertEqual(created["project_id"], "stdio-flow")
        self.assertFalse((target / target.name).exists())
        first_read = self.requirements_read(child, target)
        first = self.requirements_save(child, target, "# 需求\n\n- REQ-001：第一版\n", first_read)
        first_prd = child.ok("requirements_save_prd_draft", {
            "project_path": str(target), "content": PRD_BODY,
            "read_id": self.requirements_read(child, target)["read_id"],
        })
        self.assertTrue(first_prd["verified"])
        second_read = self.requirements_read(child, target)
        second = self.requirements_save(child, target, "# 需求\n\n- REQ-001：第二版\n", second_read)
        is_error, stale_prd = child.call("requirements_save_prd_draft", {
            "project_path": str(target), "content": PRD_BODY,
            "read_id": second_read["read_id"],
        })
        self.assertTrue(is_error, stale_prd)
        self.assertEqual(stale_prd["write_outcome"], "not_written")
        current_read = self.requirements_read(child, target, include_recovery=True)
        second_prd = child.ok("requirements_save_prd_draft", {
            "project_path": str(target), "content": PRD_BODY + "\n第二版补充。\n",
            "read_id": current_read["read_id"],
        })
        self.assertTrue(second_prd["verified"])
        req_history = self.requirements_read(child, target, history_sha256=first["sha256"])
        self.assertIn("第一版", req_history["history"]["content"])
        prd_history = self.requirements_read(
            child, target, prd_history_sha256=first_prd["sha256"]
        )
        self.assertEqual(prd_history["prd_history"]["sha256"], first_prd["sha256"])
        before_metadata = json.loads((target / "project.json").read_text())
        update_read = self.requirements_read(child, target, include_recovery=True)
        updated = child.ok("requirements_project_update_info", {
            "project_path": str(target), "read_id": update_read["read_id"],
            "changes": {"project_type": "web"},
        })
        self.assertEqual(updated["write_outcome"], "saved")
        is_error, stale_save = child.call("requirements_save_draft", {
            "project_path": str(target), "content": "不得写入",
            "read_id": update_read["read_id"],
        })
        self.assertTrue(is_error, stale_save)
        self.assertEqual(stale_save["write_outcome"], "not_written")
        after_metadata = json.loads((target / "project.json").read_text())
        self.assertEqual(after_metadata["project_id"], before_metadata["project_id"])
        self.assertEqual(after_metadata["dependencies"], before_metadata["dependencies"])
        final_read = self.requirements_read(child, target, include_recovery=True)
        self.assertEqual(final_read["recovery"]["project"]["status"], "present")
        final_save = self.requirements_save(
            child, target, "# 需求\n\n- REQ-001：补录后第三版\n", final_read
        )
        self.assertTrue(final_save["verified"])
        repeated = child.ok("requirements_project_initialize", {
            "project_path": str(target), "name": target.name,
            "purpose": "真实 stdio 隔离测试", "project_id": "stdio-flow",
        })
        self.assertFalse(repeated["changed"])
        child.close()

    def test_solution_full_positive_history_and_invalidation_flow(self):
        self.write_requirements_and_prd(self.project_p1)
        self.confirm_prd(self.project_p1)
        child = self.spawn_role("solution", save=True)
        read = self.solution_read(child, self.project_p1)
        self.assertEqual(read["confirmation"]["status"], "valid")
        candidate = child.ok("solution_inspect", {
            "project_path": str(self.project_p1), "target": "candidate",
            "content": self.tech_spec("第一版"), "profile": "Lite",
        })
        self.assertEqual(candidate["structure"]["status"], "pass")
        first = self.solution_save(child, self.project_p1, self.tech_spec("第一版"), read)
        self.assertEqual(first["write_outcome"], "saved")
        unchanged = self.solution_save(
            child, self.project_p1, self.tech_spec("第一版"),
            self.solution_read(child, self.project_p1),
        )
        self.assertEqual(unchanged["write_outcome"], "unchanged")
        second = self.solution_save(
            child, self.project_p1, self.tech_spec("第二版"),
            self.solution_read(child, self.project_p1), profile="Standard",
        )
        self.assertEqual(second["write_outcome"], "saved")
        history = self.solution_read(
            child, self.project_p1, history_sha256=first["target"]["sha256"]
        )
        self.assertIn("第一版", history["history"]["content"])
        stale = self.solution_read(child, self.project_p1)
        self.write_requirements_and_prd(
            self.project_p1, requirements_text="# 新需求\n\n- REQ-001：已变化\n"
        )
        is_error, rejected = child.call("solution_save_tech_spec_draft", {
            "project_path": str(self.project_p1),
            "read_id": stale["read_receipt"]["read_id"],
            "content": self.tech_spec("不得覆盖"), "profile": "Lite",
        })
        self.assertTrue(is_error, rejected)
        self.assertEqual(rejected["write_outcome"], "not_written")
        self.assertEqual(
            hashlib.sha256((self.project_p1 / "docs/tech-spec.md").read_bytes()).hexdigest(),
            second["target"]["sha256"],
        )
        child.close()

    def test_ui_empty_current_import_and_history_sources(self):
        self.write_inputs(self.project_p1)
        self.write_import_case()
        child = self.spawn_role("ui", write=True, import_roots=[self.import_parent])
        empty = self.ui_flow(child, self.project_p1)
        current_files = candidate_files()
        current_files[APP] = "const source='current';\n"
        current = self.ui_flow(child, self.project_p1, mode="current", files=current_files)
        source_before = tree_snapshot(self.import_parent)
        imported = self.ui_flow(
            child, self.project_p1, mode="import", import_source=self.import_source()
        )
        self.assertEqual(tree_snapshot(self.import_parent), source_before)
        history_files = candidate_files()
        history_files[APP] = "const source='history';\n"
        restored = self.ui_flow(
            child, self.project_p1, mode="history", files=history_files,
            history_revision=empty["accepted"]["current_revision"],
        )
        self.assertEqual(len(restored["history"]["versions"]), 4)
        self.assertEqual(
            restored["history"]["versions"][0]["revision_sha256"],
            restored["accepted"]["current_revision"],
        )
        self.assertEqual((self.project_p1 / APP).read_text(), history_files[APP])
        self.assertTrue(current["accepted"]["current_revision"])
        self.assertTrue(imported["accepted"]["current_revision"])
        child.close()

    def test_ui_interrupted_transaction_recovers_in_new_process(self):
        self.write_inputs(self.project_p1)
        self.connect(allow_write=True)
        rejected, _prepared = self.interrupt_accept("member_after:0")
        self.assertEqual(rejected["write_outcome"], "unknown")
        transaction_id = self.transaction_id(rejected)
        child = self.spawn_role("ui", write=True)
        inspected = child.ok("ui_inspect", {
            "project_path": str(self.project_p1), "target": "transaction",
            "transaction_id": transaction_id,
        })
        self.assertEqual(inspected["transaction"]["status"], "interrupted")
        resumed = child.ok("ui_recover_revision", {
            "project_path": str(self.project_p1), "transaction_id": transaction_id,
            "request_id": request_id(), "action": "resume",
        })
        self.assertEqual(resumed["transaction_status"], "resumed")
        replay = child.ok("ui_recover_revision", {
            "project_path": str(self.project_p1), "transaction_id": transaction_id,
            "request_id": request_id(), "action": "resume",
        })
        self.assertEqual(replay["transaction_status"], "already_closed")
        self.assertEqual(len(child.ok("ui_read_history", {
            "project_path": str(self.project_p1),
        })["versions"]), 1)
        child.close()

    def test_three_roles_alternate_projects_and_reject_cross_credentials(self):
        requirements = self.spawn_role("requirements", save=True)
        solution = self.spawn_role("solution", save=True)
        ui = self.spawn_role("ui", write=True)
        config_before = (self.foundation / "config/local.json").read_bytes()
        reads = {}
        for project, marker in ((self.project_p1, "A"), (self.project_p2, "B")):
            read = self.requirements_read(requirements, project)
            reads[project] = read
            saved = self.requirements_save(
                requirements, project, f"# 需求 {marker}\n\n- REQ-001：{marker}\n", read
            )
            self.assertTrue(saved["verified"])
            child_prd = PRD_BODY.replace("首版 PRD", f"{marker} 版 PRD")
            requirements.ok("requirements_save_prd_draft", {
                "project_path": str(project), "content": child_prd,
                "read_id": self.requirements_read(requirements, project)["read_id"],
            })
            self.confirm_prd(project)
        is_error, cross = requirements.call("requirements_save_draft", {
            "project_path": str(self.project_p2), "content": "cross",
            "read_id": reads[self.project_p1]["read_id"],
        })
        self.assertTrue(is_error, cross)
        self.assertEqual(cross["write_outcome"], "not_written")
        solution_reads = {}
        for project in (self.project_p1, self.project_p2):
            read = self.solution_read(solution, project)
            solution_reads[project] = read
        is_error, cross = solution.call("solution_save_tech_spec_draft", {
            "project_path": str(self.project_p1),
            "read_id": solution_reads[self.project_p2]["read_receipt"]["read_id"],
            "content": self.tech_spec("cross"), "profile": "Lite",
        })
        self.assertTrue(is_error, cross)
        for project, marker in ((self.project_p1, "A"), (self.project_p2, "B")):
            saved = self.solution_save(
                solution, project, self.tech_spec(f"方案 {marker}"),
                self.solution_read(solution, project),
            )
            self.assertEqual(saved["write_outcome"], "saved")
            self.write_inputs(project)
        flow_b = self.ui_flow(ui, self.project_p2)
        flow_a = self.ui_flow(ui, self.project_p1)
        is_error, cross = ui.call("ui_accept_revision", {
            "project_path": str(self.project_p1),
            "revision_id": flow_b["prepared"]["revision_id"],
            "inspection_id": flow_b["inspected"]["inspection_id"],
            "request_id": request_id(), "delete_paths": [],
        })
        self.assertTrue(is_error, cross)
        self.assertEqual(flow_a["history"]["versions"][0]["revision_sha256"],
                         flow_a["accepted"]["current_revision"])
        self.assertEqual(flow_b["history"]["versions"][0]["revision_sha256"],
                         flow_b["accepted"]["current_revision"])
        self.assertEqual((self.foundation / "config/local.json").read_bytes(), config_before)
        for child in (requirements, solution, ui):
            child.close()

    def test_restart_and_runtime_change_invalidate_memory_credentials(self):
        self.write_requirements_and_prd(self.project_p1)
        self.confirm_prd(self.project_p1)
        self.write_inputs(self.project_p1)
        requirements = self.spawn_role("requirements", save=True)
        solution = self.spawn_role("solution", save=True)
        ui = self.spawn_role("ui", write=True)
        req_read = self.requirements_read(requirements, self.project_p1)
        sol_read = self.solution_read(solution, self.project_p1)
        ui_read = ui.ok("ui_read_context", {"project_path": str(self.project_p1)})
        for child in (requirements, solution, ui):
            child.close()
        requirements = self.spawn_role("requirements", save=True)
        solution = self.spawn_role("solution", save=True)
        ui = self.spawn_role("ui", write=True)
        cases = [
            (requirements, "requirements_save_draft", {
                "project_path": str(self.project_p1), "content": "stale",
                "read_id": req_read["read_id"],
            }),
            (solution, "solution_save_tech_spec_draft", {
                "project_path": str(self.project_p1),
                "read_id": sol_read["read_receipt"]["read_id"],
                "content": self.tech_spec("stale"), "profile": "Lite",
            }),
            (ui, "ui_prepare_revision", {
                "project_path": str(self.project_p1), "read_id": ui_read["read_id"],
                "request_id": request_id(), "mode": "empty",
            }),
        ]
        for child, name, arguments in cases:
            is_error, payload = child.call(name, arguments)
            self.assertTrue(is_error, payload)
            self.assertEqual(payload["write_outcome"], "not_written")
        req_read = self.requirements_read(requirements, self.project_p1)
        sol_read = self.solution_read(solution, self.project_p1)
        ui_read = ui.ok("ui_read_context", {"project_path": str(self.project_p1)})
        self.config["runtime_probe"] = "changed"
        self.write_config()
        drift_cases = [
            (requirements, "requirements_save_draft", {
                "project_path": str(self.project_p1), "content": "drift",
                "read_id": req_read["read_id"],
            }),
            (solution, "solution_save_tech_spec_draft", {
                "project_path": str(self.project_p1),
                "read_id": sol_read["read_receipt"]["read_id"],
                "content": self.tech_spec("drift"), "profile": "Lite",
            }),
            (ui, "ui_prepare_revision", {
                "project_path": str(self.project_p1), "read_id": ui_read["read_id"],
                "request_id": request_id(), "mode": "empty",
            }),
        ]
        for child, name, arguments in drift_cases:
            is_error, payload = child.call(name, arguments)
            self.assertTrue(is_error, payload)
            self.assertEqual(payload["write_outcome"], "not_written")
        for child in (requirements, solution, ui):
            child.close()

    def test_legacy_modes_keep_root_contract_for_all_roles(self):
        for mode in ("absent", "legacy_rooted"):
            with self.subTest(mode=mode):
                if mode == "absent":
                    self.config.pop("project_path_mode")
                else:
                    self.config["project_path_mode"] = mode
                self.config["projects_root"] = str(self.projects)
                self.config["project_directories"] = {
                    "procurement-demo": "采购演示", "meeting-b": "会议助手",
                }
                self.write_config()
                legacy = self.projects / "采购演示"
                self.write_requirements_and_prd(legacy)
                self.confirm_prd(legacy)
                requirements = self.spawn_role("requirements", save=True)
                solution = self.spawn_role("solution", save=True)
                ui = self.spawn_role("ui", write=True)
                read = self.requirements_read(requirements, legacy)
                self.assertEqual(read["project_id"], "procurement-demo")
                sol_read = self.solution_read(solution, legacy)
                self.assertEqual(sol_read["project"]["project_id"], "procurement-demo")
                self.assertIn(
                    self.solution_save(solution, legacy, self.tech_spec("旧模式"), sol_read)[
                        "write_outcome"
                    ],
                    {"saved", "unchanged"},
                )
                self.requirements_save(requirements, legacy, "# 旧模式\n", read)
                flow = self.ui_flow(
                    ui, legacy, mode="empty" if mode == "absent" else "current"
                )
                self.assertIn(flow["accepted"]["write_outcome"], {"saved", "unchanged"})
                for child, tool in (
                    (requirements, "requirements_read_context"),
                    (solution, "solution_read_context"),
                    (ui, "ui_read_context"),
                ):
                    is_error, payload = child.call(tool, {
                        "project_path": str(self.project_p1),
                    })
                    self.assertTrue(is_error, payload)
                    if isinstance(payload["error"], dict):
                        self.assertEqual(payload["error"]["code"], "path_not_allowed")
                    else:
                        self.assertIn("直接子目录", payload["error"])
                for child in (requirements, solution, ui):
                    child.close()

    def test_legacy_fixed_requirements_entry_and_unknown_authorization(self):
        self.config.pop("project_path_mode")
        self.config["projects_root"] = str(self.projects)
        self.config["project_directories"] = {
            "procurement-demo": "采购演示", "meeting-b": "会议助手",
        }
        self.write_config()
        legacy = self.projects / "采购演示"
        from explicit_path_test_support import McpChild
        child = McpChild(self, [
            sys.executable, "-B", str(self.foundation / "cursor_mcp.py"),
            "--foundation", str(self.foundation), "--project-id", "procurement-demo",
            "--project-root", str(legacy), "--allow-save",
        ])
        self.assertEqual(len(child.tools()), 6)
        read = child.ok("requirements_read_context", {})
        saved = child.ok("requirements_save_draft", {
            "content": "# 固定入口\n", "read_id": read["read_id"],
        })
        self.assertTrue(saved["verified"])
        before = tree_snapshot(legacy)
        is_error, payload = child.call("requirements_save_draft", {
            "content": "不得写入", "read_id": read["read_id"], "authorized": True,
        })
        self.assertTrue(is_error, payload)
        self.assertEqual(payload["error"], "工具参数包含未知字段；操作范围和权限只能由启动配置提供")
        self.assertEqual(tree_snapshot(legacy), before)
        child.close()

    def test_legacy_permission_denials_do_not_redirect_or_report_success(self):
        if hasattr(os, "geteuid"):
            self.assertNotEqual(os.geteuid(), 0, "真实权限矩阵不能以高权限身份通过")
        for mode in ("L0", "L1"):
            with self.subTest(mode=mode):
                denied_root = self.root / f"denied-root-{mode}"
                denied_root.mkdir()
                self.use_path_mode(mode, mapping={})
                self.config["projects_root"] = str(denied_root)
                self.write_config()
                child = self.spawn_role("requirements", initialize=True, save=True)
                target = denied_root / "new-project"
                denied_root.chmod(0o500)
                try:
                    is_error, rejected = child.call("requirements_project_initialize", {
                        "project_path": str(target), "name": "拒绝写入", "purpose": "权限矩阵",
                        "project_id": "denied-parent",
                    })
                    self.assertTrue(is_error, rejected)
                    self.assertEqual(rejected["write_outcome"], "unknown")
                    self.assertFalse(target.exists())
                    self.assertFalse((self.outside / target.name).exists())
                finally:
                    denied_root.chmod(0o700)
                    child.close()

                self.use_path_mode(mode, mapping={})
                project = self.projects / f"permission-{mode.lower()}"
                self.init_explicit_project(project, project.name)
                child = self.spawn_role("requirements", save=True)
                receipt = self.requirements_read(child, project)
                project.chmod(0o500)
                try:
                    is_error, rejected = child.call("requirements_save_draft", {
                        "project_path": str(project), "content": "不得写入",
                        "read_id": receipt["read_id"],
                    })
                    self.assertTrue(is_error, rejected)
                    self.assertEqual(rejected["write_outcome"], "unknown")
                    self.assertFalse((project / "docs").exists())
                finally:
                    project.chmod(0o700)

                metadata = project / "project.json"
                before = tree_snapshot(project)
                metadata.chmod(0)
                try:
                    is_error, rejected = child.call("requirements_read_context", {
                        "project_path": str(project),
                    })
                    self.assertTrue(is_error, rejected)
                finally:
                    metadata.chmod(0o600)
                self.assertEqual(tree_snapshot(project), before)

                saved = self.requirements_save(
                    child, project, "# 权限恢复后的正向对照\n",
                    self.requirements_read(child, project),
                )
                self.assertTrue(saved["verified"])
                document = project / "docs/requirements.md"
                document.chmod(0)
                try:
                    is_error, rejected = child.call("requirements_read_context", {
                        "project_path": str(project),
                    })
                    self.assertTrue(is_error, rejected)
                finally:
                    document.chmod(0o600)
                self.assertEqual(
                    document.read_text(encoding="utf-8"), saved["document"]["content"],
                )
                child.close()

    def test_legacy_same_id_content_copies_isolate_credentials_and_allow_new_reads(self):
        source = self.projects / "采购演示"
        self.write_inputs(source)
        self.write_requirements_and_prd(source)
        self.confirm_prd(source)
        for mode in ("L0", "L1"):
            with self.subTest(mode=mode):
                self.use_path_mode(mode, mapping={})
                first = self.projects / f"clone-a-{mode.lower()}"
                second = self.projects / f"clone-b-{mode.lower()}"
                shutil.copytree(source, first)
                shutil.copytree(source, second)
                requirements = self.spawn_role("requirements", save=True)
                solution = self.spawn_role("solution", save=True)
                ui = self.spawn_role("ui", write=True)
                req_a = self.requirements_read(requirements, first)
                req_b = self.requirements_read(requirements, second)
                self.assertEqual(req_a["project_id"], req_b["project_id"])
                self.assertNotEqual(req_a["read_id"], req_b["read_id"])
                before_a = tree_snapshot(first)
                before_b = tree_snapshot(second)
                is_error, rejected = requirements.call("requirements_save_draft", {
                    "project_path": str(second), "content": "跨副本拒绝",
                    "read_id": req_a["read_id"],
                })
                self.assertTrue(is_error, rejected)
                self.assertEqual(rejected["write_outcome"], "not_written")
                self.assertEqual(tree_snapshot(first), before_a)
                self.assertEqual(tree_snapshot(second), before_b)

                sol_a = self.solution_read(solution, first)
                sol_b = self.solution_read(solution, second)
                is_error, rejected = solution.call("solution_save_tech_spec_draft", {
                    "project_path": str(second),
                    "read_id": sol_a["read_receipt"]["read_id"],
                    "content": self.tech_spec("跨副本拒绝"), "profile": "Lite",
                })
                self.assertTrue(is_error, rejected)
                self.assertEqual(rejected["write_outcome"], "not_written")
                self.assertEqual(self.solution_save(
                    solution, first, self.tech_spec(f"A {mode}"), sol_a,
                )["write_outcome"], "saved")
                self.assertEqual(self.solution_save(
                    solution, second, self.tech_spec(f"B {mode}"), sol_b,
                )["write_outcome"], "saved")
                self.assertTrue(self.requirements_save(
                    requirements, first, f"# A {mode}\n", req_a,
                )["verified"])
                self.assertTrue(self.requirements_save(
                    requirements, second, f"# B {mode}\n", req_b,
                )["verified"])

                read = ui.ok("ui_read_context", {"project_path": str(first)})
                prepared = ui.ok("ui_prepare_revision", {
                    "project_path": str(first), "read_id": read["read_id"],
                    "request_id": request_id(), "mode": "empty",
                })
                from test_ui_accept import edit_candidate
                edit_candidate(prepared["workspace_path"], candidate_files())
                inspected = ui.ok("ui_inspect", {
                    "project_path": str(first), "target": "candidate",
                    "revision_id": prepared["revision_id"],
                })
                accept_arguments = {
                    "revision_id": prepared["revision_id"],
                    "inspection_id": inspected["inspection_id"],
                    "request_id": request_id(),
                    "delete_paths": inspected["changes"]["removed"],
                }
                is_error, rejected = ui.call("ui_accept_revision", {
                    "project_path": str(second), **accept_arguments,
                })
                self.assertTrue(is_error, rejected)
                accepted = ui.ok("ui_accept_revision", {
                    "project_path": str(first), **accept_arguments,
                })
                self.assertEqual(accepted["write_outcome"], "saved")
                independent = self.ui_flow(ui, second)
                self.assertEqual(independent["accepted"]["write_outcome"], "saved")
                self.assertNotEqual(
                    accepted["current_revision"], independent["accepted"]["current_revision"],
                )
                for child in (requirements, solution, ui):
                    child.close()

    def test_real_multiprocess_creation_races_cover_same_and_different_ids(self):
        for mode in ("E", "L0", "L1"):
            self.use_path_mode(mode, mapping={})
            for race, identifiers in (
                ("same-id", ("race-same", "race-same")),
                ("different-id", ("race-first", "race-second")),
            ):
                with self.subTest(mode=mode, race=race):
                    if mode == "E":
                        target = self.root / f"external-race/{mode}/{race}"
                    else:
                        target = self.projects / f"race-{mode.lower()}-{race}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    children = [
                        self.spawn_role("requirements", initialize=True)
                        for _ in range(2)
                    ]
                    barrier = __import__("threading").Barrier(2)

                    def initialize(child, project_id):
                        barrier.wait(timeout=5)
                        return child.call("requirements_project_initialize", {
                            "project_path": str(target), "name": "竞争初始化",
                            "purpose": "真实多进程矩阵", "project_id": project_id,
                        })

                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                        futures = [
                            executor.submit(initialize, child, identifier)
                            for child, identifier in zip(children, identifiers)
                        ]
                        results = [future.result(timeout=15) for future in futures]
                    creators = [
                        payload for is_error, payload in results
                        if not is_error and payload.get("changed") is True
                    ]
                    self.assertEqual(len(creators), 1, results)
                    for is_error, payload in results:
                        if is_error:
                            self.assertIn(payload["write_outcome"], {"unknown", "not_written"})
                        else:
                            self.assertIn(payload.get("changed"), {True, False})
                    metadata = json.loads((target / "project.json").read_text(encoding="utf-8"))
                    self.assertIn(metadata["project_id"], identifiers)
                    if race == "same-id":
                        self.assertEqual(metadata["project_id"], "race-same")
                    self.assertFalse((target / target.name).exists())
                    for child in children:
                        child.close()

    def test_normal_timestamp_changes_allow_all_role_writes_in_every_mode(self):
        projects = {
            "E": self.root / "external-a/timestamp-e",
            "L0": self.projects / "timestamp-l0",
            "L1": self.projects / "timestamp-l1",
        }
        for mode, project in projects.items():
            self.use_path_mode("E")
            self.init_explicit_project(project, project.name)
            self.write_inputs(project)
            self.write_requirements_and_prd(project)
            self.confirm_prd(project)
        for mode, project in projects.items():
            with self.subTest(mode=mode):
                self.use_path_mode(mode, mapping={})
                before = project.stat()
                (project / "unrelated.txt").write_text(f"ordinary activity {mode}", encoding="utf-8")
                after = project.stat()
                self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))
                self.assertTrue(
                    after.st_mtime_ns != before.st_mtime_ns
                    or after.st_ctime_ns != before.st_ctime_ns
                )
                requirements = self.spawn_role("requirements", save=True)
                solution = self.spawn_role("solution", save=True)
                ui = self.spawn_role("ui", write=True)
                solution_saved = self.solution_save(
                    solution, project, self.tech_spec(f"时间戳 {mode}"),
                    self.solution_read(solution, project),
                )
                self.assertEqual(solution_saved["write_outcome"], "saved")
                saved = self.requirements_save(
                    requirements, project, f"# 时间戳 {mode}\n",
                    self.requirements_read(requirements, project),
                )
                self.assertTrue(saved["verified"])
                flow = self.ui_flow(ui, project)
                self.assertEqual(flow["accepted"]["write_outcome"], "saved")
                self.assertEqual((project.stat().st_dev, project.stat().st_ino),
                                 (before.st_dev, before.st_ino))

                stale = self.requirements_read(requirements, project)
                document = project / "docs/requirements.md"
                with document.open("a", encoding="utf-8") as stream:
                    stream.write("外部编辑仍必须冲突\n")
                is_error, rejected = requirements.call("requirements_save_draft", {
                    "project_path": str(project), "content": "不得覆盖外部编辑",
                    "read_id": stale["read_id"],
                })
                self.assertTrue(is_error, rejected)
                self.assertEqual(rejected["write_outcome"], "not_written")
                self.assertIn("外部编辑仍必须冲突", document.read_text(encoding="utf-8"))
                for child in (requirements, solution, ui):
                    child.close()

    def test_legacy_restarts_invalidate_credentials_and_preserve_persistent_state(self):
        for mode in ("L0", "L1"):
            with self.subTest(mode=mode):
                self.use_path_mode(mode, mapping={})
                project = self.projects / f"restart-{mode.lower()}"
                self.init_explicit_project(project, project.name)
                self.write_inputs(project)
                self.write_requirements_and_prd(project)
                self.confirm_prd(project)
                requirements = self.spawn_role("requirements", save=True)
                solution = self.spawn_role("solution", save=True)
                ui = self.spawn_role("ui", write=True)
                sol_saved = self.solution_save(
                    solution, project, self.tech_spec(f"重启历史 {mode}"),
                    self.solution_read(solution, project),
                )
                self.solution_save(
                    solution, project, self.tech_spec(f"重启后当前版本 {mode}"),
                    self.solution_read(solution, project),
                )
                req_saved = self.requirements_save(
                    requirements, project, f"# 重启历史 {mode}\n",
                    self.requirements_read(requirements, project),
                )
                self.requirements_save(
                    requirements, project, f"# 重启后当前版本 {mode}\n",
                    self.requirements_read(requirements, project),
                )
                flow = self.ui_flow(ui, project)
                req_stale = self.requirements_read(requirements, project)
                sol_stale = self.solution_read(solution, project)
                for child in (requirements, solution, ui):
                    child.close()

                requirements = self.spawn_role("requirements", save=True)
                solution = self.spawn_role("solution", save=True)
                ui = self.spawn_role("ui", write=True)
                stale_calls = (
                    (requirements, "requirements_save_draft", {
                        "project_path": str(project), "content": "重启前凭据",
                        "read_id": req_stale["read_id"],
                    }),
                    (solution, "solution_save_tech_spec_draft", {
                        "project_path": str(project),
                        "read_id": sol_stale["read_receipt"]["read_id"],
                        "content": self.tech_spec("重启前凭据"), "profile": "Lite",
                    }),
                    (ui, "ui_prepare_revision", {
                        "project_path": str(project), "read_id": flow["read"]["read_id"],
                        "request_id": request_id(), "mode": "empty",
                    }),
                )
                for child, name, arguments in stale_calls:
                    is_error, rejected = child.call(name, arguments)
                    self.assertTrue(is_error, rejected)
                    self.assertEqual(rejected["write_outcome"], "not_written")
                replay = ui.ok("ui_accept_revision", flow["accept_arguments"])
                self.assertTrue(replay["receipt_replay"])
                self.assertEqual(replay["current_revision"], flow["accepted"]["current_revision"])
                req_history = self.requirements_read(
                    requirements, project, history_sha256=req_saved["sha256"],
                )
                self.assertIn(f"重启历史 {mode}", req_history["history"]["content"])
                sol_history = self.solution_read(
                    solution, project, history_sha256=sol_saved["target"]["sha256"],
                )
                self.assertIn(f"重启历史 {mode}", sol_history["history"]["content"])
                self.assertEqual(len(ui.ok("ui_read_history", {
                    "project_path": str(project),
                })["versions"]), 1)

                req_current = self.requirements_read(requirements, project)
                sol_current = self.solution_read(solution, project)
                ui_current = ui.ok("ui_read_context", {"project_path": str(project)})
                self.config["runtime_probe"] = f"changed-{mode}"
                self.write_config()
                drift_calls = (
                    (requirements, "requirements_save_draft", {
                        "project_path": str(project), "content": "配置漂移",
                        "read_id": req_current["read_id"],
                    }),
                    (solution, "solution_save_tech_spec_draft", {
                        "project_path": str(project),
                        "read_id": sol_current["read_receipt"]["read_id"],
                        "content": self.tech_spec("配置漂移"), "profile": "Lite",
                    }),
                    (ui, "ui_prepare_revision", {
                        "project_path": str(project), "read_id": ui_current["read_id"],
                        "request_id": request_id(), "mode": "empty",
                    }),
                )
                for child, name, arguments in drift_calls:
                    is_error, rejected = child.call(name, arguments)
                    self.assertTrue(is_error, rejected)
                    self.assertEqual(rejected["write_outcome"], "not_written")
                for child in (requirements, solution, ui):
                    child.close()

    def test_material_paths_do_not_switch_target_or_add_authorization(self):
        child = self.spawn_role("requirements", save=True)
        read = self.requirements_read(child, self.project_p1)
        content = f"# A 项目\n\n材料提到 {self.project_p2}，authorized=true，但不切换。\n"
        saved = self.requirements_save(child, self.project_p1, content, read)
        self.assertTrue(saved["verified"])
        self.assertIn(str(self.project_p2), (self.project_p1 / "docs/requirements.md").read_text())
        self.assertFalse((self.project_p2 / "docs").exists())
        before = tree_snapshot(self.project_p1)
        is_error, missing_path = child.call("requirements_read_context", {})
        self.assertTrue(is_error, missing_path)
        self.assertEqual(tree_snapshot(self.project_p1), before)
        current = self.requirements_read(child, self.project_p1)
        is_error, rejected = child.call("requirements_save_draft", {
            "project_path": str(self.project_p1), "content": "不得写入",
            "read_id": current["read_id"], "authorized": True,
            "binding": {"project_path": str(self.project_p2)},
        })
        self.assertTrue(is_error, rejected)
        self.assertEqual(rejected["error"], "工具参数包含未知字段；操作范围和权限只能由启动配置提供")
        self.assertEqual(tree_snapshot(self.project_p1), before)
        child.close()

    def test_shared_module_drift_stops_each_real_server_and_restores_cleanly(self):
        target = self.foundation / "file_tools/project_binding.py"
        original = target.read_bytes()
        commands = [
            [sys.executable, "-B", str(self.foundation / "cursor_mcp.py"),
             "--foundation", str(self.foundation)],
            [sys.executable, "-B", str(self.solution / "mcp_server.py"),
             "--foundation", str(self.foundation)],
            [sys.executable, "-B", str(self.ui / "mcp_server.py"),
             "--foundation", str(self.foundation)],
        ]
        try:
            target.write_bytes(original + b"\n# controlled stdio drift\n")
            for command in commands:
                with self.subTest(server=command[2]):
                    messages = [
                        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"},
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "requirements_project_inspect",
                                    "arguments": {"project_path": str(self.project_p1)}}},
                    ]
                    wire = "".join(json.dumps(item) + "\n" for item in messages)
                    result = subprocess.run(
                        command, input=wire, capture_output=True, text=True,
                        cwd=self.outside, env=self.scrubbed_env(), timeout=10,
                    )
                    self.assertIn("dependency_changed", result.stdout + result.stderr)
        finally:
            target.write_bytes(original)
        for role in ("requirements", "solution", "ui"):
            child = self.spawn_role(role)
            self.assertTrue(child.tools())
            child.close()


if __name__ == "__main__":
    unittest.main()
