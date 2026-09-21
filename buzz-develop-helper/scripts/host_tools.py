"""Host-bound tool surface for artifact registration and collaboration.

An adapter instance is created for one already-verified Buzz turn.  Identity
and routing fields never appear in model-controlled arguments; they come only
from ``TrustedEventContext``.  The available tool list is also derived from the
signed role binding, so workers never receive Main mutation functions.
"""

import hashlib
import json

import artifacts
import collaboration
import main_artifacts
import main_collaboration
import requirements
import trusted_context
from project_init import context as project_context


IMPLEMENTED_TOOLS = frozenset({
    "requirements.context",
    "requirements.save-draft",
    "artifact.inspect",
    "artifact.preview-register",
    "artifact.register",
    "collaboration.inspect",
    "confirmation.confirm-current",
    "handoff.prepare",
    "handoff.record-sent",
    "handoff.verify-receipt",
})


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _arguments(arguments, allowed):
    if not isinstance(arguments, dict):
        raise ValueError("工具参数必须是对象")
    unknown = set(arguments) - set(allowed)
    if unknown:
        raise ValueError("工具参数包含宿主保留或未知字段：" + ", ".join(sorted(unknown)))
    return arguments


class HostToolSurface:
    def __init__(self, caller_context, foundation, *, coordinator_context=None):
        self.context = trusted_context.require_verified(caller_context)
        self.foundation = foundation
        self.coordinator = None
        if coordinator_context is not None:
            self.coordinator = trusted_context.require_verified(coordinator_context)
            self.coordinator.require_main()
            if self.coordinator.project_id != self.context.project_id:
                raise PermissionError("接收回执协调者与调用者项目不匹配")

    def list_tools(self):
        return sorted(self.context.tools & IMPLEMENTED_TOOLS)

    def call(self, tool_name, arguments=None):
        self.context.require_tool(tool_name)
        if tool_name not in IMPLEMENTED_TOOLS:
            raise ValueError(f"工具尚未实现：{tool_name}")
        args = {} if arguments is None else arguments
        dispatch = {
            "requirements.context": self._requirements_context,
            "requirements.save-draft": self._requirements_save,
            "artifact.inspect": self._artifact_inspect,
            "artifact.preview-register": self._artifact_preview,
            "artifact.register": self._artifact_register,
            "collaboration.inspect": self._collaboration_inspect,
            "confirmation.confirm-current": self._confirm,
            "handoff.prepare": self._handoff_prepare,
            "handoff.record-sent": self._handoff_sent,
            "handoff.verify-receipt": self._handoff_receipt,
        }
        return dispatch[tool_name](args)

    def _requirements_context(self, arguments):
        _arguments(arguments, ())
        return requirements.context(self.foundation, self.context.project_id)

    def _requirements_save(self, arguments):
        args = _arguments(arguments, ("content", "expected_sha256"))
        return requirements.save_draft(
            self.foundation,
            self.context.project_id,
            args.get("content"),
            args.get("expected_sha256"),
        )

    def _artifact_inspect(self, arguments):
        _arguments(arguments, ())
        return artifacts.inspect(self.foundation, self.context.project_id)

    def _artifact_preview(self, arguments):
        args = _arguments(arguments, (
            "artifact_id", "kind", "version", "producer_role", "purpose",
            "summary", "path", "manifest", "set_current",
        ))
        return artifacts.preview_register(self.foundation, self.context.project_id, **args)

    def _main_authorization(self):
        self.context.require_main()
        return main_artifacts.authorization_from_host_context(self.context)

    def _coordinator_authorization(self):
        if self.coordinator is None:
            raise PermissionError("指定接收者回执缺少宿主绑定的 Main 协调者")
        return main_artifacts.authorization_from_host_context(self.coordinator)

    def _artifact_register(self, arguments):
        args = _arguments(arguments, (
            "artifact_id", "kind", "version", "producer_role", "purpose",
            "summary", "path", "manifest", "set_current",
        ))
        preview = artifacts.preview_register(self.foundation, self.context.project_id, **args)
        return main_artifacts.apply_registration(
            self._main_authorization(), self.foundation, self.context.project_id,
            expected_project_sha256=preview["project_json_precondition"]["sha256"],
            expected_readme_sha256=preview["proposed_changes"]["readme"]["before_sha256"],
            **args,
        )

    def _collaboration_inspect(self, arguments):
        _arguments(arguments, ())
        return collaboration.inspect(self.foundation, self.context.project_id)

    def _confirm(self, arguments):
        args = _arguments(arguments, (
            "artifact_id", "version", "content_sha256", "permitted_use",
            "confirmed_scope", "non_authorizations", "blocking_open_items",
        ))
        evidence = main_collaboration.confirmation_from_host_context(self.context, **args)
        preconditions = main_collaboration.confirmation_preconditions(
            self.foundation, self.context.project_id
        )
        return main_collaboration.confirm_current_session(
            self._main_authorization(), evidence, self.foundation,
            self.context.project_id, **preconditions,
        )

    def _handoff_prepare(self, arguments):
        args = _arguments(arguments, (
            "confirmation_ids", "recipient_role", "purpose", "allowed_actions",
            "expected_outputs", "execution_authorized",
        ))
        evidence = main_collaboration.handoff_from_host_context(self.context, **args)
        _, root = project_context(self.foundation, self.context.project_id)
        decisions_sha = collaboration.read_decisions(root)[2]
        return main_collaboration.prepare_handoff(
            self._main_authorization(), evidence, self.foundation,
            self.context.project_id, expected_decisions_sha256=decisions_sha,
        )

    def _handoff_sent(self, arguments):
        args = _arguments(arguments, ("handoff_id",))
        evidence = main_collaboration.delivery_from_host_context(
            self.context, handoff_id=args.get("handoff_id")
        )
        _, root = project_context(self.foundation, self.context.project_id)
        path = root / f"{collaboration.HANDOFFS_DIRECTORY}/{evidence.handoff_id}.json"
        return main_collaboration.record_handoff_sent(
            self._main_authorization(), evidence, self.foundation,
            self.context.project_id,
            expected_handoff_sha256=digest(path.read_bytes()),
        )

    def _handoff_receipt(self, arguments):
        args = _arguments(arguments, (
            "handoff_id", "observed_inputs", "goal_summary", "scope_summary",
            "open_items_summary",
        ))
        receipt = main_collaboration.receipt_from_host_context(self.context, **args)
        _, root = project_context(self.foundation, self.context.project_id)
        path = root / f"{collaboration.HANDOFFS_DIRECTORY}/{receipt.handoff_id}.json"
        return main_collaboration.record_handoff_receipt(
            self._coordinator_authorization(), receipt, self.foundation,
            self.context.project_id,
            expected_handoff_sha256=digest(path.read_bytes()),
        )
