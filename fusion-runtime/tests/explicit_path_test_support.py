import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys

from solution_test_support import SOLUTION_SOURCE, SolutionFixture
from test_ui_accept import AcceptFixture
from ui_test_support import tree_snapshot


class McpChild:
    def __init__(self, fixture, command, *, role="unknown"):
        self.closed = False
        self.role = role
        self._fixture = fixture
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=fixture.outside,
            env=fixture.scrubbed_env(),
        )
        fixture.addCleanup(self.close)
        self.identifier = 0
        self.sequence = 0
        self.evidence_dir = fixture.child_evidence_dir(role, self.process.pid)
        self.business_before = fixture.business_snapshots()
        self.config_before = fixture.config_evidence()
        self.record_process("started", command=command, cwd=str(fixture.outside))
        self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
        })
        self.notify("notifications/initialized")

    @property
    def pid(self):
        return self.process.pid

    def request(self, method, params=None):
        self.identifier += 1
        self.sequence += 1
        message = {
            "jsonrpc": "2.0",
            "id": self.identifier,
            "method": method,
            "params": params or {},
        }
        self.record_rpc("request", message)
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
        self.process.stdin.flush()
        ready = select.select([self.process.stdout], [], [], 10)[0]
        if not ready:
            raise AssertionError(f"stdio response timeout: {method}")
        response = json.loads(self.process.stdout.readline())
        self.record_rpc("response", response)
        if "error" in response:
            raise AssertionError(response)
        return response["result"]

    def notify(self, method, params=None):
        self.sequence += 1
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self.record_rpc("notification", message)
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()

    def record_rpc(self, kind, message):
        if self.evidence_dir is None:
            return
        entry = {
            "sequence": self.sequence,
            "pid": self.process.pid,
            "role": self.role,
            "kind": kind,
            "message": message,
        }
        with (self.evidence_dir / "rpc.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def record_process(self, event, **details):
        if self.evidence_dir is None:
            return
        payload = {
            "event": event,
            "pid": self.process.pid,
            "role": self.role,
            "config": self.config_before if event == "started" else self.fixture_config(),
            "business_before": self.business_before,
            **details,
        }
        if event == "closed":
            payload["business_after"] = self.fixture_business()
        (self.evidence_dir / f"{event}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def fixture_config(self):
        return self._fixture.config_evidence()

    def fixture_business(self):
        return self._fixture.business_snapshots()

    def tools(self):
        return [item["name"] for item in self.request("tools/list")["tools"]]

    def call(self, name, arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        return result["isError"], json.loads(result["content"][0]["text"])

    def ok(self, name, arguments):
        is_error, payload = self.call(name, arguments)
        if is_error:
            raise AssertionError(payload)
        return payload

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        if self.process.poll() is None:
            self.process.wait(timeout=10)
        stderr = self.process.stderr.read().decode() if self.process.stderr else ""
        self.record_process(
            "closed", returncode=self.process.returncode, stderr=stderr,
        )
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()
        if self.process.returncode != 0:
            raise AssertionError(f"stdio exited {self.process.returncode}: {stderr}")


class ExplicitStdioFixture(AcceptFixture):
    def setUp(self):
        super().setUp()
        self.solution = self.install / "Solution Designer"
        shutil.copytree(
            SOLUTION_SOURCE,
            self.solution,
            ignore=shutil.ignore_patterns(
                ".DS_Store", "__pycache__", "*.pyc", "methods", "research-template.md"
            ),
        )
        reference = self.upstream / "harness-core/skills/sdd-product-design/references"
        reference.mkdir(parents=True, exist_ok=True)
        (reference / "research-template.md").write_text("# Research\n", encoding="utf-8")
        (self.solution / "methods").mkdir(exist_ok=True)
        (self.solution / "methods/develop-helper").symlink_to(
            self.upstream, target_is_directory=True
        )
        (self.solution / "templates/research-template.md").symlink_to(
            "../methods/develop-helper/harness-core/skills/sdd-product-design/"
            "references/research-template.md"
        )
        self.relock_upstream()
        self.project_p1 = self.root / "external-a/nested/采购 需求预测"
        self.project_p2 = self.root / "external-b/another/采购 需求预测"
        self.project_a = self.project_p1
        self.project_b = self.project_p2
        self.config["project_path_mode"] = "explicit"
        self.config["projects_root"] = str(self.root / "missing-old-root")
        self.config["project_directories"] = {"stale": "../old-mapping"}
        self.write_config()
        self.init_explicit_project(self.project_p1, "persisted-a")
        self.init_explicit_project(self.project_p2, "persisted-b")

    write_requirements_and_prd = SolutionFixture.write_requirements_and_prd
    requirements_body = SolutionFixture.requirements_body
    prd_body = SolutionFixture.prd_body
    confirm_prd = SolutionFixture.confirm_prd
    tech_spec = SolutionFixture.tech_spec

    def spawn_role(self, role, *, initialize=False, save=False, write=False, import_roots=()):
        if role == "requirements":
            command = [
                sys.executable, "-B", str(self.foundation / "cursor_mcp.py"),
                "--foundation", str(self.foundation),
            ]
            if initialize:
                command.append("--allow-initialize")
            if save:
                command.append("--allow-save")
        elif role == "solution":
            command = [
                sys.executable, "-B", str(self.solution / "mcp_server.py"),
                "--foundation", str(self.foundation),
            ]
            if save:
                command.append("--allow-save")
        elif role == "ui":
            command = [
                sys.executable, "-B", str(self.ui / "mcp_server.py"),
                "--foundation", str(self.foundation),
            ]
            if write:
                command.append("--allow-write")
            for root in import_roots:
                command.extend(["--import-root", str(root)])
        else:
            raise ValueError(role)
        return McpChild(self, command, role=role)

    def child_evidence_dir(self, role, pid):
        root = os.environ.get("EXPLICIT_PATH_EVIDENCE_ROOT")
        if not root:
            return None
        test_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", self._testMethodName)
        path = Path(root) / "rpc" / test_name / f"{role}-{pid}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def config_evidence(self):
        path = self.foundation / "config/local.json"
        return {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "content": json.loads(path.read_text(encoding="utf-8")),
        }

    def business_snapshots(self):
        roots = {
            "legacy_projects": self.projects,
            "external_a": self.root / "external-a",
            "external_b": self.root / "external-b",
            "external_c": self.root / "external-c",
        }
        result = {}
        for name, root in roots.items():
            stat = root.stat() if root.exists() else None
            result[name] = {
                "path": str(root),
                "identity": [stat.st_dev, stat.st_ino] if stat else None,
                "mtime_ns": stat.st_mtime_ns if stat else None,
                "ctime_ns": stat.st_ctime_ns if stat else None,
                "tree": tree_snapshot(root),
            }
        return result

    def use_path_mode(self, mode, *, mapping=None):
        if mode == "E":
            self.config["project_path_mode"] = "explicit"
            self.config["projects_root"] = str(self.root / "missing-old-root")
        elif mode == "L0":
            self.config.pop("project_path_mode", None)
            self.config["projects_root"] = str(self.projects)
        elif mode == "L1":
            self.config["project_path_mode"] = "legacy_rooted"
            self.config["projects_root"] = str(self.projects)
        else:
            raise ValueError(mode)
        self.config["project_directories"] = (
            dict(mapping) if mapping is not None else
            {"procurement-demo": "采购演示", "meeting-b": "会议助手"}
        )
        self.write_config()

    def requirements_read(self, child, project, **arguments):
        return child.ok("requirements_read_context", {
            "project_path": str(project), **arguments,
        })

    def requirements_save(self, child, project, content, read):
        return child.ok("requirements_save_draft", {
            "project_path": str(project), "content": content, "read_id": read["read_id"],
        })

    def solution_read(self, child, project, **arguments):
        return child.ok("solution_read_context", {
            "project_path": str(project), **arguments,
        })

    def solution_save(self, child, project, content, read, profile="Lite"):
        return child.ok("solution_save_tech_spec_draft", {
            "project_path": str(project),
            "read_id": read["read_receipt"]["read_id"],
            "content": content,
            "profile": profile,
        })

    def ui_flow(self, child, project, *, mode="empty", files=None,
                history_revision=None, import_source=None):
        from test_ui_accept import candidate_files, edit_candidate, request_id

        arguments = {"project_path": str(project)}
        if import_source is not None:
            arguments["import_source"] = import_source
        read = child.ok("ui_read_context", arguments)
        prepare_arguments = {
            "project_path": str(project),
            "read_id": read["read_id"],
            "request_id": request_id(),
            "mode": mode,
        }
        if history_revision is not None:
            prepare_arguments["history_revision"] = history_revision
        prepared = child.ok("ui_prepare_revision", prepare_arguments)
        edit_candidate(prepared["workspace_path"], files or candidate_files())
        inspected = child.ok("ui_inspect", {
            "project_path": str(project),
            "target": "candidate",
            "revision_id": prepared["revision_id"],
        })
        if inspected["state"] != "candidate_ready":
            raise AssertionError(inspected)
        accept_arguments = {
            "project_path": str(project),
            "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"],
            "request_id": request_id(),
            "delete_paths": inspected["changes"]["removed"],
        }
        accepted = child.ok("ui_accept_revision", accept_arguments)
        history = child.ok("ui_read_history", {"project_path": str(project)})
        return {
            "read": read,
            "prepared": prepared,
            "inspected": inspected,
            "accepted": accepted,
            "accept_arguments": accept_arguments,
            "history": history,
        }
