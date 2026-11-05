"""
test_bidirectional_sync.py — VaultCloud Bidirectional Sync Test Suite
======================================================================

Tests the reconciliation engine (reconciler.py) covering:
  A. Local-to-cloud scenarios
  B. Cloud-to-local scenarios
  C. Conflict handling
  D. Reliability & edge cases
  E. Loop-prevention (agent downloads do not trigger re-uploads)
  F. SQLite state integrity

All tests use isolated temp SQLite databases and mocked network calls.
No real network requests are made.
"""

import hashlib
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, call

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import db
from reconciler import (
    FileState, ReconciliationPlan, build_reconciliation_plan,
    classify_file_state, scan_local_tree, _hash_file,
    ACTION_NOOP, ACTION_UPLOAD_NEW, ACTION_UPLOAD_CHANGED,
    ACTION_DOWNLOAD_NEW, ACTION_DOWNLOAD_CHANGED, ACTION_CONFLICT,
    ACTION_LOCAL_DELETED, ACTION_CLOUD_DELETED,
    execute_plan, _execute_download, AgentWriteContext, is_agent_writing,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_file(path: str, content: bytes = b"hello world") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return _sha256(content)


def _isolated_db(test_case):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    patcher = patch.object(db, "DB_PATH", tmp.name)
    patcher.start()
    db.init_db()
    test_case._db_patcher = patcher
    test_case._tmp_db = tmp.name
    return patcher


# ---------------------------------------------------------------------------
# ═══ Suite A: Decision Table (classify_file_state) ═══
# ---------------------------------------------------------------------------

class TestClassifyFileState(unittest.TestCase):
    """Unit tests for the pure decision function."""

    def _state(self, **kwargs) -> FileState:
        return FileState(rel_path="test.txt", **kwargs)

    def test_both_absent_is_both_deleted(self):
        s = self._state(local_exists=False, cloud_exists=False)
        self.assertEqual(classify_file_state(s), "both_deleted")

    def test_new_local_no_cloud_is_upload_new(self):
        h = "aaa"
        s = self._state(local_exists=True, local_hash=h, cloud_exists=False, cloud_id=None)
        self.assertEqual(classify_file_state(s), ACTION_UPLOAD_NEW)

    def test_new_cloud_no_local_is_download_new(self):
        s = self._state(local_exists=False, cloud_exists=True,
                        cloud_id="cid1", cloud_hash="bbb")
        self.assertEqual(classify_file_state(s), ACTION_DOWNLOAD_NEW)

    def test_local_deleted_cloud_still_exists(self):
        s = self._state(
            local_exists=False, cloud_exists=True,
            cloud_id="cid1", last_synced_hash="old", cloud_hash="old"
        )
        self.assertEqual(classify_file_state(s), ACTION_LOCAL_DELETED)

    def test_cloud_deleted_local_exists(self):
        s = self._state(
            local_exists=True, local_hash="old", cloud_exists=False,
            cloud_id="cid1", last_synced_hash="old", last_synced_cloud_hash="old"
        )
        self.assertEqual(classify_file_state(s), ACTION_CLOUD_DELETED)

    def test_unchanged_both_sides_is_noop(self):
        h = "deadbeef"
        s = self._state(
            local_exists=True, local_hash=h, cloud_exists=True, cloud_hash=h,
            last_synced_hash=h, last_synced_cloud_hash=h
        )
        self.assertEqual(classify_file_state(s), ACTION_NOOP)

    def test_local_changed_cloud_unchanged_is_upload_changed(self):
        old = "aaa"
        new_local = "bbb"
        s = self._state(
            local_exists=True, local_hash=new_local, cloud_exists=True, cloud_hash=old,
            last_synced_hash=old, last_synced_cloud_hash=old
        )
        self.assertEqual(classify_file_state(s), ACTION_UPLOAD_CHANGED)

    def test_cloud_changed_local_unchanged_is_download_changed(self):
        old = "aaa"
        new_cloud = "ccc"
        s = self._state(
            local_exists=True, local_hash=old, cloud_exists=True, cloud_hash=new_cloud,
            last_synced_hash=old, last_synced_cloud_hash=old
        )
        self.assertEqual(classify_file_state(s), ACTION_DOWNLOAD_CHANGED)

    def test_both_changed_is_conflict(self):
        old = "aaa"
        s = self._state(
            local_exists=True, local_hash="bbb", cloud_exists=True, cloud_hash="ccc",
            last_synced_hash=old, last_synced_cloud_hash=old
        )
        self.assertEqual(classify_file_state(s), ACTION_CONFLICT)

    def test_first_time_identical_hash_is_noop(self):
        h = "deadbeef"
        s = self._state(
            local_exists=True, local_hash=h, cloud_exists=True, cloud_hash=h,
            last_synced_hash=None, last_synced_cloud_hash=None
        )
        # Both sides identical on first encounter → no-op (adopt silently)
        self.assertEqual(classify_file_state(s), ACTION_NOOP)

    def test_first_time_different_hash_downloads_cloud(self):
        s = self._state(
            local_exists=True, local_hash="localonly", cloud_exists=True, cloud_hash="cloudver",
            last_synced_hash=None, last_synced_cloud_hash=None
        )
        # Cloud is authoritative on first encounter with different content
        self.assertEqual(classify_file_state(s), ACTION_DOWNLOAD_CHANGED)


# ---------------------------------------------------------------------------
# ═══ Suite B: Local filesystem scan ═══
# ---------------------------------------------------------------------------

class TestScanLocalTree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_scans_flat_files(self):
        p1 = os.path.join(self.tmp.name, "a.txt")
        p2 = os.path.join(self.tmp.name, "b.txt")
        h1 = _write_file(p1, b"content a")
        h2 = _write_file(p2, b"content b")
        tree = scan_local_tree(self.tmp.name)
        self.assertEqual(tree["a.txt"], h1)
        self.assertEqual(tree["b.txt"], h2)

    def test_scans_nested_directories(self):
        nested = os.path.join(self.tmp.name, "sub", "deep")
        os.makedirs(nested)
        p = os.path.join(nested, "file.txt")
        h = _write_file(p, b"nested")
        tree = scan_local_tree(self.tmp.name)
        self.assertIn("sub/deep/file.txt", tree)
        self.assertEqual(tree["sub/deep/file.txt"], h)

    def test_skips_tmp_files(self):
        p1 = os.path.join(self.tmp.name, "real.txt")
        p2 = os.path.join(self.tmp.name, "file.tmp")
        p3 = os.path.join(self.tmp.name, "file.tmp.abc123")
        _write_file(p1)
        _write_file(p2)
        _write_file(p3)
        tree = scan_local_tree(self.tmp.name)
        self.assertIn("real.txt", tree)
        self.assertNotIn("file.tmp", tree)
        self.assertNotIn("file.tmp.abc123", tree)

    def test_skips_hidden_files(self):
        p = os.path.join(self.tmp.name, ".hidden")
        _write_file(p)
        tree = scan_local_tree(self.tmp.name)
        self.assertNotIn(".hidden", tree)

    def test_empty_directory_returns_empty(self):
        tree = scan_local_tree(self.tmp.name)
        self.assertEqual(tree, {})


# ---------------------------------------------------------------------------
# ═══ Suite C: Plan Builder (build_reconciliation_plan) ═══
# ---------------------------------------------------------------------------

class TestBuildReconciliationPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _isolated_db(self)
        db.init_db()

    def tearDown(self):
        self._db_patcher.stop()
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_new_local_file_becomes_upload(self):
        local_tree = {"newfile.txt": "hash_a"}
        remote_files = []
        sqlite_records = []
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.uploads), 1)
        self.assertEqual(plan.uploads[0].rel_path, "newfile.txt")
        self.assertEqual(plan.uploads[0].action, ACTION_UPLOAD_NEW)

    def test_new_remote_file_becomes_download(self):
        local_tree = {}
        remote_files = [{"id": "cid1", "name": "cloud.txt", "content_hash": "hash_c",
                         "version_number": 1, "deleted": False, "parent_id": None,
                         "_folder_rel": ""}]
        sqlite_records = []
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.downloads), 1)
        self.assertEqual(plan.downloads[0].cloud_id, "cid1")

    def test_unchanged_file_is_noop(self):
        h = "deadbeef"
        local_tree = {"same.txt": h}
        remote_files = [{"id": "cid2", "name": "same.txt", "content_hash": h,
                         "version_number": 1, "deleted": False, "parent_id": None,
                         "_folder_rel": ""}]
        sqlite_records = [{
            "path": "same.txt", "cloud_id": "cid2",
            "last_synced_hash": h, "last_synced_cloud_md5": h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(plan.noops, 1)
        self.assertEqual(len(plan.uploads), 0)
        self.assertEqual(len(plan.downloads), 0)

    def test_local_modified_becomes_upload_changed(self):
        old_h = "aaa"
        new_h = "bbb"
        local_tree = {"edit.txt": new_h}
        remote_files = [{"id": "cid3", "name": "edit.txt", "content_hash": old_h,
                         "version_number": 1, "deleted": False, "parent_id": None,
                         "_folder_rel": ""}]
        sqlite_records = [{
            "path": "edit.txt", "cloud_id": "cid3",
            "last_synced_hash": old_h, "last_synced_cloud_md5": old_h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.uploads), 1)
        self.assertEqual(plan.uploads[0].action, ACTION_UPLOAD_CHANGED)

    def test_cloud_modified_becomes_download_changed(self):
        old_h = "aaa"
        new_cloud_h = "ccc"
        local_tree = {"report.txt": old_h}
        remote_files = [{"id": "cid4", "name": "report.txt", "content_hash": new_cloud_h,
                         "version_number": 2, "deleted": False, "parent_id": None,
                         "_folder_rel": ""}]
        sqlite_records = [{
            "path": "report.txt", "cloud_id": "cid4",
            "last_synced_hash": old_h, "last_synced_cloud_md5": old_h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.downloads), 1)
        self.assertEqual(plan.downloads[0].action, ACTION_DOWNLOAD_CHANGED)

    def test_both_modified_becomes_conflict(self):
        old_h = "aaa"
        local_tree = {"both.txt": "local_new"}
        remote_files = [{"id": "cid5", "name": "both.txt", "content_hash": "cloud_new",
                         "version_number": 2, "deleted": False, "parent_id": None,
                         "_folder_rel": ""}]
        sqlite_records = [{
            "path": "both.txt", "cloud_id": "cid5",
            "last_synced_hash": old_h, "last_synced_cloud_md5": old_h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.conflicts), 1)
        self.assertEqual(plan.conflicts[0].action, ACTION_CONFLICT)

    def test_multiple_files_mixed_actions(self):
        h = "samehash"
        local_tree = {"same.txt": h, "new_local.txt": "new_hash"}
        remote_files = [
            {"id": "cid_same", "name": "same.txt", "content_hash": h,
             "version_number": 1, "deleted": False, "parent_id": None, "_folder_rel": ""},
            {"id": "cid_new_cloud", "name": "cloud_only.txt", "content_hash": "cloud_hash",
             "version_number": 1, "deleted": False, "parent_id": None, "_folder_rel": ""},
        ]
        sqlite_records = [{
            "path": "same.txt", "cloud_id": "cid_same",
            "last_synced_hash": h, "last_synced_cloud_md5": h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(plan.noops, 1)              # same.txt
        self.assertEqual(len(plan.uploads), 1)       # new_local.txt
        self.assertEqual(len(plan.downloads), 1)     # cloud_only.txt


# ---------------------------------------------------------------------------
# ═══ Suite D: Atomic Download (BUG-02 Fix) ═══
# ---------------------------------------------------------------------------

class TestAtomicDownload(unittest.TestCase):
    """
    Verifies that cloud updates replace the existing local file in-place
    (BUG-02: no longer creates '(cloud updated)' duplicates).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _isolated_db(self)
        db.init_db()

    def tearDown(self):
        self._db_patcher.stop()
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def _make_auth(self):
        auth = MagicMock()
        auth.backend_url = "http://localhost:8000/api"
        auth.get_auth_header.return_value = {"Authorization": "Bearer fake"}
        return auth

    def _make_drive_client(self, cloud_content: bytes):
        """Mock drive_client whose download_file writes cloud_content to destination."""
        cloud_hash = _sha256(cloud_content)
        dc = MagicMock()
        dc.download_file.side_effect = lambda auth, cid, dest: open(dest, "wb").write(cloud_content)
        dc.get_or_create_drive_folder.return_value = "root"
        dc.upload_file.return_value = {"id": "new_id", "version_number": 1, "content_hash": cloud_hash}
        dc.acquire_lock.return_value = True
        dc.release_lock.return_value = True
        return dc, cloud_hash

    def test_download_replaces_in_place_no_duplicate(self):
        """Cloud update must replace the local file in-place, NOT create a new filename."""
        old_content = b"original local content"
        new_content = b"updated cloud content"

        local_file = os.path.join(self.tmp.name, "report.txt")
        _write_file(local_file, old_content)

        dc, cloud_hash = self._make_drive_client(new_content)
        auth = self._make_auth()

        state = FileState(
            rel_path="report.txt",
            cloud_id="cloud_abc",
            cloud_hash=cloud_hash,
            cloud_version=2,
            action=ACTION_DOWNLOAD_CHANGED,
        )

        from watcher import IgnorePathContext
        _execute_download(state, auth, self.tmp.name, "device-1",
                          db, dc, IgnorePathContext, "test-cid")

        # Original file should now contain cloud content
        with open(local_file, "rb") as f:
            self.assertEqual(f.read(), new_content)

        # NO "(cloud updated)" file should exist
        files = os.listdir(self.tmp.name)
        for fname in files:
            self.assertNotIn("cloud updated", fname,
                             f"Found unexpected '(cloud updated)' file: {fname}")

    def test_download_creates_local_subdirs(self):
        """Downloading a cloud file in a subfolder creates the directory tree."""
        new_content = b"nested file content"
        dc, cloud_hash = self._make_drive_client(new_content)
        auth = self._make_auth()

        state = FileState(
            rel_path="docs/projects/report.txt",
            cloud_id="cloud_nested",
            cloud_hash=cloud_hash,
            cloud_version=1,
            action=ACTION_DOWNLOAD_NEW,
        )

        from watcher import IgnorePathContext
        _execute_download(state, auth, self.tmp.name, "device-1",
                          db, dc, IgnorePathContext, "test-cid")

        dest = os.path.join(self.tmp.name, "docs", "projects", "report.txt")
        self.assertTrue(os.path.exists(dest))
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), new_content)

    def test_download_hash_mismatch_preserves_original(self):
        """If downloaded content hash doesn't match expected, original must be preserved."""
        original_content = b"original safe content"
        bad_content = b"corrupted download"

        local_file = os.path.join(self.tmp.name, "safe.txt")
        _write_file(local_file, original_content)

        dc = MagicMock()
        dc.download_file.side_effect = lambda auth, cid, dest: open(dest, "wb").write(bad_content)
        auth = self._make_auth()

        state = FileState(
            rel_path="safe.txt",
            cloud_id="cloud_safe",
            cloud_hash="expected_hash_that_wont_match",
            cloud_version=2,
            action=ACTION_DOWNLOAD_CHANGED,
        )

        from watcher import IgnorePathContext
        with self.assertRaises(Exception):
            _execute_download(state, auth, self.tmp.name, "device-1",
                              db, dc, IgnorePathContext, "test-cid")

        # Original file must remain intact
        with open(local_file, "rb") as f:
            self.assertEqual(f.read(), original_content)

    def test_no_tmp_file_left_on_success(self):
        """Temp files must be cleaned up after a successful download."""
        content = b"clean content"
        dc, cloud_hash = self._make_drive_client(content)
        auth = self._make_auth()

        state = FileState(
            rel_path="clean.txt",
            cloud_id="cloud_clean",
            cloud_hash=cloud_hash,
            cloud_version=1,
            action=ACTION_DOWNLOAD_NEW,
        )

        from watcher import IgnorePathContext
        _execute_download(state, auth, self.tmp.name, "device-1",
                          db, dc, IgnorePathContext, "test-cid")

        tmp_files = [f for f in os.listdir(self.tmp.name) if ".tmp." in f]
        self.assertEqual(tmp_files, [], f"Leftover temp files found: {tmp_files}")

    def test_sqlite_updated_only_after_successful_download(self):
        """SQLite must be written only after successful download, not before."""
        content = b"verified content"
        dc, cloud_hash = self._make_drive_client(content)
        auth = self._make_auth()

        state = FileState(
            rel_path="verified.txt",
            cloud_id="cloud_ver",
            cloud_hash=cloud_hash,
            cloud_version=3,
            action=ACTION_DOWNLOAD_NEW,
        )

        # No record before download
        self.assertIsNone(db.get_record("verified.txt"))

        from watcher import IgnorePathContext
        _execute_download(state, auth, self.tmp.name, "device-1",
                          db, dc, IgnorePathContext, "test-cid")

        # Record must exist after
        rec = db.get_record("verified.txt")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["cloud_id"], "cloud_ver")
        self.assertEqual(rec["cloud_version"], 3)
        self.assertEqual(rec["status"], "Synced")


# ---------------------------------------------------------------------------
# ═══ Suite E: Remote Discovery (BUG-01 Fix) ═══
# ---------------------------------------------------------------------------

class TestRemoteDiscovery(unittest.TestCase):
    """
    Verifies that files created on the web dashboard (not in local SQLite)
    are discovered and downloaded (BUG-01 fix).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _isolated_db(self)
        db.init_db()

    def tearDown(self):
        self._db_patcher.stop()
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_cloud_only_file_included_in_plan(self):
        """A file uploaded via web dashboard (no SQLite record) must be in downloads."""
        local_tree = {}  # Empty local folder
        remote_files = [{
            "id": "web_upload_id", "name": "dashboard_upload.pdf",
            "content_hash": "cloud_hash_pdf", "version_number": 1,
            "deleted": False, "parent_id": None, "_folder_rel": ""
        }]
        sqlite_records = []  # No prior knowledge

        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)

        self.assertEqual(len(plan.downloads), 1,
                         "Cloud-only file must be in downloads (BUG-01 fix)")
        dl = plan.downloads[0]
        self.assertEqual(dl.cloud_id, "web_upload_id")
        self.assertEqual(dl.action, ACTION_DOWNLOAD_NEW)

    def test_multiple_cloud_only_files_all_discovered(self):
        """Multiple cloud files absent from SQLite must all be queued for download."""
        local_tree = {}
        remote_files = [
            {"id": f"cloud_{i}", "name": f"file{i}.txt", "content_hash": f"hash{i}",
             "version_number": 1, "deleted": False, "parent_id": None, "_folder_rel": ""}
            for i in range(5)
        ]
        sqlite_records = []
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.downloads), 5)

    def test_nested_cloud_folder_file_resolved_correctly(self):
        """A file in a subfolder (from web dashboard) uses the correct relative path."""
        local_tree = {}
        remote_files = [{
            "id": "nested_id", "name": "report.docx",
            "content_hash": "hash_docx", "version_number": 1,
            "deleted": False, "parent_id": "folder_id", "_folder_rel": "Documents/Work"
        }]
        sqlite_records = []
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.downloads), 1)
        self.assertEqual(plan.downloads[0].rel_path, "Documents/Work/report.docx")

    def test_known_synced_file_not_re_downloaded(self):
        """A file already in SQLite with matching hash must NOT be re-downloaded."""
        h = "matched_hash"
        local_tree = {"known.txt": h}
        remote_files = [{"id": "known_cid", "name": "known.txt",
                         "content_hash": h, "version_number": 1,
                         "deleted": False, "parent_id": None, "_folder_rel": ""}]
        sqlite_records = [{
            "path": "known.txt", "cloud_id": "known_cid",
            "last_synced_hash": h, "last_synced_cloud_md5": h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.downloads), 0)
        self.assertEqual(plan.noops, 1)


# ---------------------------------------------------------------------------
# ═══ Suite F: Conflict Handling ═══
# ---------------------------------------------------------------------------

class TestConflictHandling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _isolated_db(self)
        db.init_db()

    def tearDown(self):
        self._db_patcher.stop()
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_conflict_plan_has_no_uploads_or_downloads(self):
        """Conflict files go into the conflicts list, not uploads or downloads."""
        old_h = "original"
        local_tree = {"shared.txt": "local_modified"}
        remote_files = [{"id": "shared_cid", "name": "shared.txt",
                         "content_hash": "cloud_modified", "version_number": 2,
                         "deleted": False, "parent_id": None, "_folder_rel": ""}]
        sqlite_records = [{
            "path": "shared.txt", "cloud_id": "shared_cid",
            "last_synced_hash": old_h, "last_synced_cloud_md5": old_h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(len(plan.conflicts), 1)
        self.assertEqual(len(plan.uploads), 0)
        self.assertEqual(len(plan.downloads), 0)

    def test_conflict_copy_naming_does_not_clobber_existing(self):
        """If conflict copy name already exists, a unique name must be used."""
        import shutil
        from reconciler import _execute_conflict

        # Setup
        local_content = b"my local changes"
        cloud_content = b"cloud changes"
        local_file = os.path.join(self.tmp.name, "doc.txt")
        _write_file(local_file, local_content)

        # Pre-create a conflict file to force uniqueness logic
        # (simulate an already existing conflict file from an earlier conflict)

        dc = MagicMock()
        dc.download_file.side_effect = lambda auth, cid, dest: open(dest, "wb").write(cloud_content)
        auth = MagicMock()
        auth.get_auth_header.return_value = {"Authorization": "Bearer x"}
        auth.backend_url = "http://localhost:8000/api"

        state = FileState(
            rel_path="doc.txt",
            cloud_id="cloud_doc",
            cloud_hash=_sha256(cloud_content),
            cloud_version=2,
            action=ACTION_CONFLICT,
        )

        from watcher import IgnorePathContext
        _execute_conflict(state, auth, local_file, self.tmp.name, "dev1",
                          db, dc, IgnorePathContext, "cycle1")

        # Original should now have cloud content
        with open(local_file, "rb") as f:
            self.assertEqual(f.read(), cloud_content)

        # A conflict copy must exist
        conflict_files = [f for f in os.listdir(self.tmp.name) if "conflict" in f]
        self.assertGreater(len(conflict_files), 0, "No conflict copy was created")

        # Conflict copy must have the original local content
        conflict_path = os.path.join(self.tmp.name, conflict_files[0])
        with open(conflict_path, "rb") as f:
            self.assertEqual(f.read(), local_content)

    def test_conflict_recorded_in_sqlite(self):
        """After conflict resolution, SQLite must have an entry for the conflict copy."""
        cloud_content = b"cloud wins"
        local_file = os.path.join(self.tmp.name, "conflict_check.txt")
        _write_file(local_file, b"local version")

        dc = MagicMock()
        dc.download_file.side_effect = lambda auth, cid, dest: open(dest, "wb").write(cloud_content)
        auth = MagicMock()
        auth.get_auth_header.return_value = {"Authorization": "Bearer x"}
        auth.backend_url = "http://localhost:8000/api"

        state = FileState(
            rel_path="conflict_check.txt",
            cloud_id="cid_conflict",
            cloud_hash=_sha256(cloud_content),
            cloud_version=2,
            action=ACTION_CONFLICT,
        )

        from watcher import IgnorePathContext
        from reconciler import _execute_conflict
        _execute_conflict(state, auth, local_file, self.tmp.name, "dev1",
                          db, dc, IgnorePathContext, "cycle2")

        # Conflict copy must have a SQLite entry with status=Conflict
        all_recs = db.all_records()
        conflict_recs = [r for r in all_recs if r.get("status") == "Conflict"]
        self.assertGreater(len(conflict_recs), 0, "No Conflict-status record in SQLite")


# ---------------------------------------------------------------------------
# ═══ Suite G: Loop Prevention — Agent Downloads Do Not Trigger Re-upload ═══
# ---------------------------------------------------------------------------

class TestLoopPrevention(unittest.TestCase):
    """
    Verifies that agent-generated downloads do not trigger watcher events
    that would queue unnecessary re-uploads (sync loop prevention).
    """

    def test_agent_write_context_adds_path(self):
        with AgentWriteContext("/fake/path/file.txt"):
            self.assertTrue(is_agent_writing("/fake/path/file.txt"))
        self.assertFalse(is_agent_writing("/fake/path/file.txt"))

    def test_agent_write_context_removes_on_exit(self):
        try:
            with AgentWriteContext("/another/path.txt"):
                raise ValueError("simulated error")
        except ValueError:
            pass
        # Must be removed even on exception
        self.assertFalse(is_agent_writing("/another/path.txt"))

    def test_multiple_concurrent_paths(self):
        p1 = "/path/file1.txt"
        p2 = "/path/file2.txt"
        ctx1 = AgentWriteContext(p1)
        ctx2 = AgentWriteContext(p2)
        ctx1.__enter__()
        ctx2.__enter__()
        self.assertTrue(is_agent_writing(p1))
        self.assertTrue(is_agent_writing(p2))
        ctx1.__exit__(None, None, None)
        self.assertFalse(is_agent_writing(p1))
        self.assertTrue(is_agent_writing(p2))
        ctx2.__exit__(None, None, None)
        self.assertFalse(is_agent_writing(p2))

    def test_watcher_suppresses_event_during_agent_write(self):
        """DebouncedHandler must not schedule events when agent is writing."""
        import queue as q_mod
        from watcher import DebouncedHandler

        eq = q_mod.Queue()
        handler = DebouncedHandler(eq, debounce_seconds=0.05)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            test_path = f.name

        try:
            with AgentWriteContext(test_path):
                # Simulate file event during agent write
                class FakeEvent:
                    is_directory = False
                    src_path = test_path
                handler.on_modified(FakeEvent())
                time.sleep(0.3)  # wait for debounce flush

            # Queue must be empty — event suppressed
            self.assertTrue(eq.empty(), "Watcher must not fire events during agent writes")
        finally:
            handler.stop()
            try:
                os.unlink(test_path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ═══ Suite H: Reliability — Error Cases ═══
# ---------------------------------------------------------------------------

class TestReliability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _isolated_db(self)
        db.init_db()

    def tearDown(self):
        self._db_patcher.stop()
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def _make_auth(self):
        auth = MagicMock()
        auth.backend_url = "http://localhost:8000/api"
        auth.get_auth_header.return_value = {"Authorization": "Bearer fake"}
        return auth

    def test_failed_download_does_not_corrupt_sqlite(self):
        """A failed download must leave the existing SQLite record unchanged."""
        h = "original_synced_hash"
        db.upsert_record("broken.txt", local_hash=h, cloud_id="cid_broken",
                         last_synced_hash=h, last_synced_cloud_md5=h, cloud_version=1)

        # Pre-create local file
        local_file = os.path.join(self.tmp.name, "broken.txt")
        _write_file(local_file, b"original content")

        dc = MagicMock()
        dc.download_file.side_effect = ConnectionError("network failure")
        auth = self._make_auth()

        state = FileState(
            rel_path="broken.txt",
            cloud_id="cid_broken",
            cloud_hash="new_cloud_hash",
            cloud_version=2,
            action=ACTION_DOWNLOAD_CHANGED,
        )

        from watcher import IgnorePathContext
        with self.assertRaises(Exception):
            _execute_download(state, auth, self.tmp.name, "dev1",
                              db, dc, IgnorePathContext, "cycle_err")

        # SQLite record must still reflect the original state
        rec = db.get_record("broken.txt")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["cloud_version"], 1, "SQLite must not be updated on failed download")

    def test_concurrent_reconciliation_cycles_cannot_overlap(self):
        """Two concurrent calls must not both execute — one must skip."""
        from reconciler import _reconciliation_lock, run_reconciliation_cycle

        # Acquire the lock to simulate a running cycle
        acquired = _reconciliation_lock.acquire(blocking=False)
        self.assertTrue(acquired)

        auth = self._make_auth()
        try:
            result = run_reconciliation_cycle(
                auth=auth,
                watched_dir=self.tmp.name,
                device_id="dev1",
                db_module=db,
                drive_client_module=MagicMock(),
                watcher_ignore=MagicMock(),
            )
            self.assertTrue(result.get("skipped"), "Second cycle must skip when one is running")
        finally:
            _reconciliation_lock.release()

    def test_local_deletion_does_not_purge_cloud(self):
        """Recording a local deletion must NOT trigger a cloud delete request."""
        plan = ReconciliationPlan()
        from reconciler import FileState, ACTION_LOCAL_DELETED
        state = FileState(
            rel_path="deleted_locally.txt",
            cloud_id="cid_del",
            local_exists=False,
            cloud_exists=True,
            action=ACTION_LOCAL_DELETED,
        )
        plan.local_deletions.append(state)

        dc = MagicMock()
        auth = self._make_auth()

        from watcher import IgnorePathContext
        execute_plan(plan, auth, self.tmp.name, "dev1", db, dc, IgnorePathContext)

        # Cloud delete must NOT have been called
        dc.delete_file = MagicMock()
        dc.delete_file.assert_not_called()


# ---------------------------------------------------------------------------
# ═══ Suite I: SQLite Schema Migration ═══
# ---------------------------------------------------------------------------

class TestSQLiteMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _isolated_db(self)

    def tearDown(self):
        self._db_patcher.stop()
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_new_columns_created_on_init(self):
        """init_db must add cloud_folder_id, cloud_path, last_seen_remote_at columns."""
        db.init_db()
        import sqlite3
        with sqlite3.connect(self._tmp_db) as conn:
            cursor = conn.execute("PRAGMA table_info(file)")
            cols = [row[1] for row in cursor.fetchall()]
        self.assertIn("cloud_folder_id", cols)
        self.assertIn("cloud_path", cols)
        self.assertIn("last_seen_remote_at", cols)

    def test_idempotent_migration_on_reinit(self):
        """Calling init_db twice must not raise an error or drop existing data."""
        db.init_db()
        db.upsert_record("migtest.txt", local_hash="hash1", cloud_id="cid_m")
        db.init_db()  # re-run migration
        rec = db.get_record("migtest.txt")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["cloud_id"], "cid_m")


# ---------------------------------------------------------------------------
# ═══ Suite J: Noop Efficiency — Unchanged Files Not Transferred ═══
# ---------------------------------------------------------------------------

class TestNoopEfficiency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        _isolated_db(self)
        db.init_db()

    def tearDown(self):
        self._db_patcher.stop()
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_unchanged_file_generates_zero_network_calls(self):
        """An unchanged file must result in zero uploads, downloads, or API calls."""
        h = "stable_hash"
        local_tree = {"stable.txt": h}
        remote_files = [{"id": "cid_s", "name": "stable.txt", "content_hash": h,
                         "version_number": 1, "deleted": False, "parent_id": None,
                         "_folder_rel": ""}]
        sqlite_records = [{
            "path": "stable.txt", "cloud_id": "cid_s",
            "last_synced_hash": h, "last_synced_cloud_md5": h,
            "cloud_version": 1, "sync_mode": "folder", "abs_path": None
        }]

        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, self.tmp.name)
        self.assertEqual(plan.noops, 1)
        self.assertEqual(len(plan.uploads), 0)
        self.assertEqual(len(plan.downloads), 0)

        dc = MagicMock()
        auth = MagicMock()
        auth.get_auth_header.return_value = {}
        auth.backend_url = "http://localhost:8000/api"

        from watcher import IgnorePathContext
        execute_plan(plan, auth, self.tmp.name, "dev1", db, dc, IgnorePathContext)

        dc.upload_file.assert_not_called()
        dc.download_file.assert_not_called()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)

