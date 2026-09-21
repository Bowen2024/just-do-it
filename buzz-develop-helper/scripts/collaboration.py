"""Read-only confirmation and handoff inspection.

This module validates persisted records and snapshots. It never confirms,
sends, acknowledges, starts downstream work, or mutates project files.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import artifacts
import trusted_context
from project_init import context as project_context, load_project


SCHEMA_VERSION = 1
DECISIONS_PATH = "docs/decisions.md"
HANDOFFS_DIRECTORY = "docs/handoffs"
DECISIONS_START = "<!-- buzz-develop-helper:confirmations:start -->"
DECISIONS_END = "<!-- buzz-develop-helper:confirmations:end -->"
MAX_RECORD_BYTES = 1024 * 1024
CONFIRMATION_ID_RE = re.compile(r"^C-[0-9a-f]{20}$")
HANDOFF_ID_RE = re.compile(r"^H-[0-9a-f]{20}$")
TIMESTAMP_RE = artifacts.TIMESTAMP_RE


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def content_sha(content):
    return artifacts.content_sha(content)


def read_regular(root, relative, *, missing_ok=False, limit=MAX_RECORD_BYTES):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("记录路径必须是项目内 POSIX 相对路径")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("记录路径必须是项目内规范相对路径")
    path = root
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"记录文件不能经过软链：{relative}")
    if not path.resolve().is_relative_to(root):
        raise ValueError("记录路径越界")
    if not path.exists():
        if missing_ok:
            return None
        raise ValueError(f"记录文件不存在：{relative}")
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"记录文件不是独立普通文件：{relative}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"记录文件超过大小限制：{relative}")
    return raw


def empty_decisions():
    return {"schema_version": SCHEMA_VERSION, "confirmations": []}


def decisions_block(value):
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    return f"{DECISIONS_START}\n```json\n{payload}\n```\n{DECISIONS_END}"


def parse_decisions_text(text):
    if DECISIONS_START not in text and DECISIONS_END not in text:
        raise ValueError("decisions.md 缺少受管确认记录块")
    if text.count(DECISIONS_START) != 1 or text.count(DECISIONS_END) != 1:
        raise ValueError("decisions.md 确认记录标记不完整或重复")
    start = text.index(DECISIONS_START) + len(DECISIONS_START)
    end = text.index(DECISIONS_END, start)
    body = text[start:end].strip()
    if not body.startswith("```json\n") or not body.endswith("\n```"):
        raise ValueError("decisions.md 受管块必须包含 JSON code block")
    try:
        value = json.loads(body[len("```json\n"):-len("\n```")])
    except json.JSONDecodeError as error:
        raise ValueError("decisions.md 确认记录 JSON 无效") from error
    validate_decisions_shape(value)
    return value


def read_decisions(root):
    raw = read_regular(root, DECISIONS_PATH, missing_ok=True)
    if raw is None:
        return "", empty_decisions(), "missing"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("decisions.md 必须是 UTF-8") from error
    return text, parse_decisions_text(text), digest(raw)


def render_decisions(existing, value):
    validate_decisions_shape(value)
    block = decisions_block(value)
    if not existing:
        return "# 项目确认记录\n\n" + block + "\n"
    if DECISIONS_START not in existing and DECISIONS_END not in existing:
        return existing.rstrip() + "\n\n" + block + "\n"
    parse_decisions_text(existing)
    start = existing.index(DECISIONS_START)
    end = existing.index(DECISIONS_END, start) + len(DECISIONS_END)
    return existing[:start] + block + existing[end:]


def required_text(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} 必须是非空单行文本")
    return value.strip()


def required_statement(value, label):
    return trusted_context.required_statement(value, label)


def validate_actor(actor, label):
    if not isinstance(actor, dict):
        raise ValueError(f"{label} 身份无效")
    required_text(actor.get("principal_id"), f"{label} principal_id")
    required_text(actor.get("authority"), f"{label} authority")


def validate_decisions_shape(value):
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("不支持的确认记录 schema_version")
    confirmations = value.get("confirmations")
    if not isinstance(confirmations, list):
        raise ValueError("confirmations 必须是数组")
    seen = set()
    for record in confirmations:
        if not isinstance(record, dict) or not CONFIRMATION_ID_RE.fullmatch(str(record.get("confirmation_id", ""))):
            raise ValueError("确认记录 ID 无效")
        confirmation_id = record["confirmation_id"]
        if confirmation_id in seen:
            raise ValueError(f"确认记录重复：{confirmation_id}")
        if record.get("schema_version") != SCHEMA_VERSION or record.get("status") != "active":
            raise ValueError(f"确认记录状态无效：{confirmation_id}")
        if not TIMESTAMP_RE.fullmatch(str(record.get("recorded_at", ""))):
            raise ValueError(f"确认记录时间无效：{confirmation_id}")
        validate_actor(record.get("recorded_by"), "记录 Main")
        artifact = record.get("artifact")
        if not isinstance(artifact, dict) or not artifacts.ARTIFACT_ID_RE.fullmatch(str(artifact.get("artifact_id", ""))):
            raise ValueError(f"确认对象无效：{confirmation_id}")
        if artifact.get("kind") not in artifacts.KINDS or not artifacts.VERSION_RE.fullmatch(str(artifact.get("version", ""))):
            raise ValueError(f"确认对象类型或版本无效：{confirmation_id}")
        if not artifacts.SHA256_RE.fullmatch(str(artifact.get("content_sha256", ""))):
            raise ValueError(f"确认对象摘要无效：{confirmation_id}")
        required_text(record.get("permitted_use"), "确认用途")
        required_text(record.get("confirmed_scope"), "确认范围")
        if not isinstance(record.get("non_authorizations"), list) or not isinstance(record.get("open_items"), list):
            raise ValueError(f"确认边界无效：{confirmation_id}")
        evidence = record.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("type") != "current-session":
            raise ValueError(f"确认依据类型无效：{confirmation_id}")
        for field in ("provider", "authority", "user_principal_id", "session_id", "message_id"):
            required_text(evidence.get(field), f"确认依据 {field}")
        required_statement(evidence.get("statement"), "确认依据 statement")
        if not TIMESTAMP_RE.fullmatch(str(evidence.get("confirmed_at", ""))) or evidence.get("runtime_authenticated") is not True:
            raise ValueError(f"当前会话确认依据未认证：{confirmation_id}")
        snapshot = record.get("snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("type") not in {"file", "file-set"}:
            raise ValueError(f"确认快照结构无效：{confirmation_id}")
        seen.add(confirmation_id)


def confirmation_map(decisions):
    return {record["confirmation_id"]: record for record in decisions["confirmations"]}


def artifact_version(registry, artifact_id, version):
    entry = registry.get("entries", {}).get(artifact_id) if registry else None
    if entry is None:
        raise ValueError(f"成果尚未登记：{artifact_id}")
    for item in entry["versions"]:
        if item["version"] == version:
            return entry, item
    raise ValueError(f"成果版本尚未登记：{artifact_id}@{version}")


def validate_snapshot(root, record):
    snapshot = record["snapshot"]
    if snapshot["type"] == "file":
        raw = read_regular(root, snapshot.get("path"), limit=artifacts.MAX_ARTIFACT_BYTES)
        if digest(raw) != snapshot.get("sha256") or snapshot["sha256"] != record["artifact"]["content_sha256"]:
            raise ValueError(f"确认快照摘要不匹配：{record['confirmation_id']}")
        return
    manifest_raw = read_regular(root, snapshot.get("manifest_path"))
    if digest(manifest_raw) != snapshot.get("manifest_sha256") or snapshot["manifest_sha256"] != record["artifact"]["content_sha256"]:
        raise ValueError(f"确认清单快照摘要不匹配：{record['confirmation_id']}")
    files = snapshot.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError(f"确认集合快照缺少成员：{record['confirmation_id']}")
    for item in files:
        raw = read_regular(root, item.get("snapshot_path"), limit=artifacts.MAX_ARTIFACT_BYTES)
        if digest(raw) != item.get("sha256"):
            raise ValueError(f"确认集合成员摘要不匹配：{record['confirmation_id']}")


def read_handoffs(root):
    directory = root / HANDOFFS_DIRECTORY
    if directory.is_symlink():
        raise ValueError("handoffs 目录不能是软链")
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError("handoffs 必须是目录")
    records = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix != ".json" or path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError(f"handoffs 包含不支持的对象：{path.name}")
        raw = read_regular(root, f"{HANDOFFS_DIRECTORY}/{path.name}")
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"交接记录不是有效 JSON：{path.name}") from error
        records.append(record)
    return records


def validate_handoff(record, project_id, confirmations):
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("交接记录 schema 无效")
    handoff_id = str(record.get("handoff_id", ""))
    if not HANDOFF_ID_RE.fullmatch(handoff_id) or record.get("project_id") != project_id:
        raise ValueError("交接记录身份无效")
    if record.get("status") not in {"prepared", "sent", "received-verified"}:
        raise ValueError(f"交接状态无效：{handoff_id}")
    if not TIMESTAMP_RE.fullmatch(str(record.get("prepared_at", ""))):
        raise ValueError(f"交接准备时间无效：{handoff_id}")
    validate_actor(record.get("prepared_by"), "交接 Main")
    authorization = record.get("authorization_evidence")
    if (not isinstance(authorization, dict)
            or authorization.get("type") != "current-session"
            or authorization.get("runtime_authenticated") is not True
            or not TIMESTAMP_RE.fullmatch(str(authorization.get("authorized_at", "")))):
        raise ValueError(f"交接授权依据无效：{handoff_id}")
    for field in ("provider", "authority", "user_principal_id", "session_id", "message_id"):
        required_text(authorization.get(field), f"交接授权 {field}")
    required_statement(authorization.get("statement"), "交接授权 statement")
    recipient = record.get("recipient")
    if not isinstance(recipient, dict):
        raise ValueError(f"交接接收者无效：{handoff_id}")
    for field in ("role", "principal_id", "authority"):
        required_text(recipient.get(field), f"交接接收者 {field}")
    required_text(record.get("purpose"), "交接用途")
    if not isinstance(record.get("allowed_actions"), list) or not record["allowed_actions"]:
        raise ValueError(f"交接允许动作无效：{handoff_id}")
    if not isinstance(record.get("expected_outputs"), list) or not record["expected_outputs"]:
        raise ValueError(f"交接预期输出无效：{handoff_id}")
    if not isinstance(record.get("execution_authorized"), bool) or record.get("downstream_started") is not False:
        raise ValueError(f"交接执行边界无效：{handoff_id}")
    inputs = record.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError(f"交接输入为空：{handoff_id}")
    for item in inputs:
        confirmation_id = item.get("confirmation_id") if isinstance(item, dict) else None
        confirmation = confirmations.get(confirmation_id)
        if confirmation is None or item.get("content_sha256") != confirmation["artifact"]["content_sha256"]:
            raise ValueError(f"交接输入确认无效：{handoff_id}")
        if record["purpose"] != confirmation["permitted_use"]:
            raise ValueError(f"交接用途超出确认：{handoff_id}")
    delivery = record.get("delivery")
    receipt = record.get("receipt")
    if record["status"] in {"sent", "received-verified"} and not isinstance(delivery, dict):
        raise ValueError(f"交接缺少发送依据：{handoff_id}")
    if isinstance(delivery, dict):
        for field in ("provider", "authority", "message_id", "recipient_principal_id"):
            required_text(delivery.get(field), f"发送依据 {field}")
        if delivery.get("runtime_verified") is not True or not TIMESTAMP_RE.fullmatch(str(delivery.get("sent_at", ""))):
            raise ValueError(f"交接发送依据未认证：{handoff_id}")
    if record["status"] == "received-verified":
        if not isinstance(receipt, dict) or receipt.get("runtime_authenticated") is not True:
            raise ValueError(f"交接缺少受信接收回执：{handoff_id}")
        if receipt.get("principal_id") != recipient["principal_id"] or receipt.get("authority") != recipient["authority"]:
            raise ValueError(f"交接回执身份不匹配：{handoff_id}")
    return handoff_id


def inspect(foundation, project_id):
    base = artifacts.inspect(foundation, project_id)
    _, root = project_context(foundation, project_id)
    data = load_project(root, project_id)
    registry, _ = artifacts.validate_registry(root, data)
    _, decisions, decisions_sha = read_decisions(root)
    confirmations = confirmation_map(decisions)
    issues = list(base["issues"])
    referenced = set()
    for confirmation_id, record in confirmations.items():
        try:
            if record.get("project_id") != project_id:
                raise ValueError("确认记录项目不匹配")
            _, version = artifact_version(
                registry, record["artifact"]["artifact_id"], record["artifact"]["version"])
            if content_sha(version["content"]) != record["artifact"]["content_sha256"]:
                raise ValueError("确认记录成果摘要不匹配")
            validate_snapshot(root, record)
        except ValueError as error:
            issues.append({"code": "invalid_confirmation", "confirmation_id": confirmation_id,
                           "detail": str(error)})
    if registry:
        for artifact_id, entry in registry["entries"].items():
            for version in entry["versions"]:
                for confirmation_id in version["confirmation_ids"]:
                    record = confirmations.get(confirmation_id)
                    if record is None:
                        issues.append({"code": "missing_confirmation", "confirmation_id": confirmation_id})
                        continue
                    if (record["artifact"]["artifact_id"], record["artifact"]["version"]) != (artifact_id, version["version"]):
                        issues.append({"code": "confirmation_target_mismatch", "confirmation_id": confirmation_id})
                    referenced.add(confirmation_id)
    for confirmation_id in confirmations:
        if confirmation_id not in referenced:
            issues.append({"code": "unreferenced_confirmation", "confirmation_id": confirmation_id})
    verified_handoffs = []
    try:
        for handoff in read_handoffs(root):
            verified_handoffs.append(validate_handoff(handoff, project_id, confirmations))
    except ValueError as error:
        issues.append({"code": "invalid_handoff", "detail": str(error)})
    return {
        **base,
        "status": "consistent" if not issues else "attention_required",
        "issues": issues,
        "approval_checked": True,
        "confirmation_evidence_mode": "persisted-current-session-records",
        "decisions_sha256": decisions_sha,
        "verified_confirmation_ids": sorted(confirmations),
        "verified_handoff_ids": sorted(verified_handoffs),
        "note": "只核对确认、快照与交接记录；不发送消息、不启动下游",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id")
    parser.add_argument("--foundation", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.foundation, args.project_id), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
