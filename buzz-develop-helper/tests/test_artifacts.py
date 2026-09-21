import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_foundation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifacts
import project_init
import requirements


class ArtifactTests(unittest.TestCase):
    setUp = test_foundation.FoundationTests.setUp
    write_config = test_foundation.FoundationTests.write_config

    def project(self):
        project_init.create(self.app, "demo", "成果试点", "验证只读登记预览")
        root = (self.projects / "demo").resolve()
        requirements.save_draft(self.app, "demo", "# 需求 v0.1\n\n保持草案。", "missing")
        return root

    def preview(self, root, **changes):
        values = {
            "artifact_id": "requirements", "kind": "requirements", "version": "v0.1",
            "producer_role": "requirements", "purpose": "方案讨论", "summary": "首版需求草案",
            "path": "docs/requirements.md", "set_current": True,
        }
        values.update(changes)
        return artifacts.preview_register(self.app, "demo", **values)

    def materialize_registration(self, registry):
        for entry in registry["entries"].values():
            for version in entry["versions"]:
                version["registration"] = {
                    "actor": {"role": "main", "principal_id": "main-test",
                              "authority": "test-runtime"},
                    "recorded_at": "2026-09-19T12:00:00Z",
                }
        return registry

    def test_inspect_finds_unindexed_candidate_without_writes(self):
        root = self.project()
        before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        result = artifacts.inspect(self.app, "demo")
        after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["status"], "attention_required")
        self.assertEqual(result["issues"][0]["code"], "candidate_not_indexed")
        self.assertFalse(result["approval_checked"])

    def test_preview_is_read_only_and_keeps_draft_unconfirmed(self):
        root = self.project()
        before_project = (root / "project.json").read_bytes()
        before_readme = (root / "README.md").read_bytes()
        expected = hashlib.sha256((root / "docs/requirements.md").read_bytes()).hexdigest()
        result = self.preview(root)
        self.assertEqual(before_project, (root / "project.json").read_bytes())
        self.assertEqual(before_readme, (root / "README.md").read_bytes())
        self.assertEqual(result["artifact"]["content_sha256"], expected)
        version = result["proposed_changes"]["artifact_registry"]["entries"]["requirements"]["versions"][0]
        self.assertEqual(version["document_status"], "Draft")
        self.assertEqual(version["confirmation_ids"], [])
        self.assertIn("approval_verified=false", result["warnings"][1])
        self.assertEqual(result["proposed_changes"]["legacy_artifact_after"], "docs/requirements.md")

    def test_preview_removes_only_initializer_placeholder(self):
        root = self.project()
        readme = root / "README.md"
        readme.write_text(readme.read_text() + "\n用户手写说明。\n", encoding="utf-8")
        result = self.preview(root)
        preview = result["proposed_changes"]["readme"]
        self.assertTrue(preview["initializer_placeholder_removed"])
        self.assertIn("用户手写说明。", preview["proposed_content"])
        self.assertIn(artifacts.MARKER_START, preview["managed_block"])

    def test_historical_registration_requires_explicit_current(self):
        root = self.project()
        result = self.preview(root, set_current=False)
        entry = result["proposed_changes"]["artifact_registry"]["entries"]["requirements"]
        self.assertIsNone(entry["current_version"])
        self.assertEqual(result["operation"], "register_historical_version_requires_explicit_current")
        self.assertIsNone(result["proposed_changes"]["legacy_artifact_after"])

    def test_same_version_cannot_point_to_changed_content(self):
        root = self.project()
        proposal = self.materialize_registration(
            self.preview(root)["proposed_changes"]["artifact_registry"])
        data = json.loads((root / "project.json").read_text())
        data["artifact_registry"] = proposal
        data["artifacts"]["requirements"] = "docs/requirements.md"
        (root / "project.json").write_text(json.dumps(data), encoding="utf-8")
        (root / "docs/requirements.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "摘要不匹配"):
            self.preview(root)

    def test_symlink_artifact_is_rejected(self):
        root = self.project()
        link = root / "docs/linked.md"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "软链"):
            self.preview(root, path="docs/linked.md")
        self.assertEqual(self.source.read_text(), "original")

    def test_file_set_manifest_is_verified(self):
        root = self.project()
        ui = root / "ui"
        ui.mkdir()
        page = ui / "index.html"
        page.write_text("<h1>demo</h1>")
        sha = hashlib.sha256(page.read_bytes()).hexdigest()
        manifest = {"schema_version": 1, "entrypoint": "ui/index.html",
                    "files": [{"path": "ui/index.html", "sha256": sha}]}
        (ui / "artifact-manifest.json").write_text(json.dumps(manifest))
        result = self.preview(root, artifact_id="ui", kind="ui", version="demo-1",
                              producer_role="ui", purpose="客户演示", summary="演示页面",
                              path=None, manifest="ui/artifact-manifest.json")
        content = result["proposed_changes"]["artifact_registry"]["entries"]["ui"]["versions"][0]["content"]
        self.assertEqual(content["type"], "file-set")
        self.assertEqual(content["entrypoint"], "ui/index.html")
        page.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "摘要不匹配"):
            self.preview(root, artifact_id="ui", kind="ui", version="demo-1",
                         producer_role="ui", purpose="客户演示", summary="演示页面",
                         path=None, manifest="ui/artifact-manifest.json")

    def test_inconsistent_persisted_registry_is_rejected(self):
        root = self.project()
        data = json.loads((root / "project.json").read_text())
        registry = self.materialize_registration(
            self.preview(root)["proposed_changes"]["artifact_registry"])
        registry["entries"]["requirements"]["versions"][0]["content"]["sha256"] = "0" * 64
        data["artifact_registry"] = registry
        (root / "project.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "摘要不匹配"):
            artifacts.inspect(self.app, "demo")

    def test_inspect_detects_legacy_pointer_without_registry(self):
        root = self.project()
        extra = root / "docs/alternate.md"
        extra.write_text("alternate")
        data = json.loads((root / "project.json").read_text())
        data["artifacts"]["solution"] = "docs/alternate.md"
        (root / "project.json").write_text(json.dumps(data))
        result = artifacts.inspect(self.app, "demo")
        self.assertIn("legacy_pointer_not_registered", {item["code"] for item in result["issues"]})

    def test_inspect_detects_registry_legacy_projection_mismatch(self):
        root = self.project()
        data = json.loads((root / "project.json").read_text())
        data["artifact_registry"] = self.materialize_registration(
            self.preview(root)["proposed_changes"]["artifact_registry"])
        self.assertIsNone(data["artifacts"]["requirements"])
        (root / "project.json").write_text(json.dumps(data))
        result = artifacts.inspect(self.app, "demo")
        mismatch = [item for item in result["issues"] if item["code"] == "legacy_registry_mismatch"]
        self.assertEqual(mismatch[0]["registry_path"], "docs/requirements.md")

    def test_persisted_preview_identity_placeholder_is_rejected(self):
        root = self.project()
        data = json.loads((root / "project.json").read_text())
        data["artifact_registry"] = self.preview(root)["proposed_changes"]["artifact_registry"]
        (root / "project.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "运行时绑定 Main"):
            artifacts.inspect(self.app, "demo")

    def test_cli_exposes_no_apply_or_role_claim(self):
        root = self.project()
        before = (root / "project.json").read_bytes()
        script = Path(artifacts.__file__)
        result = subprocess.run([
            sys.executable, "-B", str(script), "--foundation", str(self.app),
            "preview-register", "demo", "--artifact-id", "requirements",
            "--kind", "requirements", "--version", "v0.1", "--producer-role", "requirements",
            "--purpose", "方案讨论", "--summary", "草案", "--path", "docs/requirements.md",
            "--set-current", "--apply"
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments: --apply", result.stderr)
        self.assertEqual(before, (root / "project.json").read_bytes())
        help_text = subprocess.run([sys.executable, "-B", str(script), "preview-register", "--help"],
                                   capture_output=True, text=True, check=True).stdout
        self.assertNotIn("--role", help_text)


if __name__ == "__main__":
    unittest.main()
