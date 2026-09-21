import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_foundation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifacts
import collaboration
import main_artifacts
import main_collaboration
import project_init
import project_state
import requirements


class MainCollaborationTests(unittest.TestCase):
    setUp = test_foundation.FoundationTests.setUp
    write_config = test_foundation.FoundationTests.write_config

    def authorization(self, project_id="demo"):
        return main_artifacts._issue_runtime_main(
            "main-test", "test-runtime", [project_id], runtime_verified=True)

    def project(self):
        project_init.create(self.app, "demo", "确认交接试点", "验证固定版本交接")
        root = (self.projects / "demo").resolve()
        requirements.save_draft(self.app, "demo", "# 需求 v0.1\n\n保持草案。", "missing")
        preview = artifacts.preview_register(
            self.app, "demo", "requirements", "requirements", "v0.1",
            "requirements", "方案讨论", "首版需求草案",
            path="docs/requirements.md", set_current=True)
        main_artifacts.apply_registration(
            self.authorization(), self.app, "demo",
            artifact_id="requirements", kind="requirements", version="v0.1",
            producer_role="requirements", purpose="方案讨论", summary="首版需求草案",
            path="docs/requirements.md", set_current=True,
            expected_project_sha256=preview["project_json_precondition"]["sha256"],
            expected_readme_sha256=preview["proposed_changes"]["readme"]["before_sha256"],
        )
        return root

    def confirmation_evidence(self, root, **changes):
        data = json.loads((root / "project.json").read_text())
        version = data["artifact_registry"]["entries"]["requirements"]["versions"][0]
        values = {
            "project_id": "demo", "provider": "codex", "authority": "test-runtime",
            "user_principal_id": "user-1", "session_id": "session-1",
            "message_id": "message-confirm-1", "confirmed_at": "2026-09-19T12:00:00Z",
            "statement": "确认该需求用于方案讨论。", "artifact_id": "requirements",
            "version": "v0.1", "content_sha256": artifacts.content_sha(version["content"]),
            "permitted_use": "方案讨论", "confirmed_scope": "需求文档全部已列范围",
            "non_authorizations": ("不授权开发", "不授权发布"),
            "blocking_open_items": (), "runtime_verified": True,
        }
        values.update(changes)
        return main_collaboration._issue_current_session_confirmation(**values)

    def confirm(self, root, evidence=None, **extra):
        preconditions = main_collaboration.confirmation_preconditions(self.app, "demo")
        preconditions.update(extra)
        return main_collaboration.confirm_current_session(
            self.authorization(), evidence or self.confirmation_evidence(root),
            self.app, "demo", **preconditions)

    def handoff_evidence(self, confirmation_id, **changes):
        values = {
            "project_id": "demo", "provider": "codex", "authority": "test-runtime",
            "user_principal_id": "user-1", "session_id": "session-1",
            "message_id": "message-handoff-1", "authorized_at": "2026-09-19T12:10:00Z",
            "statement": "把已确认需求交给方案角色，不启动开发。",
            "confirmation_ids": (confirmation_id,), "recipient_role": "solution",
            "recipient_principal_id": "solution-1", "recipient_authority": "test-runtime",
            "purpose": "方案讨论", "allowed_actions": ("读取确认快照", "编写方案"),
            "expected_outputs": ("方案文档",), "execution_authorized": False,
            "runtime_verified": True,
        }
        values.update(changes)
        return main_collaboration._issue_current_session_handoff(**values)

    def test_current_session_confirmation_creates_fixed_snapshot_and_reference(self):
        root = self.project()
        result = self.confirm(root)
        self.assertEqual(result["status"], "confirmed")
        self.assertFalse(result["document_status_changed"])
        decisions = collaboration.read_decisions(root)[1]
        record = decisions["confirmations"][0]
        self.assertEqual(record["confirmation_id"], result["confirmation_id"])
        self.assertTrue(record["evidence"]["runtime_authenticated"])
        snapshot = root / record["snapshot"]["path"]
        self.assertEqual(snapshot.read_bytes(), (root / "docs/requirements.md").read_bytes())
        data = json.loads((root / "project.json").read_text())
        version = data["artifact_registry"]["entries"]["requirements"]["versions"][0]
        self.assertEqual(version["confirmation_ids"], [result["confirmation_id"]])
        self.assertEqual(version["document_status"], "Draft")
        self.assertEqual(version["content"]["path"], record["snapshot"]["path"])
        self.assertEqual(data["artifacts"]["requirements"], record["snapshot"]["path"])
        self.assertEqual(collaboration.inspect(self.app, "demo")["status"], "consistent")

    def test_confirmation_is_idempotent_and_snapshot_survives_source_change(self):
        root = self.project()
        first = self.confirm(root)
        snapshot_path = root / first["snapshot"]["path"]
        snapshot_before = snapshot_path.read_bytes()
        second = self.confirm(root)
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(len(collaboration.read_decisions(root)[1]["confirmations"]), 1)
        (root / "docs/requirements.md").write_text("changed after confirmation")
        self.assertEqual(snapshot_path.read_bytes(), snapshot_before)
        preview = artifacts.preview_register(
            self.app, "demo", "requirements", "requirements", "v0.2",
            "requirements", "方案讨论", "第二版需求",
            path="docs/requirements.md", set_current=True)
        versions = preview["proposed_changes"]["artifact_registry"]["entries"]["requirements"]["versions"]
        self.assertEqual(versions[0]["content"]["path"], first["snapshot"]["path"])
        self.assertEqual(versions[1]["version"], "v0.2")

    def test_untrusted_mismatched_or_blocked_confirmation_is_rejected(self):
        root = self.project()
        preconditions = main_collaboration.confirmation_preconditions(self.app, "demo")
        with self.assertRaisesRegex(PermissionError, "受信运行时"):
            main_collaboration.confirm_current_session(
                self.authorization(), {"type": "current-session"}, self.app, "demo",
                **preconditions)
        with self.assertRaisesRegex(ValueError, "展示版本"):
            self.confirm(root, self.confirmation_evidence(root, content_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "阻塞未决项"):
            self.confirm(root, self.confirmation_evidence(
                root, message_id="blocked", blocking_open_items=("价格未定",)))
        self.assertFalse((root / "docs/decisions.md").exists())

    def test_confirmation_interruption_rolls_forward(self):
        root = self.project()

        def stop(stage):
            if stage == "after:docs/decisions.md":
                raise RuntimeError("stop after decisions")

        preconditions = main_collaboration.confirmation_preconditions(self.app, "demo")
        with self.assertRaisesRegex(RuntimeError, "stop after decisions"):
            main_collaboration.confirm_current_session(
                self.authorization(), self.confirmation_evidence(root), self.app, "demo",
                _failure_hook=stop, **preconditions)
        self.assertTrue((root / project_state.JOURNAL_NAME).is_file())
        recovered = main_collaboration.recover_collaboration(
            self.authorization(), self.app, "demo")
        self.assertEqual(recovered["operation"], "confirmation")
        self.assertIn("project.json", recovered["recovered_files"])
        self.assertEqual(collaboration.inspect(self.app, "demo")["status"], "consistent")

    def test_handoff_prepare_send_and_verified_receipt_are_separate(self):
        root = self.project()
        confirmation = self.confirm(root)
        evidence = self.handoff_evidence(confirmation["confirmation_id"])
        decisions_sha = collaboration.read_decisions(root)[2]
        prepared = main_collaboration.prepare_handoff(
            self.authorization(), evidence, self.app, "demo",
            expected_decisions_sha256=decisions_sha)
        self.assertEqual(prepared["status"], "prepared")
        self.assertFalse(prepared["downstream_started"])
        path = root / f"docs/handoffs/{prepared['handoff_id']}.json"
        handoff = json.loads(path.read_text())
        self.assertEqual(handoff["status"], "prepared")
        self.assertFalse(handoff["execution_authorized"])
        repeated_prepare = main_collaboration.prepare_handoff(
            self.authorization(), evidence, self.app, "demo",
            expected_decisions_sha256=decisions_sha)
        self.assertEqual(repeated_prepare["status"], "unchanged")

        delivery = main_collaboration._issue_delivery_evidence(
            project_id="demo", handoff_id=prepared["handoff_id"], provider="buzz",
            authority="test-runtime", message_id="delivery-1",
            sent_at="2026-09-19T12:11:00Z", recipient_principal_id="solution-1",
            runtime_verified=True)
        sent = main_collaboration.record_handoff_sent(
            self.authorization(), delivery, self.app, "demo",
            expected_handoff_sha256=main_collaboration.digest(path.read_bytes()))
        self.assertEqual(sent["status"], "sent")
        self.assertFalse(sent["downstream_started"])

        receipt = main_collaboration._issue_recipient_receipt(
            project_id="demo", handoff_id=prepared["handoff_id"],
            principal_id="solution-1", authority="test-runtime",
            received_at="2026-09-19T12:12:00Z",
            observed_inputs=((confirmation["confirmation_id"],
                              confirmation["snapshot"]["sha256"]),),
            goal_summary="输出方案文档", scope_summary="只读取确认需求并设计方案",
            open_items_summary="没有阻塞未决项", runtime_verified=True)
        received = main_collaboration.record_handoff_receipt(
            self.authorization(), receipt, self.app, "demo",
            expected_handoff_sha256=main_collaboration.digest(path.read_bytes()))
        self.assertEqual(received["status"], "received-verified")
        self.assertFalse(received["execution_authorized"])
        self.assertFalse(received["downstream_started"])
        repeated_receipt = main_collaboration.record_handoff_receipt(
            self.authorization(), receipt, self.app, "demo",
            expected_handoff_sha256=main_collaboration.digest(path.read_bytes()))
        self.assertEqual(repeated_receipt["status"], "unchanged")
        self.assertEqual(collaboration.inspect(self.app, "demo")["status"], "consistent")

    def test_handoff_rejects_unconfirmed_purpose_and_wrong_receipt(self):
        root = self.project()
        confirmation = self.confirm(root)
        decisions_sha = collaboration.read_decisions(root)[2]
        with self.assertRaisesRegex(ValueError, "用途超出确认"):
            main_collaboration.prepare_handoff(
                self.authorization(),
                self.handoff_evidence(confirmation["confirmation_id"], purpose="开发实现"),
                self.app, "demo", expected_decisions_sha256=decisions_sha)

        prepared = main_collaboration.prepare_handoff(
            self.authorization(), self.handoff_evidence(confirmation["confirmation_id"]),
            self.app, "demo", expected_decisions_sha256=decisions_sha)
        path = root / f"docs/handoffs/{prepared['handoff_id']}.json"
        delivery = main_collaboration._issue_delivery_evidence(
            project_id="demo", handoff_id=prepared["handoff_id"], provider="buzz",
            authority="test-runtime", message_id="delivery-2",
            sent_at="2026-09-19T12:11:00Z", recipient_principal_id="solution-1",
            runtime_verified=True)
        main_collaboration.record_handoff_sent(
            self.authorization(), delivery, self.app, "demo",
            expected_handoff_sha256=main_collaboration.digest(path.read_bytes()))
        before = path.read_bytes()
        wrong = main_collaboration._issue_recipient_receipt(
            project_id="demo", handoff_id=prepared["handoff_id"],
            principal_id="other", authority="test-runtime",
            received_at="2026-09-19T12:12:00Z",
            observed_inputs=((confirmation["confirmation_id"],
                              confirmation["snapshot"]["sha256"]),),
            goal_summary="错误接收者", scope_summary="错误", open_items_summary="无",
            runtime_verified=True)
        with self.assertRaisesRegex(PermissionError, "指定接收者"):
            main_collaboration.record_handoff_receipt(
                self.authorization(), wrong, self.app, "demo",
                expected_handoff_sha256=main_collaboration.digest(before))
        self.assertEqual(path.read_bytes(), before)
        wrong_version = main_collaboration._issue_recipient_receipt(
            project_id="demo", handoff_id=prepared["handoff_id"],
            principal_id="solution-1", authority="test-runtime",
            received_at="2026-09-19T12:12:00Z",
            observed_inputs=((confirmation["confirmation_id"], "0" * 64),),
            goal_summary="输出方案", scope_summary="读取指定需求",
            open_items_summary="无", runtime_verified=True)
        with self.assertRaisesRegex(ValueError, "输入版本"):
            main_collaboration.record_handoff_receipt(
                self.authorization(), wrong_version, self.app, "demo",
                expected_handoff_sha256=main_collaboration.digest(before))
        self.assertEqual(path.read_bytes(), before)

    def test_ui_file_set_confirmation_snapshots_all_members(self):
        root = self.project()
        (root / "ui").mkdir()
        (root / "ui/index.html").write_text("<h1>demo</h1>")
        member_sha = artifacts.digest((root / "ui/index.html").read_bytes())
        manifest = {"schema_version": 1, "entrypoint": "ui/index.html",
                    "files": [{"path": "ui/index.html", "sha256": member_sha}]}
        (root / "ui/artifact-manifest.json").write_text(json.dumps(manifest))
        preview = artifacts.preview_register(
            self.app, "demo", "ui", "ui", "v0.1", "ui", "方案讨论", "UI 演示",
            manifest="ui/artifact-manifest.json", set_current=True)
        main_artifacts.apply_registration(
            self.authorization(), self.app, "demo", artifact_id="ui", kind="ui",
            version="v0.1", producer_role="ui", purpose="方案讨论", summary="UI 演示",
            manifest="ui/artifact-manifest.json", set_current=True,
            expected_project_sha256=preview["project_json_precondition"]["sha256"],
            expected_readme_sha256=preview["proposed_changes"]["readme"]["before_sha256"])
        data = json.loads((root / "project.json").read_text())
        ui_version = data["artifact_registry"]["entries"]["ui"]["versions"][0]
        evidence = main_collaboration._issue_current_session_confirmation(
            project_id="demo", provider="codex", authority="test-runtime",
            user_principal_id="user-1", session_id="session-1", message_id="ui-confirm",
            confirmed_at="2026-09-19T13:00:00Z", statement="确认 UI 用于方案讨论。",
            artifact_id="ui", version="v0.1",
            content_sha256=artifacts.content_sha(ui_version["content"]),
            permitted_use="方案讨论", confirmed_scope="UI 演示全部成员",
            non_authorizations=("不授权开发",), blocking_open_items=(),
            runtime_verified=True)
        result = self.confirm(root, evidence)
        snapshot = result["snapshot"]
        self.assertEqual(snapshot["type"], "file-set")
        self.assertEqual(len(snapshot["files"]), 1)
        self.assertTrue((root / snapshot["manifest_path"]).is_file())
        self.assertTrue((root / snapshot["files"][0]["snapshot_path"]).is_file())

    def test_inspect_rejects_snapshot_path_escape(self):
        root = self.project()
        self.confirm(root)
        text, decisions, _ = collaboration.read_decisions(root)
        decisions["confirmations"][0]["snapshot"]["path"] = "../outside"
        (root / "docs/decisions.md").write_text(
            collaboration.render_decisions(text, decisions))
        result = collaboration.inspect(self.app, "demo")
        self.assertEqual(result["status"], "attention_required")
        self.assertEqual(result["issues"][0]["code"], "invalid_confirmation")

    def test_mutation_core_has_no_cli(self):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(main_collaboration.__file__))],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("没有 CLI", result.stderr)


if __name__ == "__main__":
    unittest.main()
