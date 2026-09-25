"""Project-scoped solution Draft and structural traceability tools."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import artifacts
import collaboration
from project_init import context as project_context, load_project
from project_state import exclusive_lock, project_state_lock
from requirements import (
    LIMIT,
    digest,
    inspect_prd,
    read_document,
    safe_path,
    validate_source_digests,
)


PROFILES = frozenset({"Lite", "Standard", "AI"})
CONTEXT_DOCUMENTS = (
    "project.json",
    "README.md",
    "docs/requirements.md",
    "docs/PRD.md",
    "docs/solution.md",
    "docs/tech-spec.md",
    "docs/decisions.md",
)
SOURCE_DOCUMENTS = ("project.json", "README.md", "docs/PRD.md")
ID_PATTERN = re.compile(r"\b(REQ|AC)-\d{3,}\b")
PROFILE_PATTERN = re.compile(r"(?m)^profile:\s*(Lite|Standard|AI)\s*$")
STATUS_PATTERN = re.compile(r"(?m)^status:\s*([^\s]+)\s*$")
PRD_SHA_PATTERN = re.compile(r"(?m)^prd_sha256:\s*([0-9a-f]{64})\s*$")
APPROVAL_PATTERN = re.compile(r"(?m)^approval_verified:\s*([^\s]+)\s*$")
COVERAGE_STATUS = frozenset({"covered", "not_applicable", "open", "blocked"})
SECTION_PATTERN = re.compile(r"(?m)^##\s+(\d+)\.\s+.+$")


def context(foundation, project_id):
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    return {
        "project_id": project_id,
        "project_path": str(root),
        "documents": [read_document(root, path) for path in CONTEXT_DOCUMENTS],
        "approval_verified": False,
    }


def _ids(content):
    result = {"REQ": set(), "AC": set()}
    if not content:
        return result
    for match in ID_PATTERN.finditer(content):
        identifier = match.group(0)
        result[match.group(1)].add(identifier)
    return result


def _frontmatter_value(pattern, content):
    if not content:
        return None
    match = pattern.search(content)
    return match.group(1) if match else None


def _coverage_rows(content):
    rows = []
    if not content:
        return rows
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 7 or not re.fullmatch(r"REQ-\d{3,}", cells[0]):
            continue
        ac_ids = sorted(set(re.findall(r"\bAC-\d{3,}\b", cells[1])))
        status = cells[6].strip("` ")
        rows.append({
            "req": cells[0],
            "ac": ac_ids,
            "design": cells[2],
            "success": cells[3],
            "failure": cells[4],
            "verification": cells[5],
            "status": status,
        })
    return rows


def _sections(content):
    if not content:
        return {}
    matches = list(SECTION_PATTERN.finditer(content))
    return {
        int(match.group(1)): content[match.end(): matches[index + 1].start()]
        if index + 1 < len(matches) else content[match.end():]
        for index, match in enumerate(matches)
    }


def _prd_confirmations(root, prd_sha):
    project = json.loads(read_document(root, "project.json")["content"])
    registry, _ = artifacts.validate_registry(root, project)
    _, decisions, _ = collaboration.read_decisions(root)
    eligible = []
    invalid = []
    for record in decisions["confirmations"]:
        artifact = record["artifact"]
        if artifact["kind"] != "requirements" or artifact["content_sha256"] != prd_sha:
            continue
        confirmation_id = record["confirmation_id"]
        if record["permitted_use"] != "形成技术方案" or record["open_items"]:
            invalid.append(confirmation_id)
            continue
        try:
            if registry is None:
                raise ValueError("PRD 成果尚未登记")
            _, version = collaboration.artifact_version(
                registry, artifact["artifact_id"], artifact["version"]
            )
            if (
                confirmation_id not in version["confirmation_ids"]
                or artifacts.content_sha(version["content"]) != prd_sha
            ):
                raise ValueError("PRD 登记版本未引用该确认")
            collaboration.validate_snapshot(root, record)
        except ValueError:
            invalid.append(confirmation_id)
            continue
        eligible.append(confirmation_id)
    return sorted(eligible), sorted(invalid)


def inspect(foundation, project_id):
    current = context(foundation, project_id)
    documents = {item["path"]: item for item in current["documents"]}
    prd_document = documents["docs/PRD.md"]
    tech_document = documents["docs/tech-spec.md"]
    requirement_ids = _ids(prd_document["content"])
    tech_ids = _ids(tech_document["content"])
    coverage = _coverage_rows(tech_document["content"])
    issues = []
    prd_review = inspect_prd(foundation, project_id)
    try:
        confirmation_ids, invalid_confirmation_ids = _prd_confirmations(
            Path(current["project_path"]), prd_document["sha256"]
        )
    except (json.JSONDecodeError, ValueError) as error:
        confirmation_ids, invalid_confirmation_ids = [], []
        issues.append({"code": "prd_confirmation_records_invalid", "detail": str(error)})

    if prd_document["content"] is None:
        issues.append({"code": "prd_missing"})
    elif not requirement_ids["REQ"] or not requirement_ids["AC"]:
        issues.append({
            "code": "requirements_ids_missing",
            "req_count": len(requirement_ids["REQ"]),
            "ac_count": len(requirement_ids["AC"]),
        })
    if prd_document["content"] is not None and prd_review["issues"]:
        issues.append({"code": "prd_structure_incomplete", "details": prd_review["issues"]})
    if prd_document["content"] is not None and not confirmation_ids:
        issues.append({
            "code": "prd_not_confirmed_for_solution",
            "required_permitted_use": "形成技术方案",
            "invalid_confirmation_ids": invalid_confirmation_ids,
        })

    if tech_document["content"] is None:
        issues.append({"code": "tech_spec_missing"})
        profile = None
        document_status = None
    else:
        profile = _frontmatter_value(PROFILE_PATTERN, tech_document["content"])
        document_status = _frontmatter_value(STATUS_PATTERN, tech_document["content"])
        bound_prd_sha = _frontmatter_value(
            PRD_SHA_PATTERN, tech_document["content"]
        )
        approval_verified = _frontmatter_value(APPROVAL_PATTERN, tech_document["content"])
        if profile not in PROFILES:
            issues.append({"code": "profile_missing_or_invalid"})
        if document_status != "Draft":
            issues.append({"code": "draft_status_missing_or_invalid", "observed": document_status})
        if approval_verified != "false":
            issues.append({"code": "draft_approval_marker_invalid", "observed": approval_verified})
        if bound_prd_sha != prd_document["sha256"]:
            issues.append({
                "code": "prd_baseline_mismatch",
                "bound_sha256": bound_prd_sha,
                "current_sha256": prd_document["sha256"],
            })
        sections = _sections(tech_document["content"])
        required_sections = set(range(1, 8)) | {10, 11}
        if profile in {"Standard", "AI"}:
            required_sections |= {8, 9}
        missing_sections = sorted(required_sections - set(sections))
        if missing_sections:
            issues.append({"code": "required_sections_missing", "sections": missing_sections})
        if profile == "AI" and 4 in sections:
            ai_section = sections[4]
            required_ai_terms = ("模型", "提示词", "工具", "评估", "权限")
            missing_ai_terms = [term for term in required_ai_terms if term not in ai_section]
            if "不适用" in ai_section or missing_ai_terms:
                issues.append({
                    "code": "ai_contract_incomplete",
                    "missing_terms": missing_ai_terms,
                    "marked_not_applicable": "不适用" in ai_section,
                })

        unknown_req = sorted(tech_ids["REQ"] - requirement_ids["REQ"])
        unknown_ac = sorted(tech_ids["AC"] - requirement_ids["AC"])
        coverage_ac = {identifier for row in coverage for identifier in row["ac"]}
        uncovered_ac = sorted(requirement_ids["AC"] - coverage_ac)
        if unknown_req or unknown_ac:
            issues.append({"code": "unknown_requirement_references", "req": unknown_req, "ac": unknown_ac})
        if uncovered_ac:
            issues.append({"code": "uncovered_acceptance_criteria", "ac": uncovered_ac})
        invalid_coverage = [row for row in coverage if row["status"] not in COVERAGE_STATUS]
        if invalid_coverage:
            issues.append({"code": "invalid_coverage_status", "rows": invalid_coverage})
        incomplete_covered = [
            row for row in coverage
            if row["status"] == "covered" and any(
                value.strip().lower() in {"", "-", "n/a", "待补", "未知"}
                for value in (
                    row["design"], row["success"], row["failure"], row["verification"]
                )
            )
        ]
        if incomplete_covered:
            issues.append({"code": "covered_row_incomplete", "rows": incomplete_covered})
        if requirement_ids["AC"] and not coverage:
            issues.append({"code": "coverage_table_missing"})

    return {
        "mode": "read-only",
        "status": "ready_for_review" if not issues else "attention_required",
        "project_id": project_id,
        "prd": {
            "path": prd_document["path"],
            "sha256": prd_document["sha256"],
            "req_ids": sorted(requirement_ids["REQ"]),
            "ac_ids": sorted(requirement_ids["AC"]),
            "confirmation_ids": confirmation_ids,
        },
        "tech_spec": {
            "path": tech_document["path"],
            "sha256": tech_document["sha256"],
            "profile": profile,
            "document_status": document_status,
            "bound_prd_sha256": (
                _frontmatter_value(PRD_SHA_PATTERN, tech_document["content"])
                if tech_document["content"] is not None else None
            ),
            "referenced_req_ids": sorted(tech_ids["REQ"]),
            "referenced_ac_ids": sorted(tech_ids["AC"]),
            "coverage_rows": coverage,
        },
        "issues": issues,
        "approval_checked": True,
        "confirmation_evidence_mode": "persisted-current-session-records",
        "semantic_correctness_checked": False,
        "runtime_verified": False,
    }


def _render(body, profile, prd_sha, confirmation_ids):
    if body.lstrip().startswith("---"):
        raise ValueError("正文不得自带 front matter；状态与输入摘要由工具生成")
    return (
        "---\n"
        "artifact_kind: tech-spec\n"
        "status: Draft\n"
        "approval_verified: false\n"
        f"profile: {profile}\n"
        "prd_path: docs/PRD.md\n"
        f"prd_sha256: {prd_sha}\n"
        f"prd_confirmation_ids: {json.dumps(confirmation_ids, ensure_ascii=False)}\n"
        "---\n\n"
        + body.strip()
        + "\n"
    )


def save_tech_spec_draft(
    foundation,
    project_id,
    body,
    expected_tech_sha,
    expected_prd_sha,
    profile,
):
    if profile not in PROFILES:
        raise ValueError("profile 必须是 Lite、Standard 或 AI")
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > LIMIT - 512:
        raise ValueError("方案草案必须是非空 UTF-8 文本，且预留元数据后小于 128 KiB")

    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    target = safe_path(root, "docs/tech-spec.md")
    lock = root / ".solution.lock"
    with project_state_lock(root, "solution-save"):
        with exclusive_lock(lock, "方案写入锁已存在；先核对在途操作"):
            temporary = None
            try:
                previous = read_document(root, "docs/tech-spec.md")
                if previous["sha256"] != expected_tech_sha:
                    raise ValueError("方案版本冲突；重新读取，不覆盖新版本")
                prd_document = read_document(root, "docs/PRD.md")
                if prd_document["sha256"] == "missing":
                    raise ValueError("缺少 docs/PRD.md；不能保存工程 tech-spec")
                if prd_document["sha256"] != expected_prd_sha:
                    raise ValueError("PRD 输入版本冲突；重新读取 PRD 和确认用途")
                prd_review = inspect_prd(foundation, project_id)
                if prd_review["status"] != "ready_for_review":
                    raise ValueError("PRD 结构尚不完整；先补齐 A 阶段再形成技术方案")
                confirmation_ids, _ = _prd_confirmations(root, prd_document["sha256"])
                if not confirmation_ids:
                    raise ValueError(
                        "PRD 尚无 Main 核验的‘形成技术方案’用途确认；不能保存 tech-spec"
                    )
                sources = {name: read_document(root, name)["sha256"] for name in SOURCE_DOCUMENTS}
                validate_source_digests(body, sources)
                rendered = _render(body, profile, prd_document["sha256"], confirmation_ids)
                raw = rendered.encode("utf-8")
                if digest(raw) == previous["sha256"]:
                    return {
                        "path": str(target),
                        "sha256": digest(raw),
                        "status": "Draft",
                        "profile": profile,
                        "changed": False,
                        "prd_sha256": prd_document["sha256"],
                        "prd_confirmation_ids": confirmation_ids,
                        "source_sha256": sources,
                    }
                docs = safe_path(root, "docs")
                docs.mkdir(exist_ok=True)
                if previous["content"] is not None:
                    history = safe_path(root, "docs/tech-spec-history")
                    history.mkdir(exist_ok=True)
                    archive_relative = f"docs/tech-spec-history/{previous['sha256']}.md"
                    archive = safe_path(root, archive_relative)
                    if archive.exists():
                        archived = read_document(root, archive_relative)
                        if archived["sha256"] != previous["sha256"]:
                            raise ValueError("方案历史版本冲突")
                    else:
                        with archive.open("x", encoding="utf-8") as stream:
                            stream.write(previous["content"])
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=docs, prefix=".tech-spec-", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                temporary = None
                return {
                    "path": str(target),
                    "sha256": digest(raw),
                    "status": "Draft",
                    "approval_verified": False,
                    "profile": profile,
                    "changed": True,
                    "prd_sha256": prd_document["sha256"],
                    "prd_confirmation_ids": confirmation_ids,
                    "index_update_required": True,
                    "source_sha256": sources,
                }
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("context")
    read.add_argument("project_id")
    check = commands.add_parser("inspect")
    check.add_argument("project_id")
    save = commands.add_parser("save-tech-spec-draft")
    save.add_argument("project_id")
    save.add_argument("--expected-tech-sha", required=True)
    save.add_argument("--expected-prd-sha", required=True)
    save.add_argument("--profile", required=True, choices=sorted(PROFILES))
    save.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "context":
            result = context(args.foundation, args.project_id)
        elif args.command == "inspect":
            result = inspect(args.foundation, args.project_id)
        elif not args.apply:
            raise ValueError("保存需要 --apply；正文通过标准输入传入")
        else:
            raw = sys.stdin.buffer.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("输入过大")
            result = save_tech_spec_draft(
                args.foundation,
                args.project_id,
                raw.decode("utf-8"),
                args.expected_tech_sha,
                args.expected_prd_sha,
                args.profile,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
