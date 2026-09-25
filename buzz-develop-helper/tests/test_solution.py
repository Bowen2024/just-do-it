import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_foundation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifacts
import project_init
import main_artifacts
import main_collaboration
import requirements
import solution


class SolutionTests(unittest.TestCase):
    setUp = test_foundation.FoundationTests.setUp
    write_config = test_foundation.FoundationTests.write_config

    def project(self, prd_body=None):
        project_init.create(self.app, "demo", "方案试点", "验证实现契约")
        root = (self.projects / "demo").resolve()
        if prd_body is not None:
            saved = requirements.save_prd_draft(
                self.app, "demo", prd_body, "missing", "missing"
            )
            self.confirm_prd(root, saved["sha256"])
        return root

    def confirm_prd(self, root, prd_sha):
        authorization = main_artifacts._issue_runtime_main(
            "main-1", "test-runtime", ["demo"], runtime_verified=True
        )
        preview = artifacts.preview_register(
            self.app, "demo", "requirements", "requirements", "v0.1",
            "requirements", "形成技术方案", "完整 A 阶段 PRD",
            path="docs/PRD.md", set_current=True,
        )
        main_artifacts.apply_registration(
            authorization, self.app, "demo",
            artifact_id="requirements", kind="requirements", version="v0.1",
            producer_role="requirements", purpose="形成技术方案",
            summary="完整 A 阶段 PRD", path="docs/PRD.md", set_current=True,
            expected_project_sha256=preview["project_json_precondition"]["sha256"],
            expected_readme_sha256=preview["proposed_changes"]["readme"]["before_sha256"],
        )
        evidence = main_collaboration._issue_current_session_confirmation(
            project_id="demo", provider="buzz", authority="relay:local",
            user_principal_id="user-1", session_id="session-1", message_id="event-1",
            confirmed_at="2026-09-24T10:00:00Z",
            statement="确认该 PRD 用于形成技术方案。",
            artifact_id="requirements", version="v0.1", content_sha256=prd_sha,
            permitted_use="形成技术方案",
            confirmed_scope="PRD 中本次范围与 REQ/AC",
            non_authorizations=("不授权启动下游",),
            blocking_open_items=(), runtime_verified=True,
        )
        main_collaboration.confirm_current_session(
            authorization, evidence, self.app, "demo",
            **main_collaboration.confirmation_preconditions(self.app, "demo"),
        )

    @staticmethod
    def valid_prd():
        return """# PRD

## 用户结果与成功指标
用户能上传文件。

## 具体案例
选择文件 → 校验 → 显示结果 → 失败时重选。

## 范围与边界
只处理单文件。

## REQ 与 AC

## REQ-001 上传

### AC-001 成功
- 结果类型：成功
- 前置条件：有效文件
- 操作：上传
- 可观察结果：看到成功
- 验证方式：界面检查

### AC-002 失败
- 结果类型：失败
- 前置条件：格式错误
- 操作：上传
- 可观察结果：看到可恢复提示
- 验证方式：界面检查

## 业务流程图
```mermaid
flowchart TD
A --> B
```

## 业务时序图
```mermaid
sequenceDiagram
U->>S: 上传
```

## 事实、假设与待决事项
无阻塞项。

## 变更摘要
初版。"""

    @staticmethod
    def valid_spec():
        return """# 技术方案

## 1. 用户结果与覆盖范围
REQ-001 覆盖 AC-001、AC-002。

## 2. 系统边界与接口
API-001 处理上传。

## 3. 数据与生命周期
文件仅临时保存。

## 4. 模型、提示词与工具
不适用：无 AI。

## 5. 算法、状态与体验影响
校验后处理。

## 6. 异常、重试与恢复
格式错误允许重新选择。

## 7. 目录、运行与验证条件
本地测试。

## 8. 技术时序
客户端调用 API-001，服务返回结果或错误。

## 9. 依据、假设与可行性
当前为 reasoned，等待真实联调。

## 10. 取舍与未决项
已决定同步校验；没有阻塞项。

## 11. REQ/AC 覆盖表
| REQ | AC | 实现设计/API | 成功路径 | 失败路径 | 验证方式 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | AC-001、AC-002 | API-001 | 上传成功 | 格式错误 | 自动测试 | covered |
"""

    def test_context_is_read_only(self):
        root = self.project()
        result = solution.context(self.app, "demo")
        self.assertEqual(result["documents"][2]["sha256"], "missing")
        self.assertEqual(result["documents"][4]["sha256"], "missing")
        self.assertFalse((root / "docs").exists())

    def test_save_requires_prd(self):
        root = self.project()
        with self.assertRaisesRegex(ValueError, "缺少 docs/PRD.md"):
            solution.save_tech_spec_draft(
                self.app, "demo", self.valid_spec(), "missing", "missing", "Lite"
            )
        self.assertFalse((root / "docs").exists())

    def test_unconfirmed_prd_cannot_save_or_appear_ready(self):
        project_init.create(self.app, "demo", "方案试点", "验证确认边界")
        requirements.save_prd_draft(
            self.app, "demo", self.valid_prd(), "missing", "missing"
        )
        prd_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        with self.assertRaisesRegex(ValueError, "形成技术方案"):
            solution.save_tech_spec_draft(
                self.app, "demo", self.valid_spec(), "missing", prd_sha, "Lite"
            )
        codes = {issue["code"] for issue in solution.inspect(self.app, "demo")["issues"]}
        self.assertIn("prd_not_confirmed_for_solution", codes)

    def test_save_is_draft_binds_prd_and_preserves_history(self):
        root = self.project(self.valid_prd())
        current = solution.context(self.app, "demo")
        req_sha = current["documents"][3]["sha256"]
        first = solution.save_tech_spec_draft(
            self.app, "demo", self.valid_spec(), "missing", req_sha, "Standard"
        )
        before = (root / "docs/tech-spec.md").read_bytes()
        second = solution.save_tech_spec_draft(
            self.app,
            "demo",
            self.valid_spec().replace("本地测试。", "本地与集成测试。"),
            first["sha256"],
            req_sha,
            "Standard",
        )
        rendered = (root / "docs/tech-spec.md").read_text()
        self.assertIn("status: Draft", rendered)
        self.assertIn("approval_verified: false", rendered)
        self.assertIn(f"prd_sha256: {req_sha}", rendered)
        self.assertIn(first["prd_confirmation_ids"][0], rendered)
        self.assertEqual((root / f"docs/tech-spec-history/{first['sha256']}.md").read_bytes(), before)
        self.assertTrue(second["index_update_required"])

    def test_stale_tech_or_prd_cannot_be_overwritten(self):
        self.project(self.valid_prd())
        current = solution.context(self.app, "demo")
        req_sha = current["documents"][3]["sha256"]
        saved = solution.save_tech_spec_draft(
            self.app, "demo", self.valid_spec(), "missing", req_sha, "Lite"
        )
        with self.assertRaisesRegex(ValueError, "方案版本冲突"):
            solution.save_tech_spec_draft(
                self.app, "demo", self.valid_spec(), "missing", req_sha, "Lite"
            )
        requirements.save_prd_draft(
            self.app, "demo", self.valid_prd() + "\n变更", req_sha, "missing"
        )
        with self.assertRaisesRegex(ValueError, "PRD 输入版本冲突"):
            solution.save_tech_spec_draft(
                self.app, "demo", self.valid_spec(), saved["sha256"], req_sha, "Lite"
            )

    def test_invalid_profile_and_frontmatter_are_rejected(self):
        self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        with self.assertRaisesRegex(ValueError, "profile 必须"):
            solution.save_tech_spec_draft(
                self.app, "demo", self.valid_spec(), "missing", req_sha, "S1"
            )
        with self.assertRaisesRegex(ValueError, "不得自带 front matter"):
            solution.save_tech_spec_draft(
                self.app, "demo", "---\nstatus: Confirmed\n---\n正文", "missing", req_sha, "Lite"
            )

    def test_existing_lock_and_symlink_docs_are_rejected(self):
        root = self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        lock = root / ".solution.lock"
        lock.write_text("in progress")
        with self.assertRaisesRegex(ValueError, "方案写入锁已存在"):
            solution.save_tech_spec_draft(
                self.app, "demo", self.valid_spec(), "missing", req_sha, "Lite"
            )
        self.assertEqual(lock.read_text(), "in progress")

        lock.unlink()
        (root / "docs/solution.md").symlink_to(self.upstream)
        with self.assertRaisesRegex(ValueError, "软链"):
            solution.context(self.app, "demo")

    def test_inspect_reports_complete_structural_coverage(self):
        self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        solution.save_tech_spec_draft(
            self.app, "demo", self.valid_spec(), "missing", req_sha, "Standard"
        )
        result = solution.inspect(self.app, "demo")
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(result["prd"]["ac_ids"], ["AC-001", "AC-002"])
        self.assertTrue(result["approval_checked"])
        self.assertFalse(result["semantic_correctness_checked"])

    def test_inspect_finds_unknown_and_uncovered_references(self):
        self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        body = self.valid_spec().replace("AC-001、AC-002", "AC-001、AC-999")
        body = body.replace("| AC-001、AC-002 |", "| AC-001、AC-999 |")
        solution.save_tech_spec_draft(self.app, "demo", body, "missing", req_sha, "AI")
        result = solution.inspect(self.app, "demo")
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("unknown_requirement_references", codes)
        self.assertIn("uncovered_acceptance_criteria", codes)

    def test_standard_and_ai_profile_structure_is_checked(self):
        self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        incomplete = self.valid_spec().replace("## 8. 技术时序", "## 18. 技术时序")
        saved = solution.save_tech_spec_draft(
            self.app, "demo", incomplete, "missing", req_sha, "Standard"
        )
        result = solution.inspect(self.app, "demo")
        self.assertIn("required_sections_missing", {issue["code"] for issue in result["issues"]})

        ai_body = self.valid_spec().replace("不适用：无 AI。", "不适用：无 AI。")
        solution.save_tech_spec_draft(
            self.app, "demo", ai_body, saved["sha256"], req_sha, "AI"
        )
        result = solution.inspect(self.app, "demo")
        self.assertIn("ai_contract_incomplete", {issue["code"] for issue in result["issues"]})

    def test_coverage_requires_table_membership_not_prose_mention(self):
        self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        body = self.valid_spec().replace("| AC-001、AC-002 |", "| AC-001 |")
        solution.save_tech_spec_draft(self.app, "demo", body, "missing", req_sha, "Standard")
        result = solution.inspect(self.app, "demo")
        uncovered = next(
            issue for issue in result["issues"] if issue["code"] == "uncovered_acceptance_criteria"
        )
        self.assertEqual(uncovered["ac"], ["AC-002"])

    def test_inspect_detects_changed_prd_baseline(self):
        self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        solution.save_tech_spec_draft(
            self.app, "demo", self.valid_spec(), "missing", req_sha, "Standard"
        )
        requirements.save_prd_draft(
            self.app, "demo", self.valid_prd() + "\n新增说明", req_sha, "missing"
        )
        result = solution.inspect(self.app, "demo")
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("prd_baseline_mismatch", codes)

    def test_source_digest_claim_is_checked(self):
        self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        with self.assertRaisesRegex(ValueError, "docs/PRD.md 来源摘要不匹配"):
            solution.save_tech_spec_draft(
                self.app,
                "demo",
                self.valid_spec() + "\n`docs/PRD.md` SHA-256：`abc123`",
                "missing",
                req_sha,
                "Lite",
            )

    def test_cli_save_requires_apply(self):
        self.project(self.valid_prd())
        current = solution.context(self.app, "demo")
        req_sha = current["documents"][3]["sha256"]
        script = Path(solution.__file__)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(script),
                "--foundation",
                str(self.app),
                "save-tech-spec-draft",
                "demo",
                "--expected-tech-sha",
                "missing",
                "--expected-prd-sha",
                req_sha,
                "--profile",
                "Lite",
            ],
            input=self.valid_spec(),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("保存需要 --apply", json.loads(result.stderr)["error"])

    def test_project_state_lock_blocks_solution_save(self):
        root = self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        state_lock = root / ".project-state.lock"
        state_lock.write_text("in progress")
        with self.assertRaisesRegex(ValueError, "项目状态写入锁已存在"):
            solution.save_tech_spec_draft(
                self.app, "demo", self.valid_spec(), "missing", req_sha, "Lite"
            )
        self.assertEqual(state_lock.read_text(), "in progress")

    def test_interrupted_atomic_replace_preserves_current_and_releases_locks(self):
        root = self.project(self.valid_prd())
        req_sha = solution.context(self.app, "demo")["documents"][3]["sha256"]
        first = solution.save_tech_spec_draft(
            self.app, "demo", self.valid_spec(), "missing", req_sha, "Lite"
        )
        target = root / "docs/tech-spec.md"
        before = target.read_bytes()
        with mock.patch.object(solution.os, "replace", side_effect=OSError("interrupted")):
            with self.assertRaisesRegex(OSError, "interrupted"):
                solution.save_tech_spec_draft(
                    self.app,
                    "demo",
                    self.valid_spec().replace("本地测试。", "更新测试。"),
                    first["sha256"],
                    req_sha,
                    "Lite",
                )
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((root / ".solution.lock").exists())
        self.assertFalse((root / ".project-state.lock").exists())
        self.assertEqual(list((root / "docs").glob(".tech-spec-*")), [])


if __name__ == "__main__":
    unittest.main()
