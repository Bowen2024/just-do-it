"""Validate the mandatory design gate for a fusion unit. Read-only."""

import argparse
import json
from pathlib import Path
import re
import sys


REQUIRED_SECTIONS = (
    "上游来源",
    "原样继承",
    "Buzz 必要适配",
    "新增建议",
    "暂不建设",
    "验收范围",
    "来源追踪表",
)
PLACEHOLDERS = ("TODO", "TBD", "待补充", "待填写", "示例占位")
DECISION_STATES = ("待确认", "已确认", "已否决", "不采纳")
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$", re.MULTILINE)
NUMBERING_RE = re.compile(r"^\d+(?:\.\d+)*(?:[.、])?\s*")
UPSTREAM_RE = re.compile(
    r"(?:Develop_Helper/|upstream/develop-helper/)harness-core/[A-Za-z0-9_./-]+"
)


def normalize_heading(value):
    return NUMBERING_RE.sub("", value.strip()).strip("` ")


def sections(text):
    matches = list(HEADING_RE.finditer(text))
    result = {}
    for index, match in enumerate(matches):
        name = normalize_heading(match.group(2))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        if name in result:
            raise ValueError(f"设计门禁章节重复：{name}")
        result[name] = body
    return result


def require_content(name, body):
    if not body:
        raise ValueError(f"设计门禁章节为空：{name}")
    if any(marker in body for marker in PLACEHOLDERS):
        raise ValueError(f"设计门禁章节仍含占位内容：{name}")


def check_document(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("设计文档必须是普通文件，不能是软链")
    text = path.read_text(encoding="utf-8")
    found = sections(text)
    missing = [name for name in REQUIRED_SECTIONS if name not in found]
    if missing:
        raise ValueError("缺少设计门禁章节：" + "、".join(missing))
    for name in REQUIRED_SECTIONS:
        require_content(name, found[name])

    upstream_refs = sorted(set(UPSTREAM_RE.findall(found["上游来源"])))
    if not upstream_refs:
        raise ValueError("上游来源必须引用 Develop_Helper/harness-core 原文；阅读指南不能代替")

    suggestion_items = [
        line.strip() for line in found["新增建议"].splitlines()
        if line.lstrip().startswith("-")
    ]
    if not suggestion_items:
        raise ValueError("新增建议必须逐项记录；没有建议时明确写一项“不采纳”")
    for item in suggestion_items:
        if not any(state in item for state in DECISION_STATES):
            raise ValueError("每项新增建议必须标记待确认、已确认、已否决或不采纳")

    trace = found["来源追踪表"]
    for column in ("设计结论", "上游依据", "处理方式", "确认状态", "验收证据"):
        if column not in trace:
            raise ValueError(f"来源追踪表缺少列：{column}")

    return {
        "status": "pass",
        "document": str(path.resolve()),
        "required_sections": list(REQUIRED_SECTIONS),
        "upstream_reference_count": len(upstream_refs),
        "new_suggestion_item_count": len(suggestion_items),
        "note": "只验证设计门禁结构与显式来源，不替代语义评审、用户确认、实现测试或运行验收",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check_command = commands.add_parser("check")
    check_command.add_argument("document", type=Path)
    args = parser.parse_args()
    try:
        result = check_document(args.document)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
