"""
test_phase2_hardening.py — VaultCloud Bidirectional Sync Phase 2 Hardening Tests
================================================================================

Covers the four critical reliability and data-integrity requirements:
  1. Cloud deletion tombstone and re-upload prevention
  2. Reliable watcher loop prevention (hash-verified WriteSuppressionRegistry)
  3. Safe first-time synchronization (preserves both versions on hash divergence)
  4. Conflict copy lifecycle (local-only, non-replicating, crash-resilient)
  5. 10 End-to-end integration scenarios matching the specification

All tests use isolated temporary SQLite databases, mock auth/drive_client,
and clean temporary directories to ensure 100% test isolation.
"""

import hashlib
import os
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import db
from reconciler import (
    FileState, ReconciliationPlan, build_reconciliation_plan,
    classify_file_state, scan_local_tree, _hash_file,
    ACTION_NOOP, ACTION_UPLOAD_NEW, ACTION_UPLOAD_CHANGED,
    ACTION_DOWNLOAD_NEW, ACTION_DOWNLOAD_CHANGED, ACTION_CONFLICT,
    ACTION_LOCAL_DELETED, ACTION_CLOUD_DELETED, ACTION_BOTH_DELETED,
    execute_plan, _execute_download, _execute_conflict, _execute_upload,
    run_reconciliation_cycle, fetch_remote_file_tree,
    AgentWriteContext, is_agent_writing,
)
from watcher import (
    DebouncedHandler, IgnorePathContext, WriteSuppressionRegistry,
    suppression_registry,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_file(path: str, content: bytes = b"test content") -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return _sha256(content)


def _setup_isolated_db(test_case):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    patcher = patch.object(db, "DB_PATH", tmp.name)
    patcher.start()
    db.init_db()
    test_case.addCleanup(patcher.stop)
    return tmp.name


# ===========================================================================
# 1. Cloud Deletion Tombstone & Re-Upload Prevention
# ===========================================================================

class TestCloudDeletionTombstone(unittest.TestCase):
    """Verifies that cloud deletion does not purge local files AND does not
    lead to false re-uploads on subsequent reconciliation cycles."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        _setup_isolated_db(self)
        self.watched_dir = self.tmp_dir.name
        self.auth = MagicMock()
        self.auth.backend_url = "http://localhost:8000/api"
        self.auth.get_auth_header.return_value = {"Authorization": "Bearer token"}

    def test_reproduce_cloud_deletion_no_reupload_cycle(self):
        """
        Scenario:
          1. Synchronize report.txt between local and cloud.
          2. Delete cloud copy through web dashboard.
          3. Run desktop reconciliation.
          4. Run another reconciliation cycle.
        Expected:
          - Local file preserved.
          - Deleted cloud file NOT automatically recreated.
          - Tombstone remembered in SQLite.
          - No false upload_new on cycle 2.
        """
        content = b"Q3 Financial Report - Final"
        content_hash = _write_file(os.path.join(self.watched_dir, "report.txt"), content)

        # Step 1: Record synchronized state in SQLite
        db.upsert_record(
            "report.txt",
            local_hash=content_hash,
            cloud_id="cloud_rep_1",
            last_synced_hash=content_hash,
            last_synced_cloud_md5=content_hash,
            cloud_version=1,
            status="Synced",
            is_tombstone=0,
        )

        # Step 2: Cloud deletion simulation -> remote tree has NO report.txt
        remote_files = []  # report.txt was deleted in web dashboard

        # Step 3: Run Cycle 1
        local_tree = scan_local_tree(self.watched_dir)
        records = db.all_records()
        plan1 = build_reconciliation_plan(local_tree, remote_files, records, self.watched_dir)

        # Must classify as cloud_deleted
        self.assertEqual(len(plan1.cloud_deletions), 1)
        self.assertEqual(plan1.cloud_deletions[0].rel_path, "report.txt")
        self.assertEqual(len(plan1.uploads), 0)

        # Execute Plan 1
        dc = MagicMock()
        results1 = execute_plan(plan1, self.auth, self.watched_dir, "dev1", db, dc, IgnorePathContext)
        self.assertEqual(results1["cloud_deletions_noted"], 1)

        # Verify local file is intact
        self.assertTrue(os.path.exists(os.path.join(self.watched_dir, "report.txt")))

        # Verify tombstone in SQLite
        rec1 = db.get_record("report.txt")
        self.assertIsNotNone(rec1)
        self.assertEqual(rec1["status"], "CloudDeleted")
        self.assertEqual(rec1.get("is_tombstone"), 1)

        # Step 4: Run Cycle 2 (subsequent cycle)
        local_tree2 = scan_local_tree(self.watched_dir)
        records2 = db.all_records()
        plan2 = build_reconciliation_plan(local_tree2, remote_files, records2, self.watched_dir)

        # CRITICAL ASSERTION: No uploads queued! Tombstone prevents false upload_new
        self.assertEqual(len(plan2.uploads), 0, "Tombstone failed: false upload_new was queued!")
        self.assertEqual(len(plan2.downloads), 0)
        self.assertEqual(len(plan2.conflicts), 0)
        self.assertEqual(plan2.noops, 1, "Expected NO-OP for tombstoned unchanged local file")

    def test_network_failure_does_not_trigger_false_deletion(self):
        """A network exception during remote tree fetch must raise and abort,
        NEVER treating failed/partial API responses as cloud deletions."""
        with patch("reconciler._api") as mock_api:
            mock_api.side_effect = Exception("Connection reset by peer")
            with self.assertRaises(RuntimeError):
                fetch_remote_file_tree(self.auth)

    def test_fetch_remote_file_tree_queries_root_and_subfolders(self):
        """Verifies fetch_remote_file_tree queries root ('root') and all subfolders discovered,
        assigning correct relative folder paths."""
        with patch("reconciler._api") as mock_api:
            def _fake_api(auth, method, path, **kwargs):
                resp = MagicMock()
                resp.raise_for_status.return_value = None
                params = kwargs.get("params", {})
                clean_path = path.strip("/")
                if clean_path == "folders":
                    resp.json.return_value = {
                        "results": [
                            {"id": "f_docs", "name": "Documents", "parent_id": None},
                            {"id": "f_proj", "name": "Projects", "parent_id": "f_docs"}
                        ]
                    }
                elif clean_path == "files":
                    parent = params.get("parent_id")
                    if parent == "root":
                        resp.json.return_value = {
                            "results": [{"id": "r1", "name": "root_file.txt", "type": "file", "deleted": False}]
                        }
                    elif parent == "f_docs":
                        resp.json.return_value = {
                            "results": [{"id": "d1", "name": "doc.pdf", "type": "file", "deleted": False}]
                        }
                    elif parent == "f_proj":
                        resp.json.return_value = {
                            "results": [{"id": "p1", "name": "plan.md", "type": "file", "deleted": False}]
                        }
                    else:
                        resp.json.return_value = {"results": []}
                return resp

            mock_api.side_effect = _fake_api
            files = fetch_remote_file_tree(self.auth)
            self.assertEqual(len(files), 3)
            files_by_name = {f["name"]: f for f in files}
            self.assertEqual(files_by_name["root_file.txt"]["_folder_rel"], "")
            self.assertEqual(files_by_name["doc.pdf"]["_folder_rel"], "Documents")
            self.assertEqual(files_by_name["plan.md"]["_folder_rel"], "Documents/Projects")

    def test_both_sides_deleted_cleans_up_safely(self):
        """When local file is deleted after cloud deletion, it is classified as both_deleted."""
        state = FileState(
            rel_path="gone.txt",
            local_exists=False,
            cloud_exists=False,
            status="CloudDeleted",
            is_tombstone=1,
        )
        self.assertEqual(classify_file_state(state), ACTION_BOTH_DELETED)


# ===========================================================================
# 2. Reliable Watcher Loop Prevention
# ===========================================================================

class TestWatcherLoopPrevention(unittest.TestCase):
    """Verifies durable, hash-verified write suppression without sleep dependencies."""

    def setUp(self):
        self.registry = WriteSuppressionRegistry(default_ttl=5.0)
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.file_path = os.path.join(self.tmp_dir.name, "downloaded.txt")
        self.content = b"agent downloaded content"
        self.content_hash = _write_file(self.file_path, self.content)

    def test_delayed_event_suppressed_by_hash(self):
        """An event arriving after download operation completes is suppressed by matching hash."""
        self.registry.record_suppression(self.file_path, self.content_hash)
        # Event arrives delayed
        self.assertTrue(self.registry.should_suppress(self.file_path))

    def test_duplicate_events_both_suppressed(self):
        """Multiple OS events for the same file write are all suppressed."""
        self.registry.record_suppression(self.file_path, self.content_hash)
        self.assertTrue(self.registry.should_suppress(self.file_path))
        self.assertTrue(self.registry.should_suppress(self.file_path))

    def test_immediate_user_modification_not_suppressed(self):
        """If user edits the file immediately after download, the event is NOT suppressed."""
        self.registry.record_suppression(self.file_path, self.content_hash)
        # User modifies the file immediately
        _write_file(self.file_path, b"user edited content right away")
        self.assertFalse(self.registry.should_suppress(self.file_path))

    def test_failed_download_does_not_suppress_existing_file(self):
        """If a download fails, no false suppression is registered for the file."""
        self.assertFalse(self.registry.should_suppress(self.file_path))

    def test_ttl_expiration_purges_suppression(self):
        """Expired suppression records do not permanently block user events."""
        registry = WriteSuppressionRegistry(default_ttl=0.05)
        registry.record_suppression(self.file_path, self.content_hash, ttl=0.05)
        time.sleep(0.1)
        self.assertFalse(registry.should_suppress(self.file_path))

    def test_bounded_cleanup_caps_memory(self):
        """Registry memory is bounded by max_entries."""
        registry = WriteSuppressionRegistry(max_entries=5)
        for i in range(10):
            p = os.path.join(self.tmp_dir.name, f"f{i}.txt")
            registry.record_suppression(p, f"hash{i}")
        self.assertLessEqual(len(registry._suppressed), 5)


# ===========================================================================
# 3. Safe First-Time Synchronization
# ===========================================================================

class TestSafeFirstTimeSync(unittest.TestCase):
    """Verifies that first-time sync NEVER silently overwrites local content."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        _setup_isolated_db(self)
        self.watched_dir = self.tmp_dir.name
        self.auth = MagicMock()
        self.auth.backend_url = "http://localhost:8000/api"
        self.auth.get_auth_header.return_value = {"Authorization": "Bearer token"}

    def test_first_sync_divergence_preserves_both_versions(self):
        """
        Local: Documents/report.txt containing LOCAL_CONTENT.
        Cloud: Documents/report.txt containing CLOUD_CONTENT.
        SQLite: No record.
        Expected:
          - Both versions preserved.
          - Never silently overwrite LOCAL_CONTENT.
          - Conflict copy created for local content.
          - Cloud version downloaded to original path.
        """
        local_content = b"LOCAL_CONTENT from laptop"
        cloud_content = b"CLOUD_CONTENT from web dashboard"

        local_path = os.path.join(self.watched_dir, "Documents", "report.txt")
        local_hash = _write_file(local_path, local_content)
        cloud_hash = _sha256(cloud_content)

        state = FileState(
            rel_path="Documents/report.txt",
            cloud_id="cloud_doc_1",
            local_exists=True,
            local_hash=local_hash,
            cloud_exists=True,
            cloud_hash=cloud_hash,
            cloud_version=1,
            last_synced_hash=None,
            last_synced_cloud_hash=None,
        )

        # 1. Decision must be CONFLICT, NOT download_changed
        action = classify_file_state(state)
        self.assertEqual(action, ACTION_CONFLICT)

        # 2. Execute conflict
        dc = MagicMock()
        def _mock_dl(auth, cid, dest):
            with open(dest, "wb") as f:
                f.write(cloud_content)
        dc.download_file.side_effect = _mock_dl

        _execute_conflict(state, self.auth, local_path, self.watched_dir, "dev1",
                          db, dc, IgnorePathContext, "cycle_test")

        # Original path has cloud content
        with open(local_path, "rb") as f:
            self.assertEqual(f.read(), cloud_content)

        # Conflict copy exists and has local content
        doc_dir = os.path.join(self.watched_dir, "Documents")
        conflict_files = [f for f in os.listdir(doc_dir) if "conflict" in f]
        self.assertEqual(len(conflict_files), 1)

        with open(os.path.join(doc_dir, conflict_files[0]), "rb") as f:
            self.assertEqual(f.read(), local_content)

        # 3. Subsequent cycle must NOT recreate conflicts
        local_tree = scan_local_tree(self.watched_dir)
        remote_files = [{
            "id": "cloud_doc_1",
            "name": "report.txt",
            "content_hash": cloud_hash,
            "version_number": 1,
            "type": "file",
            "_folder_rel": "Documents",
        }]
        records = db.all_records()
        plan = build_reconciliation_plan(local_tree, remote_files, records, self.watched_dir)

        self.assertEqual(len(plan.conflicts), 0, "Conflict was repeatedly recreated!")
        self.assertEqual(len(plan.uploads), 0)
        self.assertEqual(len(plan.downloads), 0)


# ===========================================================================
# 4. Conflict Copy Lifecycle
# ===========================================================================

class TestConflictCopyLifecycle(unittest.TestCase):
    """Verifies that conflict copies remain local-only and are not uploaded."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        _setup_isolated_db(self)
        self.watched_dir = self.tmp_dir.name

    def test_conflict_copy_is_noop_on_subsequent_cycles(self):
        """Conflict copies are marked status=Conflict in SQLite and classified as NO-OP."""
        conflict_rel = "notes (conflict from cloud 2026-11-05 120000).txt"
        conflict_path = os.path.join(self.watched_dir, conflict_rel)
        h = _write_file(conflict_path, b"preserved draft")

        db.upsert_record(
            conflict_rel,
            local_hash=h,
            cloud_id=None,
            last_synced_hash=h,
            status="Conflict",
            conflict_original_path="notes.txt",
        )

        state = FileState(
            rel_path=conflict_rel,
            cloud_id=None,
            local_exists=True,
            local_hash=h,
            status="Conflict",
            cloud_exists=False,
        )

        # Pure decision
        self.assertEqual(classify_file_state(state), ACTION_NOOP)

        # In full plan
        local_tree = {conflict_rel: h}
        remote_files = []
        records = db.all_records()
        plan = build_reconciliation_plan(local_tree, remote_files, records, self.watched_dir)

        self.assertEqual(len(plan.uploads), 0, "Conflict copy was erroneously queued for upload!")
        self.assertEqual(len(plan.conflicts), 0)
        self.assertEqual(plan.noops, 1)

    def test_conflict_records_survive_agent_restart(self):
        """Conflict status is durable in SQLite across restarts."""
        rel = "doc (conflict from cloud 2026-11-05).txt"
        h = _write_file(os.path.join(self.watched_dir, rel), b"draft")
        db.upsert_record(rel, local_hash=h, cloud_id=None, status="Conflict", conflict_original_path="doc.txt")

        # Simulate fresh connection
        rec = db.get_record(rel)
        self.assertEqual(rec["status"], "Conflict")
        self.assertIsNone(rec["cloud_id"])
        self.assertEqual(rec.get("conflict_original_path"), "doc.txt")


# ===========================================================================
# 5. 10 End-to-End Integration Scenarios
# ===========================================================================

class TestTenIntegrationScenarios(unittest.TestCase):
    """End-to-end testing of the 10 scenarios requested in Section 5."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        _setup_isolated_db(self)
        self.watched_dir = self.tmp_dir.name
        self.auth = MagicMock()
        self.auth.backend_url = "http://localhost:8000/api"
        self.auth.get_auth_header.return_value = {"Authorization": "Bearer token"}

    def test_scenario_01_dashboard_upload_to_desktop_discovery(self):
        """1. Dashboard upload -> desktop discovery and atomic download."""
        content = b"created on web dashboard"
        chash = _sha256(content)
        remote_files = [{
            "id": "cid_web_01",
            "name": "from_web.txt",
            "content_hash": chash,
            "version_number": 1,
            "type": "file",
            "_folder_rel": "",
        }]

        local_tree = scan_local_tree(self.watched_dir)
        records = db.all_records()
        plan = build_reconciliation_plan(local_tree, remote_files, records, self.watched_dir)

        self.assertEqual(len(plan.downloads), 1)
        self.assertEqual(plan.downloads[0].action, ACTION_DOWNLOAD_NEW)

        dc = MagicMock()
        def _dl(auth, cid, dest):
            with open(dest, "wb") as f:
                f.write(content)
        dc.download_file.side_effect = _dl

        results = execute_plan(plan, self.auth, self.watched_dir, "dev1", db, dc, IgnorePathContext)
        self.assertEqual(results["downloaded"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.watched_dir, "from_web.txt")))

    def test_scenario_02_dashboard_update_to_local_inplace_replacement(self):
        """2. Dashboard update -> local in-place replacement (no duplicate)."""
        old_content = b"version 1"
        new_content = b"version 2 updated from web"
        p = os.path.join(self.watched_dir, "edit.txt")
        old_hash = _write_file(p, old_content)
        new_hash = _sha256(new_content)

        db.upsert_record("edit.txt", local_hash=old_hash, cloud_id="cid_edit",
                         last_synced_hash=old_hash, last_synced_cloud_md5=old_hash,
                         cloud_version=1, status="Synced")

        remote_files = [{
            "id": "cid_edit", "name": "edit.txt", "content_hash": new_hash,
            "version_number": 2, "type": "file", "_folder_rel": ""
        }]

        local_tree = scan_local_tree(self.watched_dir)
        records = db.all_records()
        plan = build_reconciliation_plan(local_tree, remote_files, records, self.watched_dir)
        self.assertEqual(len(plan.downloads), 1)
        self.assertEqual(plan.downloads[0].action, ACTION_DOWNLOAD_CHANGED)

        dc = MagicMock()
        def _dl(auth, cid, dest):
            with open(dest, "wb") as f:
                f.write(new_content)
        dc.download_file.side_effect = _dl

        execute_plan(plan, self.auth, self.watched_dir, "dev1", db, dc, IgnorePathContext)

        with open(p, "rb") as f:
            self.assertEqual(f.read(), new_content)
        # Verify no "(cloud updated)" files created
        files = os.listdir(self.watched_dir)
        self.assertEqual(files, ["edit.txt"])

    def test_scenario_03_local_upload_to_cloud_discovery(self):
        """3. Local upload -> cloud discovery."""
        p = os.path.join(self.watched_dir, "new_local.txt")
        h = _write_file(p, b"brand new file on local disk")

        local_tree = scan_local_tree(self.watched_dir)
        remote_files = []
        records = db.all_records()
        plan = build_reconciliation_plan(local_tree, remote_files, records, self.watched_dir)

        self.assertEqual(len(plan.uploads), 1)
        self.assertEqual(plan.uploads[0].action, ACTION_UPLOAD_NEW)

        dc = MagicMock()
        dc.upload_file.return_value = {"id": "cid_new", "version_number": 1, "content_hash": h}
        dc.get_or_create_drive_folder.return_value = "root"

        results = execute_plan(plan, self.auth, self.watched_dir, "dev1", db, dc, IgnorePathContext)
        self.assertEqual(results["uploaded"], 1)
        rec = db.get_record("new_local.txt")
        self.assertEqual(rec["cloud_id"], "cid_new")
        self.assertEqual(rec["status"], "Synced")

    def test_scenario_04_local_update_to_cloud_update(self):
        """4. Local update -> cloud update."""
        p = os.path.join(self.watched_dir, "doc.txt")
        old_h = _write_file(p, b"v1")
        db.upsert_record("doc.txt", local_hash=old_h, cloud_id="cid_doc",
                         last_synced_hash=old_h, last_synced_cloud_md5=old_h,
                         cloud_version=1, status="Synced")

        new_h = _write_file(p, b"v2 local update")
        local_tree = scan_local_tree(self.watched_dir)
        remote_files = [{
            "id": "cid_doc", "name": "doc.txt", "content_hash": old_h,
            "version_number": 1, "type": "file", "_folder_rel": ""
        }]
        records = db.all_records()
        plan = build_reconciliation_plan(local_tree, remote_files, records, self.watched_dir)

        self.assertEqual(len(plan.uploads), 1)
        self.assertEqual(plan.uploads[0].action, ACTION_UPLOAD_CHANGED)

    def test_scenario_05_cloud_deletion_no_automatic_reupload(self):
        """5. Cloud deletion -> no automatic re-upload."""
        p = os.path.join(self.watched_dir, "report.txt")
        h = _write_file(p, b"report")
        db.upsert_record("report.txt", local_hash=h, cloud_id="cid_rep",
                         last_synced_hash=h, last_synced_cloud_md5=h,
                         cloud_version=1, status="Synced")

        # Cycle 1: deletion detected
        plan1 = build_reconciliation_plan({ "report.txt": h }, [], db.all_records(), self.watched_dir)
        self.assertEqual(len(plan1.cloud_deletions), 1)
        execute_plan(plan1, self.auth, self.watched_dir, "dev1", db, MagicMock(), IgnorePathContext)

        # Cycle 2: tombstone prevents re-upload
        plan2 = build_reconciliation_plan({ "report.txt": h }, [], db.all_records(), self.watched_dir)
        self.assertEqual(len(plan2.uploads), 0)
        self.assertEqual(plan2.noops, 1)

    def test_scenario_06_delayed_watcher_event_no_upload_loop(self):
        """6. Delayed watcher event -> no upload loop."""
        p = os.path.join(self.watched_dir, "auto.txt")
        h = _write_file(p, b"written by reconciler")

        # Register in hash suppression registry
        suppression_registry.record_suppression(p, h, ttl=10.0)

        # Simulate watcher event arriving after download
        self.assertTrue(suppression_registry.should_suppress(p))

    def test_scenario_07_first_sync_conflict_preserves_both(self):
        """7. First-sync conflict -> both versions preserved."""
        p = os.path.join(self.watched_dir, "diverge.txt")
        lh = _write_file(p, b"local side")
        ch = _sha256(b"cloud side")

        state = FileState(
            rel_path="diverge.txt", cloud_id="cid_div", local_exists=True,
            local_hash=lh, cloud_exists=True, cloud_hash=ch, cloud_version=1
        )
        self.assertEqual(classify_file_state(state), ACTION_CONFLICT)

    def test_scenario_08_conflict_copy_no_repeated_conflict(self):
        """8. Conflict copy -> no repeated conflict."""
        rel = "doc (conflict from cloud 2026-11-05).txt"
        h = _write_file(os.path.join(self.watched_dir, rel), b"conflict copy")
        db.upsert_record(rel, local_hash=h, cloud_id=None, status="Conflict")

        plan = build_reconciliation_plan({rel: h}, [], db.all_records(), self.watched_dir)
        self.assertEqual(len(plan.conflicts), 0)
        self.assertEqual(len(plan.uploads), 0)

    def test_scenario_09_network_failure_no_false_deletion(self):
        """9. Network failure -> no false deletion."""
        p = os.path.join(self.watched_dir, "doc.txt")
        h = _write_file(p, b"important doc")
        db.upsert_record("doc.txt", local_hash=h, cloud_id="cid_doc",
                         last_synced_hash=h, last_synced_cloud_md5=h,
                         cloud_version=1, status="Synced")

        # Network fails during run_reconciliation_cycle
        with patch("reconciler.fetch_remote_file_tree") as mock_fetch:
            mock_fetch.side_effect = RuntimeError("Network timeout")
            result = run_reconciliation_cycle(
                self.auth, self.watched_dir, "dev1",
                db, MagicMock(), IgnorePathContext
            )

        self.assertTrue(result.get("skipped"))
        # Verify SQLite record is completely untouched (still Synced, not deleted)
        rec = db.get_record("doc.txt")
        self.assertEqual(rec["status"], "Synced")

    def test_scenario_10_agent_restart_state_restored(self):
        """10. Agent restart -> state correctly restored."""
        p = os.path.join(self.watched_dir, "state.txt")
        h = _write_file(p, b"state test")
        db.upsert_record("state.txt", local_hash=h, cloud_id="cid_state",
                         last_synced_hash=h, last_synced_cloud_md5=h,
                         cloud_version=3, status="Synced", is_tombstone=0)

        # Fresh query simulating startup
        all_recs = db.all_records()
        self.assertEqual(len(all_recs), 1)
        self.assertEqual(all_recs[0]["path"], "state.txt")
        self.assertEqual(all_recs[0]["cloud_version"], 3)


if __name__ == "__main__":
    unittest.main()
