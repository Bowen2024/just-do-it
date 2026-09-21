import hashlib
import hmac
import json
from pathlib import Path
import sys
import unittest

import test_foundation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifacts
import collaboration
import host_tools
import project_init
import requirements
import trusted_context


class HostToolTests(unittest.TestCase):
    setUp = test_foundation.FoundationTests.setUp
    write_config = test_foundation.FoundationTests.write_config

    KEY = b"unit-05-host-context-verification-key"
    NOW = 1_800_000_000

    def project(self):
        project_init.create(self.app, "demo", "宿主接入试点", "验证可信上下文")
        root = (self.projects / "demo").resolve()
        requirements.save_draft(self.app, "demo", "# 需求 v0.1\n\n保持草案。", "missing")
        return root

    def payload(self, *, role="main", tools=None, agent="main-1",
                event="event-1", root="root-1", session="session-1",
                project="demo", user="user-1", recipient=None, **changes):
        if tools is None:
            tools = [
                "artifact.inspect", "artifact.preview-register",
                "collaboration.inspect", "artifact.register",
                "confirmation.confirm-current",
            ]
        value = {
            "schema_version": 1,
            "provider": "buzz",
            "authority": "relay:local",
            "project_id": project,
            "agent_principal_id": agent,
            "agent_authority": "buzz-agent:local",
            "agent_role": role,
            "channel_id": "channel-1",
            "session_id": session,
            "root_event_id": root,
            "event_id": event,
            "user_principal_id": user,
            "event_time": "2026-09-20T12:00:00Z",
            "statement": "确认当前展示版本，并按指定用途处理。",
            "recipient": recipient,
            "tools": tools,
            "issued_at": self.NOW - 10,
            "expires_at": self.NOW + 100,
            "nonce": "1" * 32,
        }
        value.update(changes)
        return value

    def envelope(self, payload):
        signature = hmac.new(
            self.KEY, trusted_context.canonical_payload(payload), hashlib.sha256
        ).hexdigest()
        return {"payload": payload, "signature": signature}

    def expected(self, *, agent="main-1", agent_authority="buzz-agent:local",
                 user="user-1", event="event-1", root="root-1",
                 session="session-1", project="demo", recipient=None):
        return trusted_context.ExpectedTurn(
            provider="buzz", authority="relay:local", project_id=project,
            agent_principal_id=agent, agent_authority=agent_authority,
            user_principal_id=user, channel_id="channel-1",
            session_id=session, root_event_id=root, event_id=event,
            recipient_principal_id=(recipient or {}).get("principal_id"),
            recipient_authority=(recipient or {}).get("authority"),
        )

    def verified(self, payload=None, expected=None):
        payload = payload or self.payload()
        return trusted_context.HostContextVerifier(
            self.KEY, clock=lambda: self.NOW
        ).verify(self.envelope(payload), expected_turn=expected or self.expected(
            agent=payload["agent_principal_id"], event=payload["event_id"],
            agent_authority=payload["agent_authority"], user=payload["user_principal_id"],
            root=payload["root_event_id"], session=payload["session_id"],
            project=payload["project_id"], recipient=payload["recipient"],
        ))

    def register(self, surface):
        return surface.call("artifact.register", {
            "artifact_id": "requirements", "kind": "requirements",
            "version": "v0.1", "producer_role": "requirements",
            "purpose": "方案讨论", "summary": "首版需求草案",
            "path": "docs/requirements.md", "set_current": True,
        })

    def confirm(self, surface, root):
        data = json.loads((root / "project.json").read_text())
        version = data["artifact_registry"]["entries"]["requirements"]["versions"][0]
        return surface.call("confirmation.confirm-current", {
            "artifact_id": "requirements", "version": "v0.1",
            "content_sha256": artifacts.content_sha(version["content"]),
            "permitted_use": "方案讨论", "confirmed_scope": "需求全部已列范围",
            "non_authorizations": ["不授权开发"], "blocking_open_items": [],
        })

    def test_forged_identity_routing_and_role_claims_fail_signature(self):
        original = self.payload(recipient={"principal_id": "solution-1",
                                           "authority": "buzz-agent:local"},
                                tools=["handoff.prepare"])
        verifier = trusted_context.HostContextVerifier(self.KEY, clock=lambda: self.NOW)
        envelope = self.envelope(original)
        for field, value in (
            ("agent_role", "requirements"),
            ("agent_principal_id", "forged-main"),
            ("user_principal_id", "forged-user"),
            ("project_id", "other"),
            ("root_event_id", "wrong-root"),
            ("event_id", "wrong-event"),
        ):
            with self.subTest(field=field):
                forged = json.loads(json.dumps(envelope))
                forged["payload"][field] = value
                with self.assertRaisesRegex(PermissionError, "签名不匹配"):
                    verifier.verify(forged, expected_turn=self.expected(
                        recipient=original["recipient"]))
        forged = json.loads(json.dumps(envelope))
        forged["payload"]["recipient"]["principal_id"] = "other-recipient"
        with self.assertRaisesRegex(PermissionError, "签名不匹配"):
            verifier.verify(forged, expected_turn=self.expected(
                recipient=original["recipient"]))

    def test_even_valid_envelope_is_rejected_for_wrong_live_turn(self):
        payload = self.payload(recipient={"principal_id": "solution-1",
                                          "authority": "buzz-agent:local"},
                               tools=["handoff.prepare"])
        verifier = trusted_context.HostContextVerifier(self.KEY, clock=lambda: self.NOW)
        envelope = self.envelope(payload)
        cases = (
            {"project": "other"}, {"root": "other-root"},
            {"event": "other-event"}, {"session": "other-session"},
            {"agent": "other-agent"}, {"agent_authority": "other-authority"},
            {"user": "other-user"},
            {"recipient": {"principal_id": "other", "authority": "buzz-agent:local"}},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                values = {"recipient": payload["recipient"]}
                values.update(changes)
                with self.assertRaisesRegex(PermissionError, "不匹配"):
                    verifier.verify(envelope, expected_turn=self.expected(**values))

        verified = verifier.verify(envelope, expected_turn=self.expected(
            recipient=payload["recipient"]
        ))
        self.assertEqual(verified.user_principal_id, "user-1")
        with self.assertRaisesRegex(PermissionError, "nonce 已被使用"):
            verifier.verify(envelope, expected_turn=self.expected(
                recipient=payload["recipient"]
            ))

        verifier = trusted_context.HostContextVerifier(self.KEY, clock=lambda: self.NOW)
        with self.assertRaisesRegex(PermissionError, "指定接收者不匹配"):
            verifier.verify(envelope, expected_turn=self.expected(recipient=None))

    def test_worker_only_sees_task_tools_and_cannot_call_main_write(self):
        self.project()
        payload = self.payload(
            role="requirements", agent="requirements-1",
            tools=["requirements.context", "requirements.save-draft",
                   "artifact.inspect", "collaboration.inspect"],
        )
        context = self.verified(payload)
        surface = host_tools.HostToolSurface(context, self.app)
        self.assertEqual(surface.list_tools(), [
            "artifact.inspect", "collaboration.inspect",
            "requirements.context", "requirements.save-draft",
        ])
        with self.assertRaisesRegex(PermissionError, "未获工具 capability"):
            self.register(surface)
        with self.assertRaisesRegex(PermissionError, "只有宿主绑定"):
            import main_artifacts
            main_artifacts.authorization_from_host_context(context)

    def test_host_rejects_worker_envelope_that_contains_main_tool(self):
        payload = self.payload(
            role="requirements", agent="requirements-1",
            tools=["requirements.context", "artifact.register"],
        )
        with self.assertRaisesRegex(PermissionError, "越权工具"):
            self.verified(payload)

    def test_main_registration_and_confirmation_use_bound_identities(self):
        root = self.project()
        context = self.verified()
        surface = host_tools.HostToolSurface(context, self.app)
        self.assertIn("artifact.register", surface.list_tools())
        self.assertEqual(self.register(surface)["status"], "applied")
        data = json.loads((root / "project.json").read_text())
        actor = data["artifact_registry"]["entries"]["requirements"]["versions"][0]["registration"]["actor"]
        self.assertEqual(actor["principal_id"], "main-1")
        self.assertEqual(actor["authority"], "buzz-agent:local")

        confirmed = self.confirm(surface, root)
        record = collaboration.read_decisions(root)[1]["confirmations"][0]
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(record["evidence"]["user_principal_id"], "user-1")
        self.assertEqual(record["evidence"]["session_id"], "session-1")
        self.assertEqual(record["evidence"]["message_id"], "event-1")
        self.assertEqual(record["recorded_by"]["principal_id"], "main-1")
        self.assertFalse(confirmed["handoff_started"])

    def test_model_arguments_cannot_override_reserved_identity_fields(self):
        self.project()
        surface = host_tools.HostToolSurface(self.verified(), self.app)
        with self.assertRaisesRegex(ValueError, "宿主保留或未知字段"):
            surface.call("artifact.inspect", {"project_id": "other"})
        with self.assertRaisesRegex(ValueError, "宿主保留或未知字段"):
            surface.call("confirmation.confirm-current", {
                "user_principal_id": "forged-user", "role": "main",
            })

    def test_handoff_actions_remain_separate_and_recipient_is_host_bound(self):
        root = self.project()
        base_surface = host_tools.HostToolSurface(self.verified(), self.app)
        self.register(base_surface)
        confirmation = self.confirm(base_surface, root)

        recipient = {"principal_id": "solution-1", "authority": "buzz-agent:local"}
        prepare_payload = self.payload(
            event="handoff-event", recipient=recipient,
            tools=["handoff.prepare"], nonce="2" * 32,
        )
        prepare_context = self.verified(prepare_payload)
        prepare_surface = host_tools.HostToolSurface(prepare_context, self.app)
        prepared = prepare_surface.call("handoff.prepare", {
            "confirmation_ids": [confirmation["confirmation_id"]],
            "recipient_role": "solution", "purpose": "方案讨论",
            "allowed_actions": ["读取确认快照"],
            "expected_outputs": ["只读核验回执"],
            "execution_authorized": False,
        })
        self.assertEqual(prepared["status"], "prepared")
        self.assertFalse(prepared["downstream_started"])

        with self.assertRaisesRegex(ValueError, "宿主保留或未知字段"):
            prepare_surface.call("handoff.prepare", {
                "recipient_principal_id": "attacker",
            })

        sent_payload = self.payload(
            event="delivery-event", recipient=recipient,
            tools=["handoff.record-sent"], nonce="3" * 32,
            event_time="2026-09-20T12:01:00Z",
        )
        sent_surface = host_tools.HostToolSurface(self.verified(sent_payload), self.app)
        sent = sent_surface.call("handoff.record-sent", {"handoff_id": prepared["handoff_id"]})
        self.assertEqual(sent["status"], "sent")
        self.assertFalse(sent["downstream_started"])

        receipt_payload = self.payload(
            role="recipient", agent="solution-1", event="receipt-event",
            recipient=recipient, tools=["artifact.inspect", "collaboration.inspect",
                                        "handoff.verify-receipt"],
            nonce="4" * 32, event_time="2026-09-20T12:02:00Z",
        )
        receipt_context = self.verified(receipt_payload)
        receipt_surface = host_tools.HostToolSurface(
            receipt_context, self.app, coordinator_context=sent_surface.context
        )
        self.assertNotIn("handoff.prepare", receipt_surface.list_tools())
        received = receipt_surface.call("handoff.verify-receipt", {
            "handoff_id": prepared["handoff_id"],
            "observed_inputs": [[confirmation["confirmation_id"],
                                 confirmation["snapshot"]["sha256"]]],
            "goal_summary": "核对方案讨论输入",
            "scope_summary": "只读确认快照",
            "open_items_summary": "无阻塞未决项",
        })
        self.assertEqual(received["status"], "received-verified")
        self.assertFalse(received["downstream_started"])

    def test_wrong_recipient_cannot_submit_receipt(self):
        self.project()
        recipient = {"principal_id": "solution-1", "authority": "buzz-agent:local"}
        payload = self.payload(
            role="recipient", agent="other-worker", recipient=recipient,
            tools=["handoff.verify-receipt"],
        )
        context = self.verified(payload)
        import main_collaboration
        with self.assertRaisesRegex(PermissionError, "不是宿主指定接收者"):
            main_collaboration.receipt_from_host_context(
                context, handoff_id="H-" + "0" * 20,
                observed_inputs=(("C-" + "0" * 20, "0" * 64),),
                goal_summary="目标", scope_summary="范围", open_items_summary="无",
            )

    def test_plain_dictionary_is_not_a_trusted_context(self):
        with self.assertRaisesRegex(PermissionError, "已验签"):
            host_tools.HostToolSurface({"role": "main"}, self.app)

    def test_multiline_statement_verifies_and_inspects(self):
        self.project()
        statement = "@first-mate\nproject_id=just-start\n只检查当前宿主绑定。"
        context = self.verified(self.payload(statement=statement))
        self.assertEqual(context.statement, statement)
        surface = host_tools.HostToolSurface(context, self.app)
        inspected = surface.call("artifact.inspect", {})
        self.assertEqual(inspected["project_id"], "demo")
        collaboration_inspected = surface.call("collaboration.inspect", {})
        self.assertEqual(collaboration_inspected["project_id"], "demo")

    def test_statement_rejects_empty_and_nul_but_identity_stays_single_line(self):
        with self.assertRaisesRegex(ValueError, "statement 必须是非空文本"):
            self.verified(self.payload(statement="\n\n"))
        with self.assertRaisesRegex(ValueError, "statement 含有非法控制字符"):
            self.verified(self.payload(statement="ok\x00no"))
        with self.assertRaisesRegex(ValueError, "project_id 必须是非空单行文本"):
            self.verified(self.payload(project_id="demo\nother"))


if __name__ == "__main__":
    unittest.main()
