import json
from pathlib import Path
import shutil
import sys
from unittest import mock

from test_ui_accept import AcceptFixture, APP, candidate_files, edit_candidate, request_id
from ui_test_support import DEFAULT_ROOT, DESIGN_PATH, MANIFEST_PATH, STATE_DIR, canonical, sha, tree_snapshot


class ExplicitUiFixture(AcceptFixture):
    def setUp(self):
        super().setUp()
        self.project_p1 = self.root / "external-a/nested/采购 UI"
        self.project_p2 = self.root / "external-b/another/采购 UI"
        self.config["project_path_mode"] = "explicit"
        self.config["projects_root"] = str(self.root / "missing-old-root")
        self.config["project_directories"] = {"stale": "../old-mapping"}
        self.write_config()
        self.init_explicit_project(self.project_p1, "shared-ui-id")
        self.init_explicit_project(self.project_p2, "shared-ui-id")

    def prepare_import_ready(self):
        self.write_inputs()
        self.write_import_case()
        self.connect(import_roots=[self.import_parent.parent], allow_write=True)
        read = self.read_context(import_source=self.import_source())
        prepared = self.prepare(read["read_id"], request_id(), "import")
        inspected = self.inspect_candidate(prepared["revision_id"])
        self.assertEqual(inspected["state"], "candidate_ready", inspected["issues"])
        return prepared, inspected

    def interrupt_import_accept(self):
        prepared, inspected = self.prepare_import_ready()
        self.server.tools.failpoint = lambda event, _context: (
            (_ for _ in ()).throw(RuntimeError("injected"))
            if event == "member_after:0" else None)
        rejected = self.call(self.mcp.ACCEPT, {
            "project_path": str(self.project_p1),
            "revision_id": prepared["revision_id"],
            "inspection_id": inspected["inspection_id"],
            "request_id": request_id(),
            "delete_paths": [],
        }, error=True)
        self.server.tools.failpoint = None
        return rejected["error"]["details"]["transaction_id"]


class ExplicitLifecycleTests(ExplicitUiFixture):
    def test_six_tools_alternate_same_id_projects_without_sharing_history(self):
        self.write_inputs(self.project_p1)
        self.write_inputs(self.project_p2)
        self.connect(allow_write=True)
        first_prepared, first_inspected = self.prepare_ready()
        first = self.accept_ready(first_prepared, first_inspected)
        second_files = candidate_files()
        second_files[APP] = "const project='B';\n"
        second_read = self.read_context(project=self.project_p2)
        second_prepared = self.prepare(
            second_read["read_id"], request_id(), project=self.project_p2)
        edit_candidate(second_prepared["workspace_path"], second_files)
        second_inspected = self.inspect_candidate(
            second_prepared["revision_id"], project=self.project_p2)
        second = self.accept(
            second_prepared["revision_id"], second_inspected["inspection_id"],
            request_id(), project=self.project_p2)
        self.assertNotEqual(first["current_revision"], second["current_revision"])
        self.assertEqual(self.read_history()["versions"][0]["revision_sha256"],
                         first["current_revision"])
        self.assertEqual(self.read_history(project=self.project_p2)["versions"][0]["revision_sha256"],
                         second["current_revision"])
        self.assertEqual(self.inspect("current")["state"], "stable")
        self.assertEqual(self.inspect("current", project=self.project_p2)["state"], "stable")
        self.assertEqual((self.project_p1 / APP).read_text(), candidate_files()[APP])
        self.assertEqual((self.project_p2 / APP).read_text(), second_files[APP])
        self.assertFalse((self.project_p1 / self.project_p1.name).exists())

    def test_cross_project_read_and_inspection_credentials_do_not_get_consumed(self):
        self.write_inputs(self.project_p1)
        self.write_inputs(self.project_p2)
        self.connect(allow_write=True)
        read = self.read_context()
        rejected_read = self.prepare(
            read["read_id"], request_id(), project=self.project_p2, identifier=30, error=True)
        self.assertEqual(rejected_read["error"]["code"], "read_invalid")
        prepared, inspected = self.prepare_ready()
        before_b = tree_snapshot(self.project_p2)
        rejected_inspect = self.accept(
            prepared["revision_id"], inspected["inspection_id"], request_id(),
            project=self.project_p2, identifier=31, error=True)
        self.assertEqual(rejected_inspect["error"]["code"], "inspection_invalid")
        self.assertEqual(tree_snapshot(self.project_p2), before_b)
        accepted = self.accept_ready(prepared, inspected)
        self.assertEqual(accepted["write_outcome"], "saved")

    def test_root_replacement_invalidates_credentials_and_candidate_binding(self):
        self.write_inputs()
        self.connect(allow_write=True)
        stale_read = self.read_context()
        prepared, inspected = self.prepare_ready()
        moved = self.project_p1.parent / "original-ui"
        self.project_p1.rename(moved)
        shutil.copytree(moved, self.project_p1)
        rejected_read = self.prepare(stale_read["read_id"], request_id(), identifier=32, error=True)
        self.assertEqual(rejected_read["error"]["code"], "read_invalid")
        rejected_candidate = self.call(self.mcp.INSPECT, {
            "project_path": str(self.project_p1), "target": "candidate",
            "revision_id": prepared["revision_id"]}, error=True)
        self.assertEqual(rejected_candidate["error"]["code"], "transaction_invalid")
        rejected_accept = self.accept(
            prepared["revision_id"], inspected["inspection_id"], request_id(), identifier=33,
            error=True)
        self.assertEqual(rejected_accept["error"]["code"], "inspection_invalid")
        self.assertFalse((self.project_p1 / MANIFEST_PATH).exists())
        self.assertFalse((moved / MANIFEST_PATH).exists())

    def test_lock_entry_directory_replacement_stops_before_candidate_write(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        project_state = self.server.tools.runtime.modules.project_state
        original_lock = project_state.project_state_lock
        moved = self.project_p1.parent / "locked-original"

        class ReplacingLock:
            def __init__(self, lock):
                self.lock = lock

            def __enter__(self):
                self.lock.__enter__()
                self.project.rename(moved)
                shutil.copytree(moved, self.project)

            def __exit__(self, *args):
                return self.lock.__exit__(*args)

        wrapper = ReplacingLock
        wrapper.project = self.project_p1
        project_state.project_state_lock = lambda root, label: wrapper(original_lock(root, label))
        rejected = self.prepare(read["read_id"], request_id(), identifier=34, error=True)
        self.assertEqual(rejected["error"]["code"], "binding_changed")
        self.assertFalse((self.project_p1 / STATE_DIR / "work").exists())
        self.assertFalse((moved / STATE_DIR / "work").exists())

    def test_runtime_change_invalidates_existing_read_id(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        self.config["unrelated_probe"] = "changed"
        self.write_config()
        rejected = self.prepare(read["read_id"], request_id(), identifier=35, error=True)
        self.assertEqual(rejected["error"]["code"], "runtime_baseline_changed")
        self.assertFalse((self.project_p1 / STATE_DIR / "work").exists())

    def test_explicit_path_rejections_have_no_business_side_effects(self):
        self.connect(allow_write=True)
        cases = (
            (self.foundation, "path_not_allowed"),
            (self.ui, "path_not_allowed"),
            (self.upstream, "path_not_allowed"),
            (self.project_p1 / "docs", "project_not_initialized"),
            (self.root / "missing-parent/project", "path_not_allowed"),
            (self.project_p1 / "../other", "path_not_allowed"),
        )
        before = tree_snapshot(self.root)
        for path, code in cases:
            with self.subTest(path=path, code=code):
                rejected = self.call(self.mcp.READ_CONTEXT, {
                    "project_path": str(path)}, error=True)
                self.assertEqual(rejected["error"]["code"], code)
        self.assertEqual(tree_snapshot(self.root), before)


class ExplicitPersistentBindingTests(ExplicitUiFixture):
    def test_copied_candidate_cannot_be_consumed_in_same_id_copy(self):
        self.write_inputs(self.project_p1)
        self.write_inputs(self.project_p2)
        self.connect(allow_write=True)
        prepared, _inspected = self.prepare_ready()
        source = Path(prepared["workspace_path"])
        target = self.project_p2 / STATE_DIR / "work" / prepared["revision_id"]
        target.parent.mkdir(parents=True)
        shutil.copytree(source, target)
        before_a = tree_snapshot(self.project_p1)
        before_b = tree_snapshot(self.project_p2)
        rejected = self.inspect_candidate(
            prepared["revision_id"], project=self.project_p2, error=True)
        self.assertEqual(rejected["error"]["code"], "transaction_invalid")
        self.assertEqual(tree_snapshot(self.project_p1), before_a)
        self.assertEqual(tree_snapshot(self.project_p2), before_b)

    def test_copied_transaction_cannot_be_inspected_or_recovered_in_same_id_copy(self):
        self.write_inputs(self.project_p1)
        self.write_inputs(self.project_p2)
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready()
        self.server.tools.failpoint = lambda event, _context: (
            (_ for _ in ()).throw(RuntimeError("injected"))
            if event == "member_after:0" else None)
        rejected = self.accept(
            prepared["revision_id"], inspected["inspection_id"], request_id(), identifier=36,
            error=True)
        self.server.tools.failpoint = None
        transaction_id = rejected["error"]["details"]["transaction_id"]
        shutil.copytree(self.project_p1 / "ui", self.project_p2 / "ui")
        before_a = tree_snapshot(self.project_p1)
        before_b = tree_snapshot(self.project_p2)
        inspected_copy = self.call(self.mcp.INSPECT, {
            "project_path": str(self.project_p2), "target": "transaction",
            "transaction_id": transaction_id}, error=True)
        self.assertEqual(inspected_copy["error"]["code"], "transaction_invalid")
        recovered_copy = self.recover(
            transaction_id, request_id(), "rollback", project=self.project_p2, identifier=37,
            error=True)
        self.assertEqual(recovered_copy["error"]["code"], "transaction_invalid")
        self.assertEqual(tree_snapshot(self.project_p1), before_a)
        self.assertEqual(tree_snapshot(self.project_p2), before_b)

    def test_old_candidate_without_binding_is_rejected_only_in_explicit_mode(self):
        self.write_inputs()
        self.connect(allow_write=True)
        read = self.read_context()
        prepared = self.prepare(read["read_id"], request_id())
        base_path = Path(prepared["workspace_path"]) / "base.json"
        base = json.loads(base_path.read_text(encoding="utf-8"))
        base.pop("project_path")
        base.pop("binding_fingerprint")
        base.pop("base_digest")
        base["base_digest"] = sha(canonical(base))
        base_path.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        rejected = self.inspect_candidate(prepared["revision_id"], error=True)
        self.assertEqual(rejected["error"]["code"], "transaction_invalid")

    def test_old_transaction_without_binding_is_rejected_in_explicit_mode(self):
        self.write_inputs()
        self.connect(allow_write=True)
        prepared, inspected = self.prepare_ready()
        self.server.tools.failpoint = lambda event, _context: (
            (_ for _ in ()).throw(RuntimeError("injected"))
            if event == "member_after:0" else None)
        rejected = self.accept(
            prepared["revision_id"], inspected["inspection_id"], request_id(), identifier=38,
            error=True)
        self.server.tools.failpoint = None
        transaction_id = rejected["error"]["details"]["transaction_id"]
        plan_path = (self.project_p1 / STATE_DIR / "transactions"
                     / transaction_id / "plan.json")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan.pop("project_path")
        plan.pop("binding_fingerprint")
        recorded = plan.pop("plan_sha256")
        self.assertNotEqual(recorded, sha(canonical(plan)))
        plan["plan_sha256"] = sha(canonical(plan))
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        rejected_plan = self.call(self.mcp.INSPECT, {
            "project_path": str(self.project_p1), "target": "transaction",
            "transaction_id": transaction_id}, error=True)
        self.assertEqual(rejected_plan["error"]["code"], "transaction_invalid")


class ExplicitImportAuthorizationTests(ExplicitUiFixture):
    def test_authorized_import_completes_accept_and_history(self):
        prepared, inspected = self.prepare_import_ready()
        source_before = tree_snapshot(self.import_parent)
        accepted = self.accept_ready(prepared, inspected)
        self.assertEqual(accepted["write_outcome"], "saved")
        self.assertEqual(tree_snapshot(self.import_parent), source_before)
        self.assertEqual(len(self.read_history()["versions"]), 1)
        self.assertTrue((self.project_p1 / DESIGN_PATH).is_file())

    def test_import_overlap_uses_current_project_not_missing_old_root(self):
        self.write_inputs()
        for restricted in (self.project_p1, self.foundation, self.ui, self.upstream):
            with self.subTest(restricted=restricted):
                self.connect(import_roots=[restricted], allow_write=True)
                spec = self.import_source(root=restricted, files=["index.html"])
                rejected = self.call(self.mcp.READ_CONTEXT, {
                    "project_path": str(self.project_p1), "import_source": spec}, error=True)
                self.assertEqual(rejected["error"]["code"], "path_not_allowed")
        legacy_import = self.projects / "old-root-independent-import"
        self.write_import_case(legacy_import)
        self.connect(import_roots=[legacy_import], allow_write=True)
        read = self.read_context(import_source=self.import_source(legacy_import))
        self.assertTrue(read["read_id"])

    def test_revoked_import_before_prepare_does_not_read_source(self):
        self.write_inputs()
        self.write_import_case()
        self.connect(import_roots=[self.import_parent], allow_write=True)
        read = self.read_context(import_source=self.import_source())
        self.server.tools.import_roots = ()
        context_module = sys.modules["file_tools.context"]
        with mock.patch.object(context_module.Closure, "_collect_import",
                               side_effect=AssertionError("external import read")):
            rejected = self.prepare(read["read_id"], request_id(), identifier=40, error=True)
        self.assertEqual(rejected["error"]["code"], "path_not_allowed")
        self.assertFalse((self.project_p1 / STATE_DIR / "work").exists())

    def test_revoked_import_rejects_inspect_and_accept_without_consuming_inspection(self):
        prepared, inspected = self.prepare_import_ready()
        self.server.tools.import_roots = ()
        context_module = sys.modules["file_tools.context"]
        with mock.patch.object(context_module.Closure, "_collect_import",
                               side_effect=AssertionError("external import read")):
            rejected_inspect = self.inspect_candidate(
                prepared["revision_id"], identifier=41, error=True)
            self.assertEqual(rejected_inspect["error"]["code"], "path_not_allowed")
            rejected_accept = self.accept(
                prepared["revision_id"], inspected["inspection_id"], request_id(), identifier=42,
                error=True)
            self.assertEqual(rejected_accept["error"]["code"], "path_not_allowed")
        self.assertFalse((self.project_p1 / MANIFEST_PATH).exists())
        self.server.tools.import_roots = (self.import_parent.parent,)
        accepted = self.accept_ready(prepared, inspected)
        self.assertEqual(accepted["write_outcome"], "saved")

    def test_new_process_without_import_authorization_rejects_persistent_candidate(self):
        prepared, _inspected = self.prepare_import_ready()
        self.connect(import_roots=(), allow_write=True)
        rejected = self.inspect_candidate(prepared["revision_id"], identifier=43, error=True)
        self.assertEqual(rejected["error"]["code"], "path_not_allowed")
        replay = self.prepare(
            "read-from-old-process", prepared["request_id"], "import", error=True)
        self.assertEqual(replay["error"]["code"], "path_not_allowed")
        self.assertFalse((self.project_p1 / MANIFEST_PATH).exists())

    def test_revoked_resume_stops_but_local_rollback_uses_only_project_evidence(self):
        transaction_id = self.interrupt_import_accept()
        self.server.tools.import_roots = ()
        context_module = sys.modules["file_tools.context"]
        unknown = self.project_p1 / DEFAULT_ROOT / "user-note.txt"
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_text("keep\n", encoding="utf-8")
        with mock.patch.object(context_module.Closure, "_collect_import",
                               side_effect=AssertionError("external import read")):
            resumed = self.recover(transaction_id, request_id(), "resume", identifier=44, error=True)
            self.assertEqual(resumed["error"]["code"], "path_not_allowed")
            rollback = self.recover(transaction_id, request_id(), "rollback", identifier=45)
        self.assertEqual(rollback["transaction_status"], "rolled_back")
        self.assertEqual(unknown.read_text(encoding="utf-8"), "keep\n")
        self.assertFalse((self.project_p1 / MANIFEST_PATH).exists())
        inputs = next(item for item in rollback["verification"] if item["code"] == "inputs")
        self.assertFalse(inputs["checked"])
        self.assertIsNone(inputs["passed"])
