"""Step 1 dependency probe; not a UI runtime, loader contract or save tool.

Copies declared dependencies and upstream into a temporary layout. Runs the
probe again under a fresh isolated interpreter, then retains JSON evidence.
Only temporary fixture files are mutated. No frontend or MCP is started.
"""

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from types import ModuleType


MODULES = (
    "__init__", "check_foundation", "project_state", "project_init",
    "requirements", "project_info", "artifact_records",
    "confirmation_records", "recovery",
)
EXCLUDED = {".git", ".DS_Store", "__pycache__", "Projects_Repo", "node_modules", ".venv", "venv"}
ALIAS = "_ui_step1_probe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe_tree(root):
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = {"link": os.readlink(path)}
        elif path.is_file():
            result[name] = {"sha256": sha(path)}
        elif path.is_dir():
            result[name] = {"directory": True}
    return result


def load_one(name, path, package=False):
    spec = importlib.util.spec_from_file_location(
        name, path, submodule_search_locations=[str(path.parent)] if package else None,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    parent, _, member = name.rpartition(".")
    if parent in sys.modules:
        setattr(sys.modules[parent], member, module)
    return module


def load_modules(foundation):
    package = ModuleType(ALIAS)
    package.__path__ = [str(foundation)]
    sys.modules[ALIAS] = package
    loaded = {}
    for module in MODULES:
        full = f"{ALIAS}.file_tools" + ("" if module == "__init__" else f".{module}")
        loaded[module] = load_one(full, foundation / "file_tools" / f"{module}.py", module == "__init__")
    return loaded


def child(root, original, scenario):
    root, original = root.resolve(), original.resolve()
    foundation = root / "install/requirements"
    results, attempts = [], []

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path == original or original in path.parents:
                attempts.append({"event": event, "path": str(path)})
                raise AssertionError(f"source checkout access forbidden: {path}")
        if event == "subprocess.Popen":
            executable, command = args[0], args[1]
            if Path(executable).name != "git" or "rev-parse" not in command:
                raise AssertionError(f"unexpected subprocess: {executable}")

    sys.addaudithook(audit)

    def record(name, operation):
        try:
            details = operation()
            results.append({"check": name, "status": "pass", "details": details})
        except Exception as error:
            results.append({"check": name, "status": "fail", "error": f"{type(error).__name__}: {error}"})
            raise

    def require(value, message):
        if not value:
            raise AssertionError(message)

    def rejected(operation, contains):
        try:
            operation()
        except (OSError, ValueError, RuntimeError) as error:
            require(contains in str(error), f"unexpected rejection: {error}")
            return {"type": type(error).__name__, "message": str(error)}
        raise AssertionError("expected rejection did not occur")

    try:
        if scenario == "missing-module":
            record("missing_shared_module_no_fallback", lambda: rejected(
                lambda: load_modules(foundation), "artifact_records.py"))
        else:
            before = describe_tree(root)
            modules = load_modules(foundation)

            def imports():
                require(before == describe_tree(root), "module imports changed the fixture")
                origins = {name: str(Path(module.__file__).relative_to(root)) for name, module in modules.items()}
                require(all(Path(m.__file__).is_relative_to(foundation) for m in modules.values()), "wrong module origin")
                require(not any("site-packages" in p or "dist-packages" in p for p in sys.path), "third party path present")
                return {"origins": origins, "isolated": sys.flags.isolated, "no_site": sys.flags.no_site,
                        "dont_write_bytecode": sys.dont_write_bytecode}

            record("nine_file_imports_without_side_effects", imports)
            check, init, documents = (modules[n] for n in ("check_foundation", "project_init", "requirements"))
            state, info, artifacts, confirmations, recovery = (
                modules[n] for n in ("project_state", "project_info", "artifact_records", "confirmation_records", "recovery"))

            record("copied_foundation_config_lock_methods", lambda: check.check(foundation))

            def methods():
                links = [foundation / "methods/develop-helper", root / "install/UI/methods/develop-helper"]
                require(all(p.resolve(strict=True) == root / "upstream" for p in links), "method target differs")
                for relative in ("skills/sdd-product-design/phase-B.md", "skills/ui-design-standard/SKILL.md",
                                 "skills/ui-design-standard/references/ui-style-template.md"):
                    require((links[1] / "harness-core" / relative).read_text(), "empty UI method")
                return "both fixture links resolve to the copied upstream; three UI method files readable"

            record("fixture_UI_and_foundation_methods", methods)
            project = root / "projects/演示依赖验证"
            project_id = "ui-dependency-case"

            def create():
                value = init.create(foundation, project_id, "运行依赖临时夹具", "仅验证共享基础", info={
                    "project_type": "web", "target_platforms": ["web"], "specification": None,
                    "repository_plan": {"mode": "none"}})
                require(value["status"] == "local_files_ready" and not value["git_initialized"], "unexpected initialization")
                require(not (project / ".git").exists(), "Git initialized unexpectedly")
                return {"status": value["status"], "git_initialized": value["git_initialized"]}

            record("temporary_chinese_project_initialization_without_Git_mutation", create)
            record("project_context_binding", lambda: str(init.context(
                foundation, project_id, expected_root=project)[1]))
            record("wrong_project_binding_rejected", lambda: rejected(
                lambda: init.context(foundation, project_id, expected_root=root / "projects/wrong"), "不一致"))

            def reads():
                versions = documents.context(foundation, project_id, expected_root=project)
                require(len(versions["documents"]) == 4, "wrong requirement context")
                require(documents.read_document(project, "docs/PRD.md")["sha256"] == "missing", "missing PRD misreported")
                data = init.load_project(project, project_id)
                require(not info.report(data)["invalid"], "project choices invalid")
                require(info.resolve_specification(foundation, None)["status"] == "not_used", "null changed to default")
                require(info.resolve_specification(foundation, "default")["status"] == "selected", "specification not located")
                return "project/read/missing-document/recorded-choices/null and selected specification verified"

            record("document_and_project_choices_reads", reads)
            record("path_escape_rejected", lambda: rejected(
                lambda: documents.read_document(project, "../outside.md"), "越界"))

            demo = project / "docs/prototypes/demo"
            demo.mkdir(parents=True)
            for relative, raw in {
                "docs/ui-style.md": "# 临时设计说明\n".encode(),
                "docs/prototypes/demo/index.html": b"<!doctype html><title>dependency fixture only</title>",
                "docs/prototypes/demo/README.md": "仅供文件校验，不是实际演示。\n".encode(),
                "docs/prototypes/demo/data.bin": bytes([0, 127, 255]),
            }.items():
                (project / relative).write_bytes(raw)
            manifest = {"schema_version": 1, "entrypoint": "docs/prototypes/demo/index.html", "files": [
                {"path": relative, "sha256": sha(project / relative)} for relative in (
                    "docs/ui-style.md", "docs/prototypes/demo/index.html", "docs/prototypes/demo/README.md",
                    "docs/prototypes/demo/data.bin")]}
            (project / "ui").mkdir()
            manifest_path = project / "ui/artifact-manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False))

            def manifest_read():
                value = artifacts.read_manifest(project, "ui/artifact-manifest.json")
                require(value["type"] == "file-set" and len(value["files"]) == 4, "wrong collection")
                return {"type": value["type"], "members": len(value["files"]), "entrypoint": value["entrypoint"]}

            record("UI_collection_text_binary_and_entrypoint", manifest_read)
            index = demo / "index.html"
            original_index = index.read_bytes()
            index.write_bytes(original_index + b"changed")
            record("UI_member_digest_mismatch_rejected", lambda: rejected(
                lambda: artifacts.read_manifest(project, "ui/artifact-manifest.json"), "摘要不匹配"))
            index.write_bytes(original_index)
            link = demo / "linked.bin"
            link.symlink_to(demo / "data.bin")
            record("UI_symlink_member_rejected", lambda: rejected(
                lambda: artifacts.safe_project_file(project, "docs/prototypes/demo/linked.bin"), "软链"))

            def read_only_recovery():
                before = describe_tree(project)
                value = recovery.read(foundation, project, project_id)
                require(value["confirmations"]["status"] == "missing", "missing confirmation misreported")
                require(confirmations.read_decisions(project)[2] == "missing", "missing decisions misreported")
                require(artifacts.validate_registry(project, init.load_project(project, project_id)) == (None, []),
                        "missing registry misreported")
                require(before == describe_tree(project), "read-only recovery wrote files")
                return {"confirmation_status": value["confirmations"]["status"], "atomic_snapshot": value["atomic_snapshot"],
                        "writes": False, "UI_recovery_implemented": False}

            record("local_validators_and_missing_confirmation_recovery_are_read_only", read_only_recovery)

            def locks():
                with state.project_state_lock(project, "ui-dependency-probe"):
                    result = rejected(lambda: enter_lock(state, project), "锁已存在")
                require(not (project / state.LOCK_NAME).exists(), "probe lock remained")
                return result

            record("shared_lock_conflict_and_release", locks)

            def atomic():
                target = project / "ui/probe.txt"
                state.atomic_replace(target, b"old")
                state.atomic_replace(target, b"new")
                require(target.read_bytes() == b"new", "write/readback differs")
                return "single-file replacement only; not a UI multi-file transaction"

            record("shared_single_file_atomic_replace", atomic)
            config_path = foundation / "config/local.json"
            original_config = config_path.read_bytes()
            parked = config_path.with_suffix(".parked")
            config_path.rename(parked)
            record("missing_local_config_rejected", lambda: rejected(lambda: check.check(foundation), "local.json"))
            parked.rename(config_path)
            config = json.loads(original_config)
            config["projects_root"] = str(root / "upstream")
            config_path.write_text(json.dumps(config))
            record("overlapping_roots_rejected", lambda: rejected(lambda: check.check(foundation), "互相包含"))
            config_path.write_bytes(original_config)
            method = foundation / "methods/develop-helper"
            method.rename(method.with_name("develop-helper.parked"))
            record("missing_methods_link_rejected", lambda: rejected(lambda: check.check(foundation), "软链"))
            method.with_name("develop-helper.parked").rename(method)
            upstream_file = root / "upstream/harness-core/skills/sdd-product-design/phase-B.md"
            old = upstream_file.read_bytes()
            upstream_file.write_bytes(old + b"\nprobe drift\n")
            record("upstream_drift_rejected", lambda: rejected(lambda: check.check(foundation), "漂移"))
            upstream_file.write_bytes(old)
            record("restored_fixture_foundation_valid", lambda: check.check(foundation))

        def isolation():
            require(not attempts, "original checkout was accessed")
            loaded_names = [name for name in sys.modules if name.startswith(ALIAS + ".file_tools")]
            require(not any(name in sys.modules for name in ("scripts", "artifacts", "collaboration", "trusted_context")),
                    "legacy bare module loaded")
            require(not any("__pycache__" in str(path) for path in root.rglob("*")), "bytecode cache created")
            return {"source_access_attempts": attempts, "loaded_alias_modules": loaded_names,
                    "bytecode_cache_created": False, "third_party_site_loaded": "site" in sys.modules}

        record("fresh_process_no_source_or_legacy_fallback", isolation)
    except Exception as error:
        if not results or results[-1]["status"] != "fail":
            results.append({"check": "probe_infrastructure", "status": "fail",
                            "error": f"{type(error).__name__}: {error}"})
    report = {"scenario": scenario, "checks": results, "passed": all(r["status"] == "pass" for r in results)}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


def enter_lock(state, project):
    with state.project_state_lock(project, "ui-probe-conflict"):
        raise AssertionError("nested lock acquired")


def parent(output):
    source_root = Path(__file__).resolve().parents[4]
    foundation_source = source_root / "fusion-runtime/workflows/requirements"
    upstream_source = source_root / "Develop_Helper"
    source_index = {f"file_tools/{name}.py": sha(foundation_source / "file_tools" / f"{name}.py") for name in MODULES}
    protected = {**source_index, "upstream-lock.json": sha(foundation_source / "upstream-lock.json"),
                 "config/local.example.json": sha(foundation_source / "config/local.example.json")}
    real_config_existed = (foundation_source / "config/local.json").exists()
    config_digest = sha(foundation_source / "config/local.json") if real_config_existed else None
    method_target = os.readlink(foundation_source / "methods/develop-helper")
    snapshot_module = load_one("_ui_probe_snapshot", foundation_source / "file_tools/check_foundation.py")
    upstream_before = snapshot_module.snapshot(upstream_source)
    lock = json.loads((foundation_source / "upstream-lock.json").read_text())
    if upstream_before != lock:
        raise RuntimeError("actual upstream differs from the adopted foundation lock")
    actual_foundation_check = (snapshot_module.check(foundation_source) if real_config_existed else
                               {"status": "unavailable", "reason": "config/local.json missing"})
    static = {}
    local_names = set(MODULES) - {"__init__"}
    for name in MODULES:
        tree = ast.parse((foundation_source / "file_tools" / f"{name}.py").read_text())
        imports, external = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(x.name.split(".")[0] for x in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    imports.update([node.module.split(".")[0]] if node.module else [a.name for a in node.names])
                elif node.module:
                    imports.add(node.module.split(".")[0])
        external = imports - local_names - set(sys.stdlib_module_names)
        if external:
            raise RuntimeError(f"undeclared imports in {name}: {sorted(external)}")
        static[name] = sorted(imports)
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git executable missing")
    git_version = subprocess.run([git, "--version"], check=True, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="ui-runtime-dependency-") as temporary:
        root = Path(temporary).resolve()
        foundation = root / "install/requirements"
        (foundation / "file_tools").mkdir(parents=True)
        (foundation / "config").mkdir()
        (foundation / "methods").mkdir()
        for name in MODULES:
            shutil.copyfile(foundation_source / "file_tools" / f"{name}.py", foundation / "file_tools" / f"{name}.py")
        shutil.copyfile(foundation_source / "upstream-lock.json", foundation / "upstream-lock.json")
        shutil.copytree(upstream_source, root / "upstream", symlinks=True,
                        ignore=lambda directory, names: [n for n in names if n in EXCLUDED or n.endswith(".pyc")])
        if snapshot_module.snapshot(root / "upstream") != lock:
            raise RuntimeError("isolated upstream copy differs from lock")
        (root / "projects").mkdir()
        config = {"schema_version": 1, "upstream_root": str(root / "upstream"),
                  "projects_root": str(root / "projects"), "project_directories": {"ui-dependency-case": "演示依赖验证"}}
        (foundation / "config/local.json").write_text(json.dumps(config, ensure_ascii=False))
        (foundation / "methods/develop-helper").symlink_to(root / "upstream", target_is_directory=True)
        (root / "install/UI/methods").mkdir(parents=True)
        (root / "install/UI/methods/develop-helper").symlink_to(root / "upstream", target_is_directory=True)
        script = root / "dependency_probe.py"
        shutil.copyfile(Path(__file__), script)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("PYTHON", "GIT_")) and key not in {"VIRTUAL_ENV", "CONDA_PREFIX"}}
        runs = []
        for scenario in ("normal", "missing-module"):
            if scenario == "missing-module":
                (foundation / "file_tools/artifact_records.py").rename(foundation / "file_tools/artifact_records.parked")
            command = [sys.executable, "-I", "-S", "-B", str(script), "--child-root", str(root),
                       "--original-root", str(source_root), "--scenario", scenario]
            result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, timeout=60)
            if not result.stdout.strip():
                raise RuntimeError(f"probe produced no JSON: {result.stderr}")
            evidence = json.loads(result.stdout)
            evidence.update(exit_code=result.returncode, stderr=result.stderr)
            runs.append(evidence)
    upstream_after = snapshot_module.snapshot(upstream_source)
    source_unchanged = all(sha(foundation_source / name) == value for name, value in protected.items())
    source_unchanged = source_unchanged and (foundation_source / "config/local.json").exists() == real_config_existed
    if real_config_existed:
        source_unchanged = source_unchanged and sha(foundation_source / "config/local.json") == config_digest
    source_unchanged = source_unchanged and os.readlink(foundation_source / "methods/develop-helper") == method_target
    passed = all(run["passed"] and run["exit_code"] == 0 for run in runs) and source_unchanged and upstream_before == upstream_after
    evidence = {
        "scope": "UI step 1 proposed dependency closure only; not an implemented UI service",
        "verified_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "python": sys.version, "python_executable": sys.executable, "git": git_version, "git_executable": git,
        "isolation_flags": ["-I", "-S", "-B"], "source_index": source_index, "static_imports": static,
        "actual_upstream": upstream_before, "matches_upstream_lock": upstream_before == lock,
        "real_local_config_exists": real_config_existed, "real_UI_methods_link_exists":
            (source_root / "fusion-runtime/workflows/UI/methods/develop-helper").exists(),
        "real_local_config_sha256": config_digest, "actual_foundation_check": actual_foundation_check,
        "temporary_fixture_config_only": True, "protected_foundation_unchanged": source_unchanged,
        "upstream_unchanged": upstream_before == upstream_after, "temporary_fixture_removed": True,
        "runs": runs, "check_count": sum(len(run["checks"]) for run in runs), "passed": passed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": passed, "checks": evidence["check_count"], "evidence": str(output),
                      "failed_checks": [r for run in runs for r in run["checks"] if r["status"] != "pass"]}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child-root", type=Path)
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--scenario", choices=("normal", "missing-module"), default="normal")
    args = parser.parse_args()
    if args.child_root:
        sys.exit(child(args.child_root, args.original_root, args.scenario))
    if args.output is None:
        parser.error("--output is required for the parent probe")
    sys.exit(parent(args.output.resolve()))
