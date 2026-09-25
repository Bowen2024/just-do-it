from pathlib import Path
import sys
import unittest

import test_foundation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifacts
import project_init
import requirements


class RequirementsTests(unittest.TestCase):
    setUp = test_foundation.FoundationTests.setUp
    write_config = test_foundation.FoundationTests.write_config

    def project(self):
        project_init.create(self.app, "demo", "需求试点", "验证共享")
        return (self.projects / "demo").resolve()

    @staticmethod
    def valid_prd():
        return """# PRD

## 用户结果与成功指标
用户获得可验证结果。

## 具体案例
输入 → 处理 → 结果 → 失败恢复。

## 范围与边界
本次只做核心流程。

## REQ 与 AC

## REQ-001 完成操作

### AC-001 成功
- 结果类型：成功
- 前置条件：输入有效
- 操作：提交
- 可观察结果：显示成功
- 验证方式：人工及自动检查

### AC-002 失败
- 结果类型：失败
- 前置条件：输入无效
- 操作：提交
- 可观察结果：显示可恢复错误
- 验证方式：人工及自动检查

## 业务流程图
```mermaid
flowchart TD
A --> B
```

## 业务时序图
```mermaid
sequenceDiagram
U->>S: 提交
```

## 事实、假设与待决事项
无阻塞项。

## 变更摘要
初版。"""

    def test_context_is_read_only(self):
        root = self.project()
        result = requirements.context(self.app, "demo")
        self.assertEqual(result["documents"][-1]["sha256"], "missing")
        self.assertFalse((root / "docs").exists())

    def test_save_always_draft_and_preserves_old_version(self):
        root = self.project()
        first = requirements.save_draft(self.app, "demo", "# 需求\n第一版", "missing")
        before = (root / "docs/requirements.md").read_bytes()
        second = requirements.save_draft(self.app, "demo", "# 需求\n第二版", first["sha256"])
        self.assertEqual(second["status"], "Draft")
        self.assertFalse(second["approval_verified"])
        self.assertEqual((root / f"docs/requirements-history/{first['sha256']}.md").read_bytes(), before)
        self.assertIn("status: Draft", (root / "docs/requirements.md").read_text())
        self.assertTrue(second["index_update_required"])

    def test_stale_version_cannot_overwrite(self):
        root = self.project()
        requirements.save_draft(self.app, "demo", "第一版", "missing")
        before = (root / "docs/requirements.md").read_bytes()
        with self.assertRaisesRegex(ValueError, "版本冲突"):
            requirements.save_draft(self.app, "demo", "旧线程覆盖", "missing")
        self.assertEqual(before, (root / "docs/requirements.md").read_bytes())

    def test_same_content_is_noop(self):
        self.project()
        first = requirements.save_draft(self.app, "demo", "第一版", "missing")
        second = requirements.save_draft(self.app, "demo", "第一版", first["sha256"])
        self.assertFalse(second["changed"])

    def test_symlink_docs_is_denied(self):
        root = self.project()
        (root / "docs").symlink_to(self.upstream)
        with self.assertRaisesRegex(ValueError, "软链"):
            requirements.save_draft(self.app, "demo", "越界", "missing")
        self.assertFalse((self.upstream / "requirements.md").exists())

    def test_recovery_reads_latest(self):
        self.project()
        result = requirements.save_draft(self.app, "demo", "已改为人工审核后发送", "missing")
        recovered = requirements.context(self.app, "demo")["documents"][-1]
        self.assertEqual(result["sha256"], recovered["sha256"])
        self.assertIn("人工审核", recovered["content"])

    def test_empty_and_oversize_rejected(self):
        root = self.project()
        for body in (" ", "x" * requirements.LIMIT):
            with self.assertRaises(ValueError):
                requirements.save_draft(self.app, "demo", body, "missing")
        self.assertFalse((root / "docs").exists())

    def test_existing_lock_preserved(self):
        root = self.project()
        lock = root / ".requirements.lock"
        lock.write_text("in progress")
        with self.assertRaisesRegex(ValueError, "锁已存在"):
            requirements.save_draft(self.app, "demo", "需求", "missing")
        self.assertEqual(lock.read_text(), "in progress")

    def test_source_digest_mismatch_is_rejected(self):
        root = self.project()
        body = "`README.md` 读取时 SHA-256：`abc123`"
        with self.assertRaisesRegex(ValueError, "README.md 来源摘要不匹配"):
            requirements.save_draft(self.app, "demo", body, "missing")
        self.assertFalse((root / "docs").exists())
        self.assertFalse((root / ".requirements.lock").exists())

    def test_matching_source_digests_are_reported(self):
        self.project()
        current = requirements.context(self.app, "demo")
        sources = {item["path"]: item["sha256"] for item in current["documents"][:2]}
        body = (f"`project.json` 读取时 SHA-256：`{sources['project.json']}`\n"
                f"`README.md` 读取时 SHA-256：`{sources['README.md']}`")
        result = requirements.save_draft(self.app, "demo", body, "missing")
        self.assertEqual(result["source_sha256"], sources)

    def test_role_contract_hides_internal_save_details(self):
        role = (Path(__file__).resolve().parents[1] / "capabilities/requirements.md").read_text()
        self.assertIn("不要求用户说“进入 R”", role)
        self.assertIn("不要要求用户提供命令、绝对路径、expected-sha", role)
        self.assertIn("保存工具会重新核验并拒绝不一致值", role)

    def test_prd_save_inspect_and_history(self):
        root = self.project()
        first = requirements.save_prd_draft(
            self.app, "demo", self.valid_prd(), "missing", "missing"
        )
        self.assertEqual(requirements.inspect_prd(self.app, "demo")["status"], "ready_for_review")
        before = (root / "docs/PRD.md").read_bytes()
        second = requirements.save_prd_draft(
            self.app, "demo", self.valid_prd() + "\n补充说明。", first["sha256"], "missing"
        )
        self.assertEqual(
            (root / f"docs/prd-history/{first['sha256']}.md").read_bytes(), before
        )
        self.assertFalse(second["approval_verified"])

    def test_prd_inspect_requires_complete_ac_and_two_business_diagrams(self):
        self.project()
        incomplete = self.valid_prd().replace("- 验证方式：人工及自动检查", "", 1)
        incomplete = incomplete.replace("sequenceDiagram", "stateDiagram")
        requirements.save_prd_draft(self.app, "demo", incomplete, "missing", "missing")
        codes = {issue["code"] for issue in requirements.inspect_prd(self.app, "demo")["issues"]}
        self.assertIn("acceptance_criteria_incomplete", codes)
        self.assertIn("business_sequence_diagram_missing", codes)

    def test_prd_source_version_and_frontmatter_are_enforced(self):
        self.project()
        lightweight = requirements.save_draft(self.app, "demo", "# 轻量需求", "missing")
        with self.assertRaisesRegex(ValueError, "轻量需求输入版本冲突"):
            requirements.save_prd_draft(
                self.app, "demo", self.valid_prd(), "missing", "missing"
            )
        with self.assertRaisesRegex(ValueError, "不得自带 front matter"):
            requirements.save_prd_draft(
                self.app, "demo", "---\nstatus: Confirmed\n---\nPRD", "missing", lightweight["sha256"]
            )

    def test_prd_becomes_the_requirements_registration_candidate(self):
        self.project()
        lightweight = requirements.save_draft(self.app, "demo", "# 轻量需求", "missing")
        before = artifacts.inspect(self.app, "demo")
        self.assertEqual(before["candidates"][0]["content"]["path"], "docs/requirements.md")
        requirements.save_prd_draft(
            self.app, "demo", self.valid_prd(), "missing", lightweight["sha256"]
        )
        after = artifacts.inspect(self.app, "demo")
        self.assertEqual(after["candidates"][0]["content"]["path"], "docs/PRD.md")


if __name__ == "__main__":
    unittest.main()
