"""Bind one explicit project directory to its persistent identity."""

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat

if __package__:
    from . import check_foundation
else:
    import check_foundation


SHARED_MODULE_FILES = (
    "__init__.py",
    "check_foundation.py",
    "project_binding.py",
    "project_state.py",
    "project_init.py",
    "requirements.py",
    "project_info.py",
    "recovery.py",
    "confirmation_records.py",
    "artifact_records.py",
)
PROJECT_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


@dataclass(frozen=True)
class ProjectBinding:
    foundation: Path
    mode: str
    requested_path: str
    root: Path
    project_id: str
    identity_source: str
    state: str
    parent_identity: tuple
    root_identity: tuple | None
    environment_fingerprint: str
    protected_roots: tuple


def require_project_id(project_id):
    if not isinstance(project_id, str) or PROJECT_ID.fullmatch(project_id) is None:
        raise ValueError("项目 ID 须为 1–64 位小写字母、数字或连字符，首位不能是连字符")
    return project_id


def project_directories(config):
    mapping = config.get("project_directories", {})
    if not isinstance(mapping, dict):
        raise ValueError("project_directories 必须是项目编号到目录名的对象")
    for identifier, directory in mapping.items():
        require_project_id(identifier)
        if (not isinstance(directory, str) or not directory or directory != directory.strip()
                or directory in {".", ".."} or "/" in directory or "\\" in directory
                or any(ord(char) < 32 or ord(char) == 127 for char in directory)):
            raise ValueError("项目映射必须是业务父目录下的单层目录名")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("不同项目编号不能映射到同一目录")
    for identifier, directory in mapping.items():
        if (directory != identifier and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", directory)
                and mapping.get(directory, directory) == directory):
            raise ValueError("项目映射与另一个编号的默认目录冲突")
    return dict(mapping)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _foundation_path(foundation):
    value = getattr(foundation, "foundation", foundation)
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("foundation 必须是绝对目录")
    return path.resolve(strict=True)


def _identity(path):
    info = path.stat(follow_symlinks=False)
    return info.st_dev, info.st_ino


def _environment_fingerprint(foundation):
    config_path = foundation / "config/local.json"
    lock_path = foundation / "upstream-lock.json"
    modules = {
        name: _sha256(foundation / "file_tools" / name)
        for name in SHARED_MODULE_FILES
    }
    methods = foundation / check_foundation.METHODS_LINK
    payload = {
        "config_sha256": _sha256(config_path),
        "upstream_lock_sha256": _sha256(lock_path),
        "shared_modules_sha256": modules,
        "methods_link": os.readlink(methods),
        "methods_target": str(methods.resolve(strict=True)),
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def environment_fingerprint(foundation):
    foundation = _foundation_path(foundation)
    check_foundation.check(foundation)
    return _environment_fingerprint(foundation)


def _protected_roots(foundation, config, extra):
    values = [
        foundation,
        foundation.parent / "Solution Designer",
        foundation.parent / "UI",
        check_foundation.configured_directory(config, "upstream_root"),
        *extra,
    ]
    roots = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("受保护目录必须是绝对路径")
        resolved = path.resolve(strict=False)
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _reject_protected(root, protected_roots):
    for protected in protected_roots:
        if check_foundation.overlaps(root, protected):
            raise ValueError(f"项目目录不得与工具或上游目录重叠：{protected}")


def _normalize_path(project_path):
    if not isinstance(project_path, str) or not project_path.strip():
        raise ValueError("project_path 必须是非空绝对路径字符串")
    if any(ord(char) < 32 or ord(char) == 127 for char in project_path):
        raise ValueError("project_path 不得包含控制字符")
    supplied = Path(project_path)
    if not supplied.is_absolute() or ".." in supplied.parts:
        raise ValueError("project_path 必须是不含 .. 的绝对路径")
    if os.path.lexists(supplied) and supplied.is_symlink():
        raise ValueError("项目根目录不得是软链或断链")
    if supplied.exists() and not supplied.is_dir():
        raise ValueError("project_path 必须是项目目录，不能是普通文件或其他文件类型")
    try:
        parent = supplied.parent.resolve(strict=True)
    except OSError as error:
        raise ValueError("项目父目录必须存在且可读取；不递归创建未知父链") from error
    if not parent.is_dir():
        raise ValueError("项目父路径必须是已存在目录")
    try:
        root = supplied.resolve(strict=True) if supplied.exists() else parent / supplied.name
    except OSError as error:
        raise ValueError("项目目录无法稳定解析；拒绝绑定") from error
    return supplied, root, _identity(parent), _identity(root) if root.exists() else None


def _persistent_identity(root):
    metadata = root / "project.json"
    if not os.path.lexists(metadata):
        return None
    info = metadata.lstat()
    if metadata.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("project.json 必须是独立普通文件，不能是软链、硬链或其他文件类型")
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("project.json 不可读或 JSON 损坏；不降级为新项目") from error
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("project.json 格式版本不受支持；不降级为新项目")
    return require_project_id(data.get("project_id"))


def _suggested_identity(root, requested_project_id):
    if requested_project_id is not None:
        return require_project_id(requested_project_id), "explicit"
    if PROJECT_ID.fullmatch(root.name):
        return root.name, "directory_name"
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:24]
    return "req-" + digest, "path_digest"


def _legacy_context(config, supplied, root):
    projects_root = check_foundation.configured_directory(config, "projects_root")
    if supplied.parent != projects_root or root.parent != projects_root:
        raise ValueError("项目必须是配置的业务根目录下的直接子目录，且不能是软链")
    mapping = project_directories(config)
    identifier = next((key for key, directory in mapping.items() if directory == root.name), None)
    return mapping, identifier


def bind_project(foundation, project_path, *, allow_uninitialized=False,
                 requested_project_id=None, protected_roots=()):
    foundation = _foundation_path(foundation)
    check_foundation.check(foundation)
    config = check_foundation.read_json(foundation / "config/local.json")
    mode = check_foundation.project_path_mode(config)
    supplied, root, parent_identity, root_identity = _normalize_path(project_path)
    protected = _protected_roots(foundation, config, protected_roots)
    _reject_protected(root, protected)
    legacy_mapping, legacy_identifier = ({}, None)
    if mode == "legacy_rooted":
        legacy_mapping, legacy_identifier = _legacy_context(config, supplied, root)
    persisted = _persistent_identity(root)
    if persisted is not None:
        if legacy_identifier is not None and legacy_identifier != persisted:
            raise ValueError("项目目录映射与持久身份冲突")
        project_id, identity_source, state = persisted, "persisted", "initialized"
        if requested_project_id is not None and require_project_id(requested_project_id) != persisted:
            raise ValueError("项目已初始化，请求编号与持久身份冲突")
    else:
        if legacy_identifier is not None:
            if requested_project_id is not None and require_project_id(requested_project_id) != legacy_identifier:
                raise ValueError("请求编号与既有目录映射冲突")
            project_id, identity_source = legacy_identifier, "mapping"
        else:
            project_id, identity_source = _suggested_identity(root, requested_project_id)
        if not root.exists():
            state = "missing"
        elif any(root.iterdir()):
            state = "nonempty_uninitialized"
        else:
            state = "empty"
    if mode == "legacy_rooted":
        if project_id in legacy_mapping and legacy_mapping[project_id] != root.name:
            raise ValueError("项目编号与既有目录映射冲突")
        if (root.name != project_id and project_id not in legacy_mapping
                and os.path.lexists(root.parent / project_id)):
            raise ValueError("项目编号的默认目录已存在，不能绑定其他目录")
    if state != "initialized" and not allow_uninitialized:
        raise ValueError(f"项目未初始化：{state}")
    return ProjectBinding(
        foundation=foundation,
        mode=mode,
        requested_path=str(supplied),
        root=root,
        project_id=project_id,
        identity_source=identity_source,
        state=state,
        parent_identity=parent_identity,
        root_identity=root_identity,
        environment_fingerprint=_environment_fingerprint(foundation),
        protected_roots=protected,
    )


def _verify_environment(binding):
    check_foundation.check(binding.foundation)
    if _environment_fingerprint(binding.foundation) != binding.environment_fingerprint:
        raise ValueError("运行基线已变化；旧项目绑定和读取引用失效")


def _verify_location(binding):
    _, root, parent_identity, root_identity = _normalize_path(binding.requested_path)
    if root != binding.root or parent_identity != binding.parent_identity:
        raise ValueError("项目或父路径已改绑；停止后续操作")
    if root_identity != binding.root_identity:
        raise ValueError("项目目录身份已变化；停止后续操作")
    _reject_protected(root, binding.protected_roots)


def revalidate(binding, *, require_initialized=False, allow_initialization_lock=False):
    if not isinstance(binding, ProjectBinding):
        raise ValueError("无效项目绑定")
    _verify_environment(binding)
    _verify_location(binding)
    persisted = _persistent_identity(binding.root)
    has_members = binding.root.exists() and any(
        not (allow_initialization_lock and binding.state == "empty"
             and entry.name == ".project-state.lock")
        for entry in binding.root.iterdir()
    )
    current_state = "initialized" if persisted is not None else (
        "missing" if not binding.root.exists() else
        "nonempty_uninitialized" if has_members else "empty"
    )
    if current_state != binding.state:
        raise ValueError("项目初始化状态未经 bind_initialized 提升；拒绝沿用旧绑定")
    if binding.state == "initialized" and persisted != binding.project_id:
        raise ValueError("项目持久身份已变化；停止后续操作")
    if require_initialized and binding.state != "initialized":
        raise ValueError("项目尚未通过 bind_initialized 建立持久绑定")


def bind_initialized(binding):
    if binding.state == "initialized":
        revalidate(binding, require_initialized=True)
        return binding
    if binding.state not in {"missing", "empty"}:
        raise ValueError("非空未初始化目录不能提升为项目绑定")
    _verify_environment(binding)
    _, root, parent_identity, root_identity = _normalize_path(binding.requested_path)
    if root != binding.root or parent_identity != binding.parent_identity:
        raise ValueError("初始化期间项目或父路径已改绑")
    if binding.root_identity is not None and root_identity != binding.root_identity:
        raise ValueError("初始化期间项目目录已被替换")
    if root_identity is None:
        raise ValueError("初始化后项目目录仍不存在")
    persisted = _persistent_identity(root)
    if persisted is None or persisted != binding.project_id:
        raise ValueError("初始化后的持久身份与本次绑定不一致")
    return replace(
        binding,
        project_id=persisted,
        identity_source="persisted",
        state="initialized",
        root_identity=root_identity,
    )


def binding_fingerprint(binding):
    payload = {
        "foundation": str(binding.foundation),
        "mode": binding.mode,
        "requested_path": binding.requested_path,
        "root": str(binding.root),
        "project_id": binding.project_id,
        "identity_source": binding.identity_source,
        "state": binding.state,
        "parent_identity": list(binding.parent_identity),
        "root_identity": list(binding.root_identity) if binding.root_identity is not None else None,
        "environment_fingerprint": binding.environment_fingerprint,
        "protected_roots": [str(path) for path in binding.protected_roots],
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()
