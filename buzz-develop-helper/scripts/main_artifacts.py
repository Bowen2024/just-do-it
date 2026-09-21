"""Main-only artifact registry mutation core.

There is deliberately no write CLI. A trusted host adapter must issue the
MainAuthorization capability and call these functions. Python module privacy is
not an OS sandbox; unrestricted shells remain outside this tool boundary.
"""

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

import artifacts
import trusted_context
from project_init import context as project_context, json_text, load_project
from project_state import (JOURNAL_NAME, atomic_replace, create_journal,
                           project_state_lock, read_journal, remove_journal)


TRANSACTION_SCHEMA_VERSION = 1
_AUTHORIZATION_SEAL = object()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_identity(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} 必须是非空单行文本")
    return value.strip()


@dataclass(frozen=True)
class MainAuthorization:
    principal_id: str
    authority: str
    project_ids: frozenset
    _seal: object

    def __post_init__(self):
        if self._seal is not _AUTHORIZATION_SEAL:
            raise PermissionError("Main capability 必须由受信运行时签发")
        _required_identity(self.principal_id, "Main principal_id")
        _required_identity(self.authority, "Main authority")
        if not isinstance(self.project_ids, frozenset) or not self.project_ids:
            raise ValueError("Main capability 必须绑定至少一个项目")

    def require_project(self, project_id):
        if project_id not in self.project_ids:
            raise PermissionError("Main capability 未授权当前项目")

    def actor(self):
        return {"role": "main", "principal_id": self.principal_id,
                "authority": self.authority}


def _issue_runtime_main(principal_id, authority, project_ids, runtime_verified=False):
    """Internal host-adapter hook; never expose as an Agent or user command."""
    if runtime_verified is not True:
        raise PermissionError("运行时尚未验证 Main 身份")
    if not isinstance(project_ids, (set, frozenset, tuple, list)):
        raise ValueError("项目授权集合格式无效")
    return MainAuthorization(
        _required_identity(principal_id, "Main principal_id"),
        _required_identity(authority, "Main authority"),
        frozenset(project_ids),
        _AUTHORIZATION_SEAL,
    )


def authorization_from_host_context(context):
    """Production adapter path from a verified Buzz host turn.

    Unlike ``_issue_runtime_main`` this entry does not accept identity fields or
    a caller-provided verification boolean.  All identity and project claims
    come from the already-verified host envelope.
    """
    context = trusted_context.require_verified(context)
    context.require_main()
    return MainAuthorization(
        context.agent_principal_id,
        context.agent_authority,
        frozenset({context.project_id}),
        _AUTHORIZATION_SEAL,
    )


def require_authorization(authorization, project_id):
    if not isinstance(authorization, MainAuthorization) or authorization._seal is not _AUTHORIZATION_SEAL:
        raise PermissionError("写入只接受受信运行时签发的 Main capability")
    authorization.require_project(project_id)


def materialize_registration(registry, artifact_id, version, authorization, recorded_at):
    rendered = json.loads(json.dumps(registry))
    entry = rendered["entries"][artifact_id]
    target = next(item for item in entry["versions"] if item["version"] == version)
    registration = target.get("registration")
    principal = registration.get("actor", {}).get("principal_id") if isinstance(registration, dict) else None
    if isinstance(principal, str) and principal.startswith("<"):
        target["registration"] = {
            "actor": authorization.actor(),
            "recorded_at": recorded_at,
        }
    return rendered


def encode_file(before, after):
    return {
        "before_sha256": digest(before),
        "after_sha256": digest(after),
        "before_base64": base64.b64encode(before).decode("ascii"),
        "after_base64": base64.b64encode(after).decode("ascii"),
    }


def decode_snapshot(record, field):
    try:
        raw = base64.b64decode(record[field], validate=True)
        expected = record["before_sha256" if field == "before_base64" else "after_sha256"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("恢复事务包含无效文件快照") from error
    if digest(raw) != expected:
        raise ValueError("恢复事务文件快照摘要不匹配")
    return raw


def build_transaction(project_id, authorization, before_project, after_project,
                      before_readme, after_readme):
    return {
        "schema_version": TRANSACTION_SCHEMA_VERSION,
        "type": "artifact-registry-update",
        "transaction_id": uuid.uuid4().hex,
        "project_id": project_id,
        "prepared_at": utc_now(),
        "actor": authorization.actor(),
        "files": {
            "project.json": encode_file(before_project, after_project),
            "README.md": encode_file(before_readme, after_readme),
        },
    }


def validate_transaction(value, project_id):
    files = value.get("files") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != TRANSACTION_SCHEMA_VERSION
        or value.get("type") != "artifact-registry-update"
        or value.get("project_id") != project_id
        or not re.fullmatch(r"[0-9a-f]{32}", str(value.get("transaction_id", "")))
        or not isinstance(files, dict)
        or set(files) != {"project.json", "README.md"}
    ):
        raise ValueError("恢复事务格式或项目身份不匹配")
    actor = value.get("actor")
    if not isinstance(actor, dict) or actor.get("role") != "main":
        raise ValueError("恢复事务缺少原 Main 身份")
    _required_identity(actor.get("principal_id"), "事务 Main principal_id")
    _required_identity(actor.get("authority"), "事务 Main authority")
    for record in files.values():
        if not isinstance(record, dict):
            raise ValueError("恢复事务文件记录无效")
        decode_snapshot(record, "before_base64")
        decode_snapshot(record, "after_base64")
    return value


def _write_transaction(root, transaction, failure_hook=None):
    journal = create_journal(root, transaction)
    files = transaction["files"]
    if digest((root / "project.json").read_bytes()) != files["project.json"]["before_sha256"]:
        raise RuntimeError("事务写入冲突：project.json 在替换前发生变化")
    atomic_replace(root / "project.json", decode_snapshot(files["project.json"], "after_base64"))
    if failure_hook is not None:
        failure_hook("after-project-json")
    if digest((root / "README.md").read_bytes()) != files["README.md"]["before_sha256"]:
        raise RuntimeError("事务写入冲突：README.md 在替换前发生变化")
    atomic_replace(root / "README.md", decode_snapshot(files["README.md"], "after_base64"))
    for name, record in files.items():
        if digest((root / name).read_bytes()) != record["after_sha256"]:
            raise RuntimeError(f"写入后摘要核对失败：{name}")
    return journal


def apply_registration(authorization, foundation, project_id, *, artifact_id, kind,
                       version, producer_role, purpose, summary,
                       expected_project_sha256, expected_readme_sha256,
                       path=None, manifest=None, set_current=False,
                       _failure_hook=None):
    require_authorization(authorization, project_id)
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    with project_state_lock(root, "artifact-registry-apply"):
        if (root / JOURNAL_NAME).exists() or (root / JOURNAL_NAME).is_symlink():
            raise ValueError("存在未完成的成果索引事务；先由 Main 恢复")
        before_project = (root / "project.json").read_bytes()
        before_readme = (root / "README.md").read_bytes()
        if digest(before_project) != expected_project_sha256:
            raise ValueError("project.json 乐观摘要冲突；重新预览")
        if digest(before_readme) != expected_readme_sha256:
            raise ValueError("README.md 乐观摘要冲突；重新预览")
        preview = artifacts.preview_register(
            foundation, project_id, artifact_id, kind, version, producer_role,
            purpose, summary, path=path, manifest=manifest, set_current=set_current,
        )
        if preview["project_json_precondition"]["sha256"] != expected_project_sha256:
            raise ValueError("预览使用的 project.json 版本已改变")
        if preview["proposed_changes"]["readme"]["before_sha256"] != expected_readme_sha256:
            raise ValueError("预览使用的 README.md 版本已改变")
        data = json.loads(before_project.decode("utf-8"))
        registry = materialize_registration(
            preview["proposed_changes"]["artifact_registry"], artifact_id,
            version, authorization, utc_now(),
        )
        data["artifact_registry"] = registry
        data["artifacts"][kind] = preview["proposed_changes"]["legacy_artifact_after"]
        artifacts.validate_registry(root, data)
        after_project = json_text(data).encode("utf-8")
        readme = artifacts.preview_readme(before_readme.decode("utf-8"), registry)
        after_readme = readme["proposed_content"].encode("utf-8")
        if after_project == before_project and after_readme == before_readme:
            return {
                "status": "unchanged", "project_id": project_id,
                "artifact_id": artifact_id, "version": version,
                "project_json_sha256": digest(before_project),
                "readme_sha256": digest(before_readme),
                "actor": authorization.actor(),
            }
        transaction = build_transaction(
            project_id, authorization, before_project, after_project,
            before_readme, after_readme,
        )
        journal_path = _write_transaction(root, transaction, _failure_hook)
        result = artifacts.inspect(foundation, project_id)
        if result["status"] != "consistent":
            raise RuntimeError("写入完成但索引一致性检查未通过")
        remove_journal(journal_path)
        return {
            "status": "applied", "project_id": project_id,
            "artifact_id": artifact_id, "version": version,
            "transaction_id": transaction["transaction_id"],
            "project_json_sha256": result["project_json_sha256"],
            "readme_sha256": result["readme_sha256"],
            "actor": authorization.actor(),
            "approval_changed": False,
            "handoff_started": False,
        }


def recover_registration(authorization, foundation, project_id):
    require_authorization(authorization, project_id)
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    with project_state_lock(root, "artifact-registry-recover"):
        journal_path, raw_transaction = read_journal(root)
        transaction = validate_transaction(raw_transaction, project_id)
        recovered = []
        already_complete = []
        for name in ("project.json", "README.md"):
            record = transaction["files"][name]
            current = (root / name).read_bytes()
            current_sha = digest(current)
            if current_sha == record["after_sha256"]:
                already_complete.append(name)
                continue
            if current_sha != record["before_sha256"]:
                raise ValueError(f"恢复冲突：{name} 已被事务外修改；不覆盖")
            atomic_replace(root / name, decode_snapshot(record, "after_base64"))
            recovered.append(name)
        for name, record in transaction["files"].items():
            if digest((root / name).read_bytes()) != record["after_sha256"]:
                raise RuntimeError(f"恢复后摘要核对失败：{name}")
        result = artifacts.inspect(foundation, project_id)
        if result["status"] != "consistent":
            raise RuntimeError("恢复后索引一致性检查未通过")
        remove_journal(journal_path)
        return {
            "status": "recovered", "project_id": project_id,
            "transaction_id": transaction["transaction_id"],
            "recovered_files": recovered,
            "already_complete_files": already_complete,
            "recovered_by": authorization.actor(),
            "original_actor": transaction["actor"],
            "project_json_sha256": result["project_json_sha256"],
            "readme_sha256": result["readme_sha256"],
        }


if __name__ == "__main__":
    print(json.dumps({
        "status": "fail",
        "error": "Main 写入内核没有 CLI；必须由受信运行时适配器签发 capability 后调用",
    }, ensure_ascii=False), file=sys.stderr)
    sys.exit(2)
