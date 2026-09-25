"""Read-only artifact registry inspection and registration preview.

This module never writes project files, records approvals, sends messages, or
starts downstream work. A future mutating Main tool must bind its caller from
the runtime trust boundary instead of accepting a role claim from CLI input.
"""

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

from project_init import context as project_context, load_project


REGISTRY_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
KINDS = ("requirements", "solution", "ui")
DEFAULT_CANDIDATES = {
    "requirements": "docs/requirements.md",
    "solution": "docs/solution.md",
    "ui": "ui/artifact-manifest.json",
}
README_PLACEHOLDER = "当前没有需求、方案或 UI 成果，按需创建后登记。"
MARKER_START = "<!-- buzz-develop-helper:artifact-index:start -->"
MARKER_END = "<!-- buzz-develop-helper:artifact-index:end -->"
MAX_METADATA_BYTES = 128 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ARTIFACT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_small_file(path, label):
    with path.open("rb") as stream:
        raw = stream.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        raise ValueError(f"{label} 超过 128 KiB 限制")
    return raw


def safe_project_file(root, relative, limit=MAX_ARTIFACT_BYTES):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("成果路径必须是项目内 POSIX 相对路径")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("成果路径必须是项目内规范相对路径")
    path = root
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("不允许通过软链登记成果")
    if not path.exists() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"成果文件缺失或不是独立普通文件：{relative}")
    if not path.resolve().is_relative_to(root):
        raise ValueError("成果路径越界")
    size = path.stat().st_size
    if size > limit:
        raise ValueError(f"成果文件超过首版 {limit // (1024 * 1024)} MiB 限制：{relative}")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return {"path": candidate.as_posix(), "sha256": hasher.hexdigest(), "size": size}


def document_status(path):
    raw = read_small_file(path, "文本成果")
    text = raw.decode("utf-8")
    status = None
    approval_verified = None
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            front_matter = text[4:end]
            for line in front_matter.splitlines():
                key, separator, value = line.partition(":")
                if not separator:
                    continue
                if key.strip() == "status":
                    status = value.strip() or None
                elif key.strip() == "approval_verified":
                    lowered = value.strip().lower()
                    approval_verified = {"true": True, "false": False}.get(lowered)
    return status, approval_verified


def read_manifest(root, relative):
    metadata = safe_project_file(root, relative, MAX_METADATA_BYTES)
    path = root / relative
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("成果清单必须是 UTF-8 JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("不支持的成果清单 schema_version")
    entrypoint = manifest.get("entrypoint")
    members = manifest.get("files")
    if not isinstance(entrypoint, str) or not isinstance(members, list) or not members:
        raise ValueError("成果清单必须包含 entrypoint 和非空 files")
    verified = []
    seen = set()
    for item in members:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("成果清单 files 仅接受 path 和 sha256")
        relative_path, expected = item["path"], item["sha256"]
        if relative_path in seen:
            raise ValueError("成果清单包含重复路径")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise ValueError("成果清单包含无效 SHA-256")
        actual = safe_project_file(root, relative_path)
        if actual["sha256"] != expected:
            raise ValueError(f"成果清单摘要不匹配：{relative_path}")
        verified.append(actual)
        seen.add(relative_path)
    if entrypoint not in seen:
        raise ValueError("成果清单 entrypoint 必须列入 files")
    return {
        "type": "file-set",
        "manifest": metadata,
        "entrypoint": entrypoint,
        "files": verified,
    }


def artifact_content(root, path=None, manifest=None):
    if bool(path) == bool(manifest):
        raise ValueError("必须且只能提供 --path 或 --manifest")
    if manifest:
        return read_manifest(root, manifest)
    result = safe_project_file(root, path)
    return {"type": "file", **result}


def validate_registry(root, data):
    registry = data.get("artifact_registry")
    if registry is None:
        return None, []
    if not isinstance(registry, dict) or registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError("不支持的 artifact_registry schema_version")
    if registry.get("confirmations_path") != "docs/decisions.md":
        raise ValueError("artifact_registry.confirmations_path 不受支持")
    if registry.get("handoffs_directory") != "docs/handoffs":
        raise ValueError("artifact_registry.handoffs_directory 不受支持")
    entries = registry.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("artifact_registry.entries 必须是对象")
    verified = []
    for artifact_id, entry in entries.items():
        if not ARTIFACT_ID_RE.fullmatch(artifact_id) or not isinstance(entry, dict):
            raise ValueError("成果 ID 或登记结构无效")
        if entry.get("artifact_id") != artifact_id or entry.get("kind") not in KINDS:
            raise ValueError(f"成果登记身份不匹配：{artifact_id}")
        versions = entry.get("versions")
        current = entry.get("current_version")
        if not isinstance(versions, list) or not versions:
            raise ValueError(f"成果登记没有版本：{artifact_id}")
        seen_versions = set()
        for version in versions:
            if not isinstance(version, dict) or not VERSION_RE.fullmatch(str(version.get("version", ""))):
                raise ValueError(f"成果版本格式无效：{artifact_id}")
            label = version["version"]
            if label in seen_versions:
                raise ValueError(f"成果版本重复：{artifact_id}@{label}")
            content = version.get("content")
            if not isinstance(content, dict) or content.get("type") not in {"file", "file-set"}:
                raise ValueError(f"成果内容结构无效：{artifact_id}@{label}")
            if content["type"] == "file":
                actual = safe_project_file(root, content.get("path"))
                if content.get("sha256") != actual["sha256"] or content.get("size") != actual["size"]:
                    raise ValueError(f"成果版本摘要不匹配：{artifact_id}@{label}")
            else:
                manifest = content.get("manifest")
                if not isinstance(manifest, dict):
                    raise ValueError(f"成果清单记录无效：{artifact_id}@{label}")
                actual = read_manifest(root, manifest.get("path"))
                if actual != content:
                    raise ValueError(f"成果集合与清单不匹配：{artifact_id}@{label}")
            confirmations = version.get("confirmation_ids")
            if not isinstance(confirmations, list) or any(not isinstance(value, str) for value in confirmations):
                raise ValueError(f"确认引用格式无效：{artifact_id}@{label}")
            for field in ("producer_role", "purpose", "summary"):
                if not isinstance(version.get(field), str) or not version[field].strip():
                    raise ValueError(f"成果版本缺少 {field}：{artifact_id}@{label}")
            if version.get("document_status") is not None and not isinstance(version["document_status"], str):
                raise ValueError(f"文档状态格式无效：{artifact_id}@{label}")
            if not isinstance(version.get("open_items"), list):
                raise ValueError(f"未决项格式无效：{artifact_id}@{label}")
            availability = version.get("availability")
            if not isinstance(availability, dict) or availability.get("scope") not in {"local-only", "git-commit"}:
                raise ValueError(f"可见范围格式无效：{artifact_id}@{label}")
            commit = availability.get("git_commit")
            if availability["scope"] == "local-only" and commit is not None:
                raise ValueError(f"本地成果不能声称 Git 提交：{artifact_id}@{label}")
            if availability["scope"] == "git-commit" and (
                not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit)
            ):
                raise ValueError(f"Git 可见成果缺少有效提交：{artifact_id}@{label}")
            registration = version.get("registration")
            actor = registration.get("actor") if isinstance(registration, dict) else None
            if (
                not isinstance(actor, dict)
                or actor.get("role") != "main"
                or not isinstance(actor.get("principal_id"), str)
                or not actor["principal_id"].strip()
                or not isinstance(actor.get("authority"), str)
                or not actor["authority"].strip()
                or not isinstance(registration.get("recorded_at"), str)
                or not TIMESTAMP_RE.fullmatch(registration["recorded_at"])
            ):
                raise ValueError(f"登记身份必须由运行时绑定 Main：{artifact_id}@{label}")
            seen_versions.add(label)
            verified.append({"artifact_id": artifact_id, "version": label})
        if current is not None and current not in seen_versions:
            raise ValueError(f"current_version 不存在：{artifact_id}")
    return registry, verified


def empty_registry():
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "confirmations_path": "docs/decisions.md",
        "handoffs_directory": "docs/handoffs",
        "entries": {},
    }


def render_managed_block(registry):
    rows = []
    for artifact_id, entry in sorted(registry["entries"].items()):
        current = entry.get("current_version")
        if current is None:
            continue
        version = next(value for value in entry["versions"] if value["version"] == current)
        content = version["content"]
        path = content["path"] if content["type"] == "file" else content["manifest"]["path"]
        status = version.get("document_status") or "未标注"
        confirmation = "、".join(version["confirmation_ids"]) or "未正式确认"
        rows.append(
            f"| `{artifact_id}` | {entry['kind']} | `{current}` | `{path}` | "
            f"`{content_sha(content)[:12]}` | {status} | {confirmation} |"
        )
    if rows:
        table = (
            "| 成果 ID | 类型 | 当前版本 | 路径/清单 | SHA-256 | 文档状态 | 用途确认 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows)
        )
    else:
        table = "当前没有已登记成果。"
    return f"{MARKER_START}\n{table}\n{MARKER_END}"


def content_sha(content):
    return content["sha256"] if content["type"] == "file" else content["manifest"]["sha256"]


def content_path(content):
    return content["path"] if content["type"] == "file" else content["manifest"]["path"]


def preview_readme(readme, registry):
    block = render_managed_block(registry)
    if MARKER_START in readme or MARKER_END in readme:
        if readme.count(MARKER_START) != 1 or readme.count(MARKER_END) != 1:
            raise ValueError("README 成果索引标记不完整或重复")
        start = readme.index(MARKER_START)
        end = readme.index(MARKER_END, start) + len(MARKER_END)
        proposed = readme[:start] + block + readme[end:]
        removed_placeholder = False
    else:
        heading = re.search(r"(?m)^## 成果索引\s*$", readme)
        removed_placeholder = False
        if heading:
            insert_at = heading.end()
            tail = readme[insert_at:]
            placeholder = re.search(
                rf"\A\s*{re.escape(README_PLACEHOLDER)}\s*(?=\n## |\Z)", tail
            )
            if placeholder:
                tail = tail[placeholder.end():]
                removed_placeholder = True
            proposed = readme[:insert_at] + "\n\n" + block + "\n" + tail.lstrip("\n")
        else:
            proposed = readme.rstrip() + "\n\n## 成果索引\n\n" + block + "\n"
    before = readme.encode("utf-8")
    after = proposed.encode("utf-8")
    diff = "".join(difflib.unified_diff(
        readme.splitlines(keepends=True), proposed.splitlines(keepends=True),
        fromfile="README.md (current)", tofile="README.md (proposed)"
    ))
    return {
        "before_sha256": digest(before),
        "after_sha256": digest(after),
        "changed": before != after,
        "initializer_placeholder_removed": removed_placeholder,
        "managed_block": block,
        "proposed_content": proposed,
        "diff": diff,
    }


def inspect(foundation, project_id):
    _, root = project_context(foundation, project_id)
    data = load_project(root, project_id)
    registry, verified = validate_registry(root, data)
    candidates = []
    issues = []
    candidates_by_kind = dict(DEFAULT_CANDIDATES)
    prd_candidate = root / "docs/PRD.md"
    if prd_candidate.exists() or prd_candidate.is_symlink():
        candidates_by_kind["requirements"] = "docs/PRD.md"
    for kind, relative in candidates_by_kind.items():
        candidate = root / relative
        if candidate.exists() or candidate.is_symlink():
            try:
                content = artifact_content(root, manifest=relative) if kind == "ui" else artifact_content(root, path=relative)
                candidates.append({"kind": kind, "content": content})
                entry = registry.get("entries", {}).get(kind) if registry else None
                registered_paths = {
                    content_path(version["content"]) for version in entry["versions"]
                } if entry else set()
                if data.get("artifacts", {}).get(kind) is None and relative not in registered_paths:
                    issues.append({"code": "candidate_not_indexed", "kind": kind, "path": relative})
            except ValueError as error:
                issues.append({"code": "invalid_candidate", "kind": kind, "path": relative,
                               "detail": str(error)})
    legacy = data.get("artifacts")
    if not isinstance(legacy, dict):
        raise ValueError("project.json.artifacts 必须是对象")
    entries = registry["entries"] if registry else {}
    for kind in KINDS:
        pointer = legacy.get(kind)
        if pointer is not None and not isinstance(pointer, str):
            issues.append({"code": "invalid_legacy_pointer", "kind": kind})
            continue
        entry = entries.get(kind)
        if entry is None:
            if pointer is not None:
                try:
                    if kind == "ui" and pointer == DEFAULT_CANDIDATES["ui"]:
                        artifact_content(root, manifest=pointer)
                    else:
                        artifact_content(root, path=pointer)
                    issues.append({"code": "legacy_pointer_not_registered", "kind": kind,
                                   "path": pointer})
                except ValueError as error:
                    issues.append({"code": "invalid_legacy_pointer", "kind": kind,
                                   "path": pointer, "detail": str(error)})
            continue
        current = entry.get("current_version")
        expected = None
        if current is not None:
            version = next(value for value in entry["versions"] if value["version"] == current)
            expected = content_path(version["content"])
        if pointer != expected:
            issues.append({"code": "legacy_registry_mismatch", "kind": kind,
                           "legacy_path": pointer, "registry_path": expected})
    readme_raw = read_small_file(root / "README.md", "README.md")
    readme = readme_raw.decode("utf-8")
    if registry is not None:
        expected = render_managed_block(registry)
        if expected not in readme:
            issues.append({"code": "readme_projection_stale"})
    return {
        "status": "consistent" if not issues else "attention_required",
        "mode": "read-only",
        "project_id": project_id,
        "project_path": str(root),
        "project_json_sha256": digest((root / "project.json").read_bytes()),
        "readme_sha256": digest(readme_raw),
        "registry_schema_version": registry.get("schema_version") if registry else None,
        "verified_registry_versions": verified,
        "candidates": candidates,
        "issues": issues,
        "approval_checked": False,
        "note": "只核对文件和索引；不读取确认事件、不写项目、不启动下游",
    }


def preview_register(foundation, project_id, artifact_id, kind, version, producer_role,
                     purpose, summary, path=None, manifest=None, set_current=False):
    if not ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise ValueError("成果 ID 须为小写字母、数字或连字符")
    if kind not in KINDS or not VERSION_RE.fullmatch(version):
        raise ValueError("成果类型或版本格式无效")
    for value, label in ((producer_role, "生产角色"), (purpose, "用途"), (summary, "摘要")):
        if not isinstance(value, str) or not value.strip() or "\n" in value:
            raise ValueError(f"{label} 必须是非空单行文本")
    _, root = project_context(foundation, project_id)
    data = load_project(root, project_id)
    current_registry, _ = validate_registry(root, data)
    registry = json.loads(json.dumps(current_registry or empty_registry()))
    content = artifact_content(root, path=path, manifest=manifest)
    primary_path = content_path(content)
    status, approval_verified = (None, None)
    if content["type"] == "file" and primary_path.endswith(".md"):
        status, approval_verified = document_status(root / primary_path)
    proposed_version = {
        "version": version,
        "content": content,
        "document_status": status,
        "producer_role": producer_role.strip(),
        "purpose": purpose.strip(),
        "summary": summary.strip(),
        "open_items": [],
        "confirmation_ids": [],
        "availability": {"scope": "local-only", "git_commit": None},
        "registration": {
            "actor": {
                "role": "main",
                "principal_id": "<runtime-bound-required-at-apply>",
                "authority": "<trusted-runtime-required-at-apply>",
            },
            "recorded_at": "<write-time-required-at-apply>",
        },
    }
    entry = registry["entries"].get(artifact_id)
    if entry is None:
        entry = {"artifact_id": artifact_id, "kind": kind, "current_version": None, "versions": []}
        registry["entries"][artifact_id] = entry
    elif entry.get("kind") != kind:
        raise ValueError("同一成果 ID 不能改变类型")
    existing = next((item for item in entry["versions"] if item["version"] == version), None)
    if existing is not None:
        if content_sha(existing["content"]) != content_sha(content):
            raise ValueError("同一版本标签已绑定不同内容")
        proposed_version = existing
        operation = "already_registered"
    else:
        entry["versions"].append(proposed_version)
        operation = "register_version"
    if set_current:
        entry["current_version"] = version
    elif entry["current_version"] is None:
        operation = "register_historical_version_requires_explicit_current"
    legacy = data.get("artifacts")
    if not isinstance(legacy, dict) or kind not in legacy:
        raise ValueError("project.json 缺少兼容 artifacts 字段")
    legacy_before = legacy[kind]
    legacy_after = primary_path if set_current else legacy_before
    readme_raw = read_small_file(root / "README.md", "README.md")
    readme_preview = preview_readme(readme_raw.decode("utf-8"), registry)
    warnings = ["登记不等于正式确认；confirmation_ids 保持为空"]
    if approval_verified is False:
        warnings.append("成果正文标记 approval_verified=false，预览不会提升状态")
    if not set_current:
        warnings.append("未指定 --set-current；该版本不会成为当前入口")
    return {
        "status": "preview",
        "mode": "read-only",
        "operation": operation,
        "project_id": project_id,
        "artifact": {"artifact_id": artifact_id, "kind": kind, "version": version,
                     "content_sha256": content_sha(content)},
        "project_json_precondition": {
            "sha256": digest((root / "project.json").read_bytes()),
            "legacy_artifact_before": legacy_before,
        },
        "proposed_changes": {
            "artifact_registry": registry,
            "legacy_artifact_after": legacy_after,
            "readme": readme_preview,
        },
        "write_requirements": {
            "tool": "Main-only mutation core; host adapter required",
            "caller_identity": "must be attached by trusted runtime, never accepted from CLI or document",
            "optimistic_checks": ["project_json_precondition.sha256", "readme.before_sha256"],
        },
        "approval_checked": False,
        "handoff_started": False,
        "warnings": warnings,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_command = commands.add_parser("inspect")
    inspect_command.add_argument("project_id")
    preview = commands.add_parser("preview-register")
    preview.add_argument("project_id")
    preview.add_argument("--artifact-id", required=True)
    preview.add_argument("--kind", choices=KINDS, required=True)
    preview.add_argument("--version", required=True)
    preview.add_argument("--producer-role", required=True)
    preview.add_argument("--purpose", required=True)
    preview.add_argument("--summary", required=True)
    source = preview.add_mutually_exclusive_group(required=True)
    source.add_argument("--path")
    source.add_argument("--manifest")
    preview.add_argument("--set-current", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        if args.command == "inspect":
            result = inspect(args.foundation, args.project_id)
        else:
            result = preview_register(
                args.foundation, args.project_id, args.artifact_id, args.kind, args.version,
                args.producer_role, args.purpose, args.summary, path=args.path,
                manifest=args.manifest, set_current=args.set_current,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
