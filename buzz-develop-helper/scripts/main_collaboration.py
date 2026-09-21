"""Main-only confirmation, fixed snapshot, handoff, and receipt core.

There is no write CLI. Trusted host adapters must issue both Main authority and
runtime-bound evidence capabilities. Module privacy is not an OS sandbox.
"""

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

import artifacts
import collaboration
import main_artifacts
import trusted_context
from project_init import context as project_context, json_text, load_project
from project_state import (JOURNAL_NAME, atomic_replace, create_journal,
                           project_state_lock, read_journal, remove_journal)


TRANSACTION_SCHEMA_VERSION = 1
_EVIDENCE_SEAL = object()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return digest(raw)


def required_text(value, label):
    return collaboration.required_text(value, label)


def required_statement(value, label):
    return trusted_context.required_statement(value, label)


def valid_timestamp(value, label):
    if not isinstance(value, str) or not collaboration.TIMESTAMP_RE.fullmatch(value):
        raise ValueError(f"{label} 必须是 UTC ISO-8601 时间")
    return value


@dataclass(frozen=True)
class CurrentSessionConfirmation:
    project_id: str
    provider: str
    authority: str
    user_principal_id: str
    session_id: str
    message_id: str
    confirmed_at: str
    statement: str
    artifact_id: str
    version: str
    content_sha256: str
    permitted_use: str
    confirmed_scope: str
    non_authorizations: tuple
    blocking_open_items: tuple
    _seal: object

    def __post_init__(self):
        if self._seal is not _EVIDENCE_SEAL:
            raise PermissionError("当前会话确认依据必须由受信运行时签发")


@dataclass(frozen=True)
class CurrentSessionHandoff:
    project_id: str
    provider: str
    authority: str
    user_principal_id: str
    session_id: str
    message_id: str
    authorized_at: str
    statement: str
    confirmation_ids: tuple
    recipient_role: str
    recipient_principal_id: str
    recipient_authority: str
    purpose: str
    allowed_actions: tuple
    expected_outputs: tuple
    execution_authorized: bool
    _seal: object

    def __post_init__(self):
        if self._seal is not _EVIDENCE_SEAL:
            raise PermissionError("当前会话交接依据必须由受信运行时签发")


@dataclass(frozen=True)
class DeliveryEvidence:
    project_id: str
    handoff_id: str
    provider: str
    authority: str
    message_id: str
    sent_at: str
    recipient_principal_id: str
    _seal: object

    def __post_init__(self):
        if self._seal is not _EVIDENCE_SEAL:
            raise PermissionError("发送依据必须由受信运行时签发")


@dataclass(frozen=True)
class RecipientReceipt:
    project_id: str
    handoff_id: str
    principal_id: str
    authority: str
    received_at: str
    observed_inputs: tuple
    goal_summary: str
    scope_summary: str
    open_items_summary: str
    _seal: object

    def __post_init__(self):
        if self._seal is not _EVIDENCE_SEAL:
            raise PermissionError("接收回执必须由受信运行时签发")


def _issue_current_session_confirmation(*, runtime_verified=False, **values):
    """Internal host/test hook; never expose as an Agent command."""
    if runtime_verified is not True:
        raise PermissionError("运行时尚未认证当前用户会话")
    string_fields = (
        "project_id", "provider", "authority", "user_principal_id", "session_id",
        "message_id", "artifact_id", "version", "content_sha256",
        "permitted_use", "confirmed_scope",
    )
    for field in string_fields:
        values[field] = required_text(values.get(field), field)
    values["statement"] = required_statement(values.get("statement"), "statement")
    valid_timestamp(values.get("confirmed_at"), "confirmed_at")
    if not artifacts.SHA256_RE.fullmatch(values["content_sha256"]):
        raise ValueError("content_sha256 无效")
    for field in ("non_authorizations", "blocking_open_items"):
        items = values.get(field, ())
        if not isinstance(items, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in items):
            raise ValueError(f"{field} 必须是非空文本数组")
        values[field] = tuple(item.strip() for item in items)
    return CurrentSessionConfirmation(_seal=_EVIDENCE_SEAL, **values)


def _issue_current_session_handoff(*, runtime_verified=False, **values):
    """Internal host/test hook; never expose as an Agent command."""
    if runtime_verified is not True:
        raise PermissionError("运行时尚未认证交接授权会话")
    string_fields = (
        "project_id", "provider", "authority", "user_principal_id", "session_id",
        "message_id", "recipient_role", "recipient_principal_id",
        "recipient_authority", "purpose",
    )
    for field in string_fields:
        values[field] = required_text(values.get(field), field)
    values["statement"] = required_statement(values.get("statement"), "statement")
    valid_timestamp(values.get("authorized_at"), "authorized_at")
    for field in ("confirmation_ids", "allowed_actions", "expected_outputs"):
        items = values.get(field)
        if not isinstance(items, (list, tuple)) or not items or any(not isinstance(item, str) or not item.strip() for item in items):
            raise ValueError(f"{field} 必须是非空文本数组")
        values[field] = tuple(item.strip() for item in items)
    if not isinstance(values.get("execution_authorized"), bool):
        raise ValueError("execution_authorized 必须是布尔值")
    return CurrentSessionHandoff(_seal=_EVIDENCE_SEAL, **values)


def _issue_delivery_evidence(*, runtime_verified=False, **values):
    if runtime_verified is not True:
        raise PermissionError("运行时尚未认证发送结果")
    for field in ("project_id", "handoff_id", "provider", "authority",
                  "message_id", "recipient_principal_id"):
        values[field] = required_text(values.get(field), field)
    valid_timestamp(values.get("sent_at"), "sent_at")
    return DeliveryEvidence(_seal=_EVIDENCE_SEAL, **values)


def _issue_recipient_receipt(*, runtime_verified=False, **values):
    if runtime_verified is not True:
        raise PermissionError("运行时尚未认证接收者身份")
    for field in ("project_id", "handoff_id", "principal_id", "authority",
                  "goal_summary", "scope_summary", "open_items_summary"):
        values[field] = required_text(values.get(field), field)
    valid_timestamp(values.get("received_at"), "received_at")
    observed = values.get("observed_inputs")
    if not isinstance(observed, (list, tuple)) or not observed:
        raise ValueError("observed_inputs 必须是非空数组")
    normalized = []
    for item in observed:
        if (not isinstance(item, (list, tuple)) or len(item) != 2
                or not collaboration.CONFIRMATION_ID_RE.fullmatch(str(item[0]))
                or not artifacts.SHA256_RE.fullmatch(str(item[1]))):
            raise ValueError("observed_inputs 必须包含 confirmation_id 与 SHA-256")
        normalized.append((item[0], item[1]))
    values["observed_inputs"] = tuple(normalized)
    return RecipientReceipt(_seal=_EVIDENCE_SEAL, **values)


def _host_text_tuple(values, label, *, required=False):
    if not isinstance(values, (list, tuple)) or (required and not values):
        raise ValueError(f"{label} 必须是{'非空' if required else ''}文本数组")
    normalized = []
    for value in values:
        normalized.append(required_text(value, label))
    return tuple(normalized)


def confirmation_from_host_context(context, *, artifact_id, version,
                                   content_sha256, permitted_use,
                                   confirmed_scope, non_authorizations=(),
                                   blocking_open_items=()):
    context = trusted_context.require_verified(context)
    context.require_main()
    context.require_tool("confirmation.confirm-current")
    content_sha256 = required_text(content_sha256, "content_sha256")
    if not artifacts.SHA256_RE.fullmatch(content_sha256):
        raise ValueError("content_sha256 无效")
    return CurrentSessionConfirmation(
        project_id=context.project_id,
        provider=context.provider,
        authority=context.authority,
        user_principal_id=context.user_principal_id,
        session_id=context.session_id,
        message_id=context.message_id,
        confirmed_at=context.event_time,
        statement=context.statement,
        artifact_id=required_text(artifact_id, "artifact_id"),
        version=required_text(version, "version"),
        content_sha256=content_sha256,
        permitted_use=required_text(permitted_use, "permitted_use"),
        confirmed_scope=required_text(confirmed_scope, "confirmed_scope"),
        non_authorizations=_host_text_tuple(non_authorizations, "non_authorizations"),
        blocking_open_items=_host_text_tuple(blocking_open_items, "blocking_open_items"),
        _seal=_EVIDENCE_SEAL,
    )


def handoff_from_host_context(context, *, confirmation_ids, recipient_role,
                              purpose, allowed_actions, expected_outputs,
                              execution_authorized):
    context = trusted_context.require_verified(context)
    context.require_main()
    context.require_tool("handoff.prepare")
    if context.recipient is None:
        raise PermissionError("宿主事件没有绑定指定接收者")
    if not isinstance(execution_authorized, bool):
        raise ValueError("execution_authorized 必须是布尔值")
    return CurrentSessionHandoff(
        project_id=context.project_id,
        provider=context.provider,
        authority=context.authority,
        user_principal_id=context.user_principal_id,
        session_id=context.session_id,
        message_id=context.message_id,
        authorized_at=context.event_time,
        statement=context.statement,
        confirmation_ids=_host_text_tuple(confirmation_ids, "confirmation_ids", required=True),
        recipient_role=required_text(recipient_role, "recipient_role"),
        recipient_principal_id=context.recipient.principal_id,
        recipient_authority=context.recipient.authority,
        purpose=required_text(purpose, "purpose"),
        allowed_actions=_host_text_tuple(allowed_actions, "allowed_actions", required=True),
        expected_outputs=_host_text_tuple(expected_outputs, "expected_outputs", required=True),
        execution_authorized=execution_authorized,
        _seal=_EVIDENCE_SEAL,
    )


def delivery_from_host_context(context, *, handoff_id):
    context = trusted_context.require_verified(context)
    context.require_main()
    context.require_tool("handoff.record-sent")
    if context.recipient is None:
        raise PermissionError("宿主发送结果没有绑定指定接收者")
    return DeliveryEvidence(
        project_id=context.project_id,
        handoff_id=required_text(handoff_id, "handoff_id"),
        provider=context.provider,
        authority=context.authority,
        message_id=context.message_id,
        sent_at=context.event_time,
        recipient_principal_id=context.recipient.principal_id,
        _seal=_EVIDENCE_SEAL,
    )


def receipt_from_host_context(context, *, handoff_id, observed_inputs,
                              goal_summary, scope_summary, open_items_summary):
    context = trusted_context.require_verified(context)
    context.require_tool("handoff.verify-receipt")
    if context.agent_role != "recipient":
        raise PermissionError("只有宿主绑定的指定接收者可提交核验回执")
    if context.recipient is None or (
        context.agent_principal_id,
        context.agent_authority,
    ) != (context.recipient.principal_id, context.recipient.authority):
        raise PermissionError("当前 Agent principal 不是宿主指定接收者")
    if not isinstance(observed_inputs, (list, tuple)) or not observed_inputs:
        raise ValueError("observed_inputs 必须是非空数组")
    normalized_inputs = []
    for item in observed_inputs:
        if (not isinstance(item, (list, tuple)) or len(item) != 2
                or not collaboration.CONFIRMATION_ID_RE.fullmatch(str(item[0]))
                or not artifacts.SHA256_RE.fullmatch(str(item[1]))):
            raise ValueError("observed_inputs 必须包含 confirmation_id 与 SHA-256")
        normalized_inputs.append((item[0], item[1]))
    return RecipientReceipt(
        project_id=context.project_id,
        handoff_id=required_text(handoff_id, "handoff_id"),
        principal_id=context.agent_principal_id,
        authority=context.agent_authority,
        received_at=context.event_time,
        observed_inputs=tuple(normalized_inputs),
        goal_summary=required_text(goal_summary, "goal_summary"),
        scope_summary=required_text(scope_summary, "scope_summary"),
        open_items_summary=required_text(open_items_summary, "open_items_summary"),
        _seal=_EVIDENCE_SEAL,
    )


def require_evidence(value, expected_type, project_id):
    if not isinstance(value, expected_type) or value._seal is not _EVIDENCE_SEAL:
        raise PermissionError("操作依据必须由受信运行时签发")
    if value.project_id != project_id:
        raise PermissionError("操作依据未绑定当前项目")


def _safe_relative(relative):
    candidate = Path(relative)
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts)):
        raise ValueError("事务路径必须是项目内规范相对路径")
    return candidate


def _ensure_parent(root, relative):
    candidate = _safe_relative(relative)
    current = root
    for part in candidate.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError("不允许通过软链创建记录目录")
        if current.exists() and not current.is_dir():
            raise ValueError("记录目录路径被非目录占用")
        current.mkdir(exist_ok=True)
    return root / candidate


def _read_optional(root, relative):
    path = root / _safe_relative(relative)
    if path.is_symlink():
        raise ValueError(f"事务目标不能是软链：{relative}")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"事务目标不是独立普通文件：{relative}")
    return path.read_bytes()


def _immutable_write(root, relative, raw):
    path = _ensure_parent(root, relative)
    if path.exists() or path.is_symlink():
        existing = _read_optional(root, relative)
        if existing is None or existing != raw:
            raise ValueError(f"固定快照路径已被不同内容占用：{relative}")
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=f".{path.name}-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = _read_optional(root, relative)
            if existing != raw:
                raise ValueError(f"固定快照并发冲突：{relative}")
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _snapshot(root, content):
    if content["type"] == "file":
        source = content["path"]
        raw = (root / source).read_bytes()
        if digest(raw) != content["sha256"]:
            raise ValueError("确认前成果内容已改变")
        relative = f"docs/confirmations/snapshots/{content['sha256']}/{Path(source).name}"
        _immutable_write(root, relative, raw)
        return {"type": "file", "source_path": source, "path": relative,
                "sha256": content["sha256"], "size": len(raw)}
    manifest = content["manifest"]
    manifest_raw = (root / manifest["path"]).read_bytes()
    if digest(manifest_raw) != manifest["sha256"]:
        raise ValueError("确认前成果清单已改变")
    base = f"docs/confirmations/snapshots/{manifest['sha256']}"
    manifest_path = f"{base}/{Path(manifest['path']).name}"
    _immutable_write(root, manifest_path, manifest_raw)
    files = []
    for member in content["files"]:
        raw = (root / member["path"]).read_bytes()
        if digest(raw) != member["sha256"]:
            raise ValueError(f"确认前集合成员已改变：{member['path']}")
        destination = f"{base}/files/{member['path']}"
        _immutable_write(root, destination, raw)
        files.append({"source_path": member["path"], "snapshot_path": destination,
                      "sha256": member["sha256"], "size": len(raw)})
    return {"type": "file-set", "source_manifest_path": manifest["path"],
            "manifest_path": manifest_path, "manifest_sha256": manifest["sha256"],
            "entrypoint": content["entrypoint"], "files": files}


def _file_record(before, after):
    return {
        "before_exists": before is not None,
        "before_sha256": digest(before) if before is not None else None,
        "before_base64": base64.b64encode(before).decode("ascii") if before is not None else None,
        "after_sha256": digest(after),
        "after_base64": base64.b64encode(after).decode("ascii"),
    }


def _decode(record, before=False):
    field = "before_base64" if before else "after_base64"
    sha_field = "before_sha256" if before else "after_sha256"
    if before and record.get("before_exists") is False:
        return None
    try:
        raw = base64.b64decode(record[field], validate=True)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("协作事务包含无效文件快照") from error
    if digest(raw) != record.get(sha_field):
        raise ValueError("协作事务文件快照摘要不匹配")
    return raw


def _transaction(operation, project_id, authorization, files):
    return {
        "schema_version": TRANSACTION_SCHEMA_VERSION,
        "type": "collaboration-update",
        "operation": operation,
        "transaction_id": uuid.uuid4().hex,
        "project_id": project_id,
        "prepared_at": main_artifacts.utc_now(),
        "actor": authorization.actor(),
        "files": {relative: _file_record(before, after)
                  for relative, (before, after) in files.items()},
    }


def _validate_transaction(value, project_id):
    if (not isinstance(value, dict) or value.get("schema_version") != TRANSACTION_SCHEMA_VERSION
            or value.get("type") != "collaboration-update" or value.get("project_id") != project_id
            or value.get("operation") not in {"confirmation", "handoff-prepare", "handoff-sent", "handoff-receipt"}
            or not re.fullmatch(r"[0-9a-f]{32}", str(value.get("transaction_id", "")))
            or not isinstance(value.get("files"), dict) or not value["files"]):
        raise ValueError("协作恢复事务格式或项目身份不匹配")
    collaboration.validate_actor(value.get("actor"), "事务 Main")
    for relative, record in value["files"].items():
        _safe_relative(relative)
        if not isinstance(record, dict):
            raise ValueError("协作事务文件记录无效")
        _decode(record, before=True)
        _decode(record, before=False)
    return value


def _write_transaction(root, transaction, failure_hook=None):
    journal = create_journal(root, transaction)
    for relative, record in transaction["files"].items():
        current = _read_optional(root, relative)
        after = _decode(record)
        if current == after:
            continue
        before = _decode(record, before=True)
        if current != before:
            raise RuntimeError(f"协作事务写入冲突：{relative} 在替换前发生变化")
        path = _ensure_parent(root, relative)
        atomic_replace(path, after)
        if failure_hook is not None:
            failure_hook(f"after:{relative}")
    for relative, record in transaction["files"].items():
        if digest(_read_optional(root, relative)) != record["after_sha256"]:
            raise RuntimeError(f"协作事务写入后摘要不匹配：{relative}")
    return journal


def confirmation_preconditions(foundation, project_id):
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    _, _, decisions_sha = collaboration.read_decisions(root)
    return {"expected_project_sha256": digest((root / "project.json").read_bytes()),
            "expected_readme_sha256": digest((root / "README.md").read_bytes()),
            "expected_decisions_sha256": decisions_sha}


def confirm_current_session(authorization, evidence, foundation, project_id, *,
                            expected_project_sha256, expected_readme_sha256,
                            expected_decisions_sha256, _failure_hook=None):
    main_artifacts.require_authorization(authorization, project_id)
    require_evidence(evidence, CurrentSessionConfirmation, project_id)
    if evidence.blocking_open_items:
        raise ValueError("当前用途仍有阻塞未决项，不能正式确认")
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    with project_state_lock(root, "current-session-confirmation"):
        if (root / JOURNAL_NAME).exists() or (root / JOURNAL_NAME).is_symlink():
            raise ValueError("存在未完成事务；先由 Main 恢复")
        before_project = (root / "project.json").read_bytes()
        before_readme = (root / "README.md").read_bytes()
        decisions_text, decisions, decisions_sha = collaboration.read_decisions(root)
        if digest(before_project) != expected_project_sha256 or digest(before_readme) != expected_readme_sha256:
            raise ValueError("项目入口乐观摘要冲突；重新展示确认对象")
        if decisions_sha != expected_decisions_sha256:
            raise ValueError("确认记录乐观摘要冲突；重新读取")
        data = json.loads(before_project.decode("utf-8"))
        registry, _ = artifacts.validate_registry(root, data)
        entry, version = collaboration.artifact_version(registry, evidence.artifact_id, evidence.version)
        actual_sha = collaboration.content_sha(version["content"])
        if actual_sha != evidence.content_sha256:
            raise ValueError("当前会话展示版本与已登记成果摘要不一致")
        identity = {
            "project_id": project_id, "provider": evidence.provider,
            "authority": evidence.authority, "session_id": evidence.session_id,
            "message_id": evidence.message_id, "artifact_id": evidence.artifact_id,
            "version": evidence.version, "content_sha256": actual_sha,
            "permitted_use": evidence.permitted_use,
        }
        confirmation_id = "C-" + canonical_digest(identity)[:20]
        existing = collaboration.confirmation_map(decisions).get(confirmation_id)
        if existing is not None:
            evidence_record = existing.get("evidence", {})
            if (
                existing.get("project_id") != project_id
                or existing.get("artifact", {}).get("artifact_id") != evidence.artifact_id
                or existing.get("artifact", {}).get("version") != evidence.version
                or existing.get("artifact", {}).get("content_sha256") != actual_sha
                or existing.get("permitted_use") != evidence.permitted_use
                or existing.get("confirmed_scope") != evidence.confirmed_scope
                or existing.get("non_authorizations") != list(evidence.non_authorizations)
                or evidence_record.get("authority") != evidence.authority
                or evidence_record.get("session_id") != evidence.session_id
                or evidence_record.get("message_id") != evidence.message_id
            ):
                raise ValueError("相同确认依据已绑定不同记录")
            record = existing
            snapshot = existing["snapshot"]
            collaboration.validate_snapshot(root, existing)
        else:
            source_path = artifacts.content_path(version["content"])
            snapshot = _snapshot(root, version["content"])
            record = {
                "schema_version": collaboration.SCHEMA_VERSION,
                "confirmation_id": confirmation_id,
                "project_id": project_id,
                "status": "active",
                "artifact": {"artifact_id": evidence.artifact_id, "kind": entry["kind"],
                             "version": evidence.version, "content_sha256": actual_sha,
                             "registered_path": source_path},
                "snapshot": snapshot,
                "permitted_use": evidence.permitted_use,
                "confirmed_scope": evidence.confirmed_scope,
                "non_authorizations": list(evidence.non_authorizations),
                "open_items": json.loads(json.dumps(version["open_items"])),
                "evidence": {"type": "current-session", "provider": evidence.provider,
                             "authority": evidence.authority,
                             "user_principal_id": evidence.user_principal_id,
                             "session_id": evidence.session_id, "message_id": evidence.message_id,
                             "confirmed_at": evidence.confirmed_at,
                             "statement": evidence.statement, "runtime_authenticated": True},
                "recorded_by": authorization.actor(),
                "recorded_at": main_artifacts.utc_now(),
            }
            decisions["confirmations"].append(record)
        if version["content"]["type"] == "file":
            version["content"] = {
                "type": "file", "path": snapshot["path"],
                "sha256": snapshot["sha256"], "size": snapshot["size"],
            }
            if entry.get("current_version") == evidence.version:
                data["artifacts"][entry["kind"]] = snapshot["path"]
        if confirmation_id not in version["confirmation_ids"]:
            version["confirmation_ids"].append(confirmation_id)
        data["artifacts"]["decisions"] = collaboration.DECISIONS_PATH
        artifacts.validate_registry(root, data)
        after_project = json_text(data).encode("utf-8")
        after_readme = artifacts.preview_readme(before_readme.decode("utf-8"), data["artifact_registry"])["proposed_content"].encode("utf-8")
        after_decisions = collaboration.render_decisions(decisions_text, decisions).encode("utf-8")
        before_decisions = None if decisions_sha == "missing" else decisions_text.encode("utf-8")
        files = {
            collaboration.DECISIONS_PATH: (before_decisions, after_decisions),
            "project.json": (before_project, after_project),
            "README.md": (before_readme, after_readme),
        }
        if all(before == after for before, after in files.values()):
            return {"status": "unchanged", "confirmation_id": confirmation_id,
                    "snapshot": snapshot, "document_status_changed": False,
                    "handoff_started": False}
        transaction = _transaction("confirmation", project_id, authorization, files)
        journal = _write_transaction(root, transaction, _failure_hook)
        result = collaboration.inspect(foundation, project_id)
        if result["status"] != "consistent":
            raise RuntimeError("确认写入完成但一致性检查未通过")
        remove_journal(journal)
        return {"status": "confirmed", "confirmation_id": confirmation_id,
                "transaction_id": transaction["transaction_id"], "snapshot": snapshot,
                "document_status_changed": False, "handoff_started": False,
                "project_json_sha256": result["project_json_sha256"],
                "readme_sha256": result["readme_sha256"],
                "decisions_sha256": result["decisions_sha256"]}


def prepare_handoff(authorization, evidence, foundation, project_id, *,
                    expected_decisions_sha256, _failure_hook=None):
    main_artifacts.require_authorization(authorization, project_id)
    require_evidence(evidence, CurrentSessionHandoff, project_id)
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    with project_state_lock(root, "handoff-prepare"):
        if (root / JOURNAL_NAME).exists() or (root / JOURNAL_NAME).is_symlink():
            raise ValueError("存在未完成事务；先由 Main 恢复")
        _, decisions, decisions_sha = collaboration.read_decisions(root)
        if decisions_sha != expected_decisions_sha256:
            raise ValueError("确认记录乐观摘要冲突；重新读取")
        confirmations = collaboration.confirmation_map(decisions)
        inputs = []
        for confirmation_id in evidence.confirmation_ids:
            record = confirmations.get(confirmation_id)
            if record is None or record["status"] != "active":
                raise ValueError(f"交接引用不存在或无效：{confirmation_id}")
            if record["permitted_use"] != evidence.purpose:
                raise ValueError(f"交接用途超出确认范围：{confirmation_id}")
            inputs.append({"confirmation_id": confirmation_id,
                           "artifact": record["artifact"],
                           "snapshot": record["snapshot"],
                           "content_sha256": record["artifact"]["content_sha256"],
                           "open_items": record["open_items"]})
        identity = {"project_id": project_id, "provider": evidence.provider,
                    "authority": evidence.authority, "session_id": evidence.session_id,
                    "message_id": evidence.message_id,
                    "confirmation_ids": list(evidence.confirmation_ids),
                    "recipient": evidence.recipient_principal_id, "purpose": evidence.purpose}
        handoff_id = "H-" + canonical_digest(identity)[:20]
        record = {
            "schema_version": collaboration.SCHEMA_VERSION,
            "handoff_id": handoff_id, "project_id": project_id, "status": "prepared",
            "prepared_at": main_artifacts.utc_now(), "prepared_by": authorization.actor(),
            "authorization_evidence": {"type": "current-session", "provider": evidence.provider,
                                       "authority": evidence.authority,
                                       "user_principal_id": evidence.user_principal_id,
                                       "session_id": evidence.session_id,
                                       "message_id": evidence.message_id,
                                       "authorized_at": evidence.authorized_at,
                                       "statement": evidence.statement,
                                       "runtime_authenticated": True},
            "recipient": {"role": evidence.recipient_role,
                          "principal_id": evidence.recipient_principal_id,
                          "authority": evidence.recipient_authority},
            "purpose": evidence.purpose,
            "allowed_actions": list(evidence.allowed_actions),
            "expected_outputs": list(evidence.expected_outputs),
            "execution_authorized": evidence.execution_authorized,
            "inputs": inputs, "delivery": None, "receipt": None,
            "downstream_started": False,
        }
        relative = f"{collaboration.HANDOFFS_DIRECTORY}/{handoff_id}.json"
        before = _read_optional(root, relative)
        after = json_text(record).encode("utf-8")
        if before is not None:
            try:
                persisted = json.loads(before.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("已有交接记录 JSON 无效") from error
            stable_fields = (
                "handoff_id", "project_id", "prepared_by", "authorization_evidence",
                "recipient", "purpose", "allowed_actions", "expected_outputs",
                "execution_authorized", "inputs",
            )
            if any(persisted.get(field) != record.get(field) for field in stable_fields):
                raise ValueError("相同交接依据已生成不同记录")
            return {"status": "unchanged", "handoff_id": handoff_id,
                    "delivery_status": persisted.get("status"), "downstream_started": False}
        transaction = _transaction("handoff-prepare", project_id, authorization,
                                   {relative: (None, after)})
        journal = _write_transaction(root, transaction, _failure_hook)
        result = collaboration.inspect(foundation, project_id)
        if result["status"] != "consistent":
            raise RuntimeError("交接准备完成但一致性检查未通过")
        remove_journal(journal)
        return {"status": "prepared", "handoff_id": handoff_id,
                "transaction_id": transaction["transaction_id"],
                "delivery_status": "prepared", "downstream_started": False}


def _read_handoff(root, handoff_id):
    if not collaboration.HANDOFF_ID_RE.fullmatch(handoff_id):
        raise ValueError("handoff_id 无效")
    relative = f"{collaboration.HANDOFFS_DIRECTORY}/{handoff_id}.json"
    raw = _read_optional(root, relative)
    if raw is None:
        raise ValueError("交接记录不存在")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("交接记录 JSON 无效") from error
    return relative, raw, record


def record_handoff_sent(authorization, evidence, foundation, project_id, *,
                        expected_handoff_sha256):
    main_artifacts.require_authorization(authorization, project_id)
    require_evidence(evidence, DeliveryEvidence, project_id)
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    with project_state_lock(root, "handoff-sent"):
        if (root / JOURNAL_NAME).exists() or (root / JOURNAL_NAME).is_symlink():
            raise ValueError("存在未完成事务；先由 Main 恢复")
        relative, before, record = _read_handoff(root, evidence.handoff_id)
        if digest(before) != expected_handoff_sha256:
            raise ValueError("交接记录乐观摘要冲突；重新读取")
        if record["recipient"]["principal_id"] != evidence.recipient_principal_id:
            raise PermissionError("发送依据接收者与交接目标不匹配")
        delivery = {"provider": evidence.provider, "authority": evidence.authority,
                    "message_id": evidence.message_id, "sent_at": evidence.sent_at,
                    "recipient_principal_id": evidence.recipient_principal_id,
                    "runtime_verified": True}
        if record["status"] == "received-verified":
            if record["delivery"] == delivery:
                return {"status": "unchanged", "handoff_id": evidence.handoff_id,
                        "delivery_status": "received-verified", "downstream_started": False}
            raise ValueError("已完成接收核验的交接不能重写发送状态")
        if record["delivery"] is not None and record["delivery"] != delivery:
            raise ValueError("交接已绑定不同发送依据")
        record["delivery"] = delivery
        record["status"] = "sent"
        after = json_text(record).encode("utf-8")
        if after == before:
            return {"status": "unchanged", "handoff_id": evidence.handoff_id,
                    "downstream_started": False}
        transaction = _transaction("handoff-sent", project_id, authorization,
                                   {relative: (before, after)})
        journal = _write_transaction(root, transaction)
        result = collaboration.inspect(foundation, project_id)
        if result["status"] != "consistent":
            raise RuntimeError("交接发送记录一致性检查未通过")
        remove_journal(journal)
        return {"status": "sent", "handoff_id": evidence.handoff_id,
                "transaction_id": transaction["transaction_id"],
                "downstream_started": False}


def record_handoff_receipt(authorization, receipt, foundation, project_id, *,
                           expected_handoff_sha256):
    main_artifacts.require_authorization(authorization, project_id)
    require_evidence(receipt, RecipientReceipt, project_id)
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    with project_state_lock(root, "handoff-receipt"):
        if (root / JOURNAL_NAME).exists() or (root / JOURNAL_NAME).is_symlink():
            raise ValueError("存在未完成事务；先由 Main 恢复")
        relative, before, record = _read_handoff(root, receipt.handoff_id)
        if digest(before) != expected_handoff_sha256:
            raise ValueError("交接记录乐观摘要冲突；重新读取")
        recipient = record["recipient"]
        if (receipt.principal_id, receipt.authority) != (recipient["principal_id"], recipient["authority"]):
            raise PermissionError("接收回执身份与指定接收者不匹配")
        expected = {(item["confirmation_id"], item["content_sha256"])
                    for item in record["inputs"]}
        if set(receipt.observed_inputs) != expected:
            raise ValueError("接收回执读取的输入版本与交接记录不一致")
        receipt_record = {
            "principal_id": receipt.principal_id, "authority": receipt.authority,
            "received_at": receipt.received_at,
            "observed_inputs": [{"confirmation_id": item[0], "content_sha256": item[1]}
                                for item in receipt.observed_inputs],
            "goal_summary": receipt.goal_summary,
            "scope_summary": receipt.scope_summary,
            "open_items_summary": receipt.open_items_summary,
            "runtime_authenticated": True,
        }
        if record["status"] == "received-verified":
            if record.get("receipt") == receipt_record:
                return {"status": "unchanged", "handoff_id": receipt.handoff_id,
                        "execution_authorized": record["execution_authorized"],
                        "downstream_started": False}
            raise ValueError("交接已绑定不同接收回执")
        if record["status"] != "sent":
            raise ValueError("交接尚未记录为已发送")
        record["receipt"] = receipt_record
        record["status"] = "received-verified"
        after = json_text(record).encode("utf-8")
        transaction = _transaction("handoff-receipt", project_id, authorization,
                                   {relative: (before, after)})
        journal = _write_transaction(root, transaction)
        result = collaboration.inspect(foundation, project_id)
        if result["status"] != "consistent":
            raise RuntimeError("交接接收回执一致性检查未通过")
        remove_journal(journal)
        return {"status": "received-verified", "handoff_id": receipt.handoff_id,
                "transaction_id": transaction["transaction_id"],
                "execution_authorized": record["execution_authorized"],
                "downstream_started": False}


def recover_collaboration(authorization, foundation, project_id):
    main_artifacts.require_authorization(authorization, project_id)
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    with project_state_lock(root, "collaboration-recover"):
        journal_path, raw = read_journal(root)
        transaction = _validate_transaction(raw, project_id)
        recovered, already_complete = [], []
        for relative, record in transaction["files"].items():
            current = _read_optional(root, relative)
            after = _decode(record)
            if current == after:
                already_complete.append(relative)
                continue
            before = _decode(record, before=True)
            if current != before:
                raise ValueError(f"恢复冲突：{relative} 已被事务外修改；不覆盖")
            atomic_replace(_ensure_parent(root, relative), after)
            recovered.append(relative)
        result = collaboration.inspect(foundation, project_id)
        if result["status"] != "consistent":
            raise RuntimeError("协作事务恢复后一致性检查未通过")
        remove_journal(journal_path)
        return {"status": "recovered", "operation": transaction["operation"],
                "transaction_id": transaction["transaction_id"],
                "recovered_files": recovered,
                "already_complete_files": already_complete}


if __name__ == "__main__":
    print(json.dumps({"status": "fail",
                      "error": "确认与交接写入内核没有 CLI；必须由受信宿主调用"},
                     ensure_ascii=False), file=sys.stderr)
    sys.exit(2)
