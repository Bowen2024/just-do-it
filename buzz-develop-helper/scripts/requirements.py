"""Project-scoped draft tools. No model calls, Git mutations or approvals."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from project_init import context as project_context, load_project

LIMIT = 128 * 1024
SOURCE_DOCUMENTS = ("project.json", "README.md")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def safe_path(root, relative):
    path = root
    for part in Path(relative).parts:
        if part in {"..", "/"}:
            raise ValueError("路径越界")
        path = path / part
        if path.is_symlink():
            raise ValueError("不允许通过软链读写项目文档")
    if not path.resolve().is_relative_to(root):
        raise ValueError("路径越界")
    return path


def read_document(root, relative):
    path = safe_path(root, relative)
    if not path.exists():
        return {"path": relative, "content": None, "sha256": "missing"}
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("文档不是独立普通文件")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("文档超过首版 128 KiB 限制")
    return {"path": relative, "content": raw.decode("utf-8"), "sha256": digest(raw)}


def context(foundation, project_id):
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    return {"project_id": project_id, "project_path": str(root),
            "documents": [read_document(root, p) for p in (
                "project.json", "README.md", "docs/requirements.md")],
            "approval_verified": False}


def validate_source_digests(body, sources):
    """Reject source SHA claims that disagree with the current project files."""
    for name, expected in sources.items():
        for line in body.splitlines():
            if name not in line or "sha" not in line.lower():
                continue
            match = re.search(r"sha(?:-?256)?\s*[：:]\s*`?([0-9a-z_-]+)", line, re.IGNORECASE)
            if match and match.group(1).lower() != expected:
                raise ValueError(f"{name} 来源摘要不匹配；重新读取项目背景")


def save_draft(foundation, project_id, body, expected):
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > LIMIT - 100:
        raise ValueError("草案必须是非空 UTF-8 文本，且小于 128 KiB")
    _, root = project_context(foundation, project_id)
    load_project(root, project_id)
    target = safe_path(root, "docs/requirements.md")
    lock = root / ".requirements.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError("需求写入锁已存在；先核对在途操作") from error
    os.close(fd)
    temporary = None
    try:
        previous = read_document(root, "docs/requirements.md")
        if previous["sha256"] != expected:
            raise ValueError("需求版本冲突；重新读取，不覆盖新版本")
        sources = {name: read_document(root, name)["sha256"] for name in SOURCE_DOCUMENTS}
        validate_source_digests(body, sources)
        rendered = "---\nstatus: Draft\napproval_verified: false\n---\n\n" + body.strip() + "\n"
        raw = rendered.encode("utf-8")
        if digest(raw) == previous["sha256"]:
            return {"path": str(target), "sha256": digest(raw), "status": "Draft", "changed": False,
                    "source_sha256": sources}
        docs = safe_path(root, "docs")
        docs.mkdir(exist_ok=True)
        if previous["content"] is not None:
            history = safe_path(root, "docs/requirements-history")
            history.mkdir(exist_ok=True)
            archive = safe_path(root, f"docs/requirements-history/{previous['sha256']}.md")
            if archive.exists():
                archived = read_document(root, archive.relative_to(root).as_posix())
                if archived["sha256"] != previous["sha256"]:
                    raise ValueError("历史版本冲突")
            else:
                with archive.open("x", encoding="utf-8") as stream:
                    stream.write(previous["content"])
        with tempfile.NamedTemporaryFile(mode="wb", dir=docs, prefix=".requirements-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        return {"path": str(target), "sha256": digest(raw), "status": "Draft", "changed": True,
                "approval_verified": False, "index_update_required": True,
                "source_sha256": sources}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("context")
    read.add_argument("project_id")
    save = commands.add_parser("save-draft")
    save.add_argument("project_id")
    save.add_argument("--expected-sha", required=True, help="context 返回的摘要；首次为 missing")
    save.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "context":
            result = context(args.foundation, args.project_id)
        elif not args.apply:
            raise ValueError("保存需要 --apply；正文通过标准输入传入")
        else:
            raw = sys.stdin.buffer.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("输入过大")
            result = save_draft(args.foundation, args.project_id, raw.decode("utf-8"), args.expected_sha)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
