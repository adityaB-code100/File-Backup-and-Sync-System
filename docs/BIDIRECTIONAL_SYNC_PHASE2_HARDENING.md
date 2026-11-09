# VaultCloud — Bidirectional Sync Phase 2: Data Integrity & Reliability Hardening

**Document Version**: 2.0  
**Date**: November 2026  
**Repository**: `E:\backup-sync` (Branch: `main`)  
**Status**: Implemented & Verified with 109 Automated Tests  

---

## Executive Overview

Phase 1 established the foundation for bidirectional synchronization between the VaultCloud Python desktop agent and Django REST API backend (`app/reconciler.py`), fixing remote file discovery (BUG-01) and duplicate `(cloud updated)` file proliferation (BUG-02).

Phase 2 focuses strictly on **data preservation, predictable reconciliation, and recovery after interruption**. It hardens four edge cases:
1. **Cloud Deletion Tombstone & Re-Upload Prevention**: Preserves local files when cloud counterparts are deleted while guaranteeing the desktop agent never recreates deleted cloud files.
2. **Reliable Watcher Loop Prevention**: Replaces fragile context-only suppression with hash-verified suppression (`WriteSuppressionRegistry`), immune to OS event latency while preserving immediate user edits.
3. **Safe First-Time Synchronization**: Eliminates silent local overwrites on first encounter divergence by adopting a safe dual-preservation conflict policy.
4. **Conflict Copy Lifecycle**: Formally defines local-only conflict copy semantics, preventing sync loops, redundant conflict copies, and cloud storage pollution.

---

## 1. Issue 1: Cloud Deletion Tombstone and Re-Upload Prevention

### 1.1 Issue Reproduction
1. Synchronize `report.txt` between local watched folder and cloud storage. SQLite records `status="Synced"`, `cloud_id="cid123"`, and `last_synced_hash`.
2. Delete the file on the cloud via the web dashboard (or soft-delete via API).
3. Run desktop reconciliation cycle 1:
   - `build_reconciliation_plan` classifies `report.txt` as `ACTION_CLOUD_DELETED`.
   - `execute_plan` logs that the cloud copy was deleted and previously executed `db_module.delete_record(state.rel_path)`.
4. Run reconciliation cycle 2:
   - `report.txt` still exists on local disk (preserved for user safety).
   - Because `delete_record` wiped out its SQLite history, `sqlite_records` has no record for `report.txt`.
   - In Pass 3 of `build_reconciliation_plan`, `report.txt` is treated as a brand-new local file (`ACTION_UPLOAD_NEW`).
   - The desktop agent uploads `report.txt` to the cloud, resurrecting the file the user explicitly deleted on the web dashboard!

### 1.2 Root Cause
The Phase 1 implementation deleted the SQLite state record (`db_module.delete_record`) upon observing a remote 404/deleted file. Without persistent local memory that the cloud file was deleted, the subsequent reconciliation cycle observed `local_exists=True, cloud_exists=False, in_sqlite=False`, which incorrectly matched the condition for a new local file waiting to be uploaded.

Furthermore, in `fetch_remote_file_tree`, network errors or HTTP errors during pagination broke out of the loop and returned a partial file list, which caused unaffected remote files on subsequent pages to appear missing and trigger false deletions.

### 1.3 Fix Implemented
1. **Persistent SQLite Tombstone (`is_tombstone=1`, `status="CloudDeleted"`)**:
   Instead of deleting the row from SQLite, `execute_plan` calls `db_module.set_tombstone(state.rel_path)`. The row is preserved with its `last_synced_hash`, `status="CloudDeleted"`, and `is_tombstone=1`.
2. **Decision Table Enforcement**:
   In `classify_file_state`, when `state.status == "CloudDeleted"` or `state.is_tombstone == 1`:
   - If `cloud_exists == False` and `local_exists == True`:
     - If `local_hash == state.last_synced_hash`, returns `ACTION_NOOP`. The local file remains preserved, and no upload is queued.
     - The agent remembers the deletion across cycles and application restarts.
   - If both local and cloud copies are absent, returns `ACTION_BOTH_DELETED`.
   - If the file is subsequently recreated in the cloud (`cloud_exists == True`), the tombstone is cleared upon successful sync.
3. **Fail-Fast Remote Fetching**:
   `fetch_remote_file_tree` and `_build_folder_path_map` now raise `RuntimeError` on any page request failure. `run_reconciliation_cycle` catches the exception and aborts the cycle with `{"skipped": True}`, preventing network timeouts from ever being mistaken for cloud deletions.

---

## 2. Issue 2: Reliable Watcher Loop Prevention

### 2.1 Issue Reproduction
1. Desktop agent initiates a download or in-place conflict resolution replacement in `_execute_download`.
2. `_execute_download` wraps the atomic replace in `AgentWriteContext(abs_dest)`.
3. The atomic replace (`os.replace`) completes and `AgentWriteContext` exits.
4. On Windows / macOS, OS filesystem event notifications from the watchdog observer can arrive with a delay (e.g. 50ms to 500ms), or sit in watchdog's event queue.
5. When `DebouncedHandler.on_modified` or `on_created` executes, `is_agent_writing(abs_path)` is already `False`.
6. The handler schedules a `changed` event.
7. The flusher thread dequeues the event and triggers an upload back to the cloud, creating an unnecessary network write or infinite sync echo.

### 2.2 Root Cause
Transient, context-manager-based suppression (`AgentWriteContext`) only suppresses events that fire synchronously during the exact lifetime of the context manager block. OS filesystem event delivery is asynchronous and decoupled from Python thread execution, so delayed events frequently arrive after the context has exited.

### 2.3 Fix Implemented: `WriteSuppressionRegistry`
Implemented a thread-safe, hash-verified suppression registry in `app/watcher.py`:

```python
class WriteSuppressionRegistry:
    def record_suppression(self, path: str, expected_sha256: str, ttl: float = 30.0)
    def should_suppress(self, path: str, current_hash: Optional[str] = None) -> bool
    def cancel_suppression(self, path: str)
```

1. **Hash Verification Protocol**: When the reconciler writes or replaces a file, it registers the normalized canonical path and expected SHA-256 hash with a 30-second TTL.
2. **Verification on Event Arrival**: When `on_created` or `on_modified` fires, `should_suppress(abs_path)` inspects the registry:
   - If the on-disk SHA-256 matches `expected_sha256`, the event is confirmed to be agent-generated and is suppressed.
   - If the on-disk SHA-256 does NOT match, a legitimate user edit occurred immediately following the download. The registry cancels suppression and allows the event to proceed.
3. **Duplicate Event Immunity**: Multiple events for the same file write (e.g., `on_created` followed by multiple `on_modified` events on Windows) are all suppressed without consuming or invalidating the registry entry prematurely.
4. **Bounded Memory**: Registry entries expire after the TTL. An internal lock protects concurrent access, and entries are capped at 10,000 items with LRU eviction.

---

## 3. Issue 3: Safe First-Time Synchronization

### 3.1 Issue Reproduction
1. Local folder contains `Documents/report.txt` with `LOCAL_CONTENT` (hash $H_L$).
2. Cloud storage contains `Documents/report.txt` with `CLOUD_CONTENT` (hash $H_C$), where $H_L \neq H_C$.
3. SQLite has no tracking record for this file (fresh agent install or newly configured watched directory).
4. Run reconciliation.
5. In Phase 1, `classify_file_state` executed:
   ```python
   if not last_local and not last_cloud:
       if local_hash == cloud_hash: return ACTION_NOOP
       return ACTION_DOWNLOAD_CHANGED  # Cloud was treated as authoritative!
   ```
6. The desktop agent downloaded `CLOUD_CONTENT` and atomically replaced `Documents/report.txt`.
7. **`LOCAL_CONTENT` was silently overwritten and permanently destroyed without warning.**

### 3.2 Root Cause
The Phase 1 decision table used a "cloud authoritative" default on first encounter, assuming local content was either stale or disposable. This violated the core safety rule: **never silently destroy user data**.

### 3.3 Fix Implemented
Adopted a strict **Dual-Preservation Conflict Policy** for first-time sync divergence:
1. When `local_exists=True`, `cloud_exists=True`, and `last_synced_hash=None`:
   - If `local_hash == cloud_hash`: classified as `ACTION_NOOP` (both sides agree; adopt silently).
   - If `local_hash != cloud_hash`: classified as `ACTION_CONFLICT`.
2. Execution via `_execute_conflict`:
   - The user's original local file is copied to `Documents/report (conflict from cloud {YYYY-MM-DD HHMMSS}).txt`.
   - The cloud version is downloaded in-place into `Documents/report.txt`.
   - The canonical path is mapped to the cloud ID with `status="Synced"`.
   - The conflict copy is recorded in SQLite with `status="Conflict"`, `cloud_id=None`, and `conflict_original_path="Documents/report.txt"`.
3. Subsequent reconciliation cycles evaluate the canonical file as `noop` (matching cloud) and the conflict copy as `noop` (local-only), preventing repeated conflict loops.

---

## 4. Issue 4: Conflict Copy Lifecycle

### 4.1 Issue Reproduction
1. A conflict occurs, creating `report (conflict from cloud 2026-11-05 120000).txt`.
2. The conflict copy is saved in SQLite with `status="Conflict"` and `cloud_id=None`.
3. On the next reconciliation cycle:
   - `local_tree` contains the conflict file.
   - Remote tree does NOT contain the conflict file.
   - Pass 1 / Pass 3 of `build_reconciliation_plan` saw `cloud_id=None`, which fell into `ACTION_UPLOAD_NEW`.
   - The desktop agent uploaded the conflict copy to the cloud.
   - Other linked client devices downloaded the conflict file, causing sync storms and cloud clutter.

### 4.2 Root Cause
The reconciler lacked explicit classification rules for conflict copies in SQLite. Any local file without a `cloud_id` was automatically presumed to be a user file needing first-time upload.

### 4.3 Fix Implemented
1. **Explicit Local-Only Semantics**:
   In `classify_file_state`:
   ```python
   if state.status == "Conflict" and state.cloud_id is None:
       if local_exists:
           return ACTION_NOOP
       return ACTION_BOTH_DELETED
   ```
2. **Lifecycle Rules**:
   - Preserved on local disk for user review, diffing, and manual merging.
   - Never automatically uploaded to the cloud.
   - If the user renames the file to a standard name (e.g. `final_report_v2.txt`), it is treated as a new user file and uploaded normally.
   - If the user deletes the conflict copy locally, the SQLite record is retired (`ACTION_BOTH_DELETED`).
   - SQLite schema v3 persists `conflict_original_path`, linking the conflict copy directly to its progenitor across restarts.

---

## 5. SQLite Schema Upgrades

Migrations are additive, non-destructive, and idempotent (`db.init_db()`):

```sql
-- Phase 1 additions (Schema v2)
ALTER TABLE file ADD COLUMN cloud_folder_id TEXT;
ALTER TABLE file ADD COLUMN cloud_path TEXT;
ALTER TABLE file ADD COLUMN last_seen_remote_at TEXT;

-- Phase 2 additions (Schema v3)
ALTER TABLE file ADD COLUMN is_tombstone INTEGER DEFAULT 0;
ALTER TABLE file ADD COLUMN conflict_original_path TEXT;
```

Compatibility guarantees:
- Existing databases run without error; columns are added only if missing.
- Existing rows default `is_tombstone = 0` and `conflict_original_path = NULL`.
- `upsert_record()` preserves existing values when optional fields are omitted.
- `set_tombstone(path, is_tombstone=1)` provides an explicit, atomic API for deletion tracking.

---

## 6. Files Changed in Phase 2

| File | Change Type | Lines Changed | Description |
|---|:---:|:---:|---|
| `app/db.py` | Modified | +25 lines | Added schema v3 migrations (`is_tombstone`, `conflict_original_path`), updated `upsert_record`, added `set_tombstone()` helper. |
| `app/watcher.py` | Modified | +95 lines | Implemented `WriteSuppressionRegistry`, integrated hash-verified suppression into `DebouncedHandler` and `IndividualFileHandler`. |
| `app/reconciler.py` | Modified | +65 lines | Added tombstone and conflict copy classification rules, updated first-time sync conflict divergence, integrated hash-suppression registration on download/conflict, added fail-fast remote fetch error propagation. |
| `app/test_bidirectional_sync.py` | Modified | +18 lines | Updated first-time sync test assertion to `ACTION_CONFLICT`, resolved test mock file handle warnings. |
| `app/test_phase2_hardening.py` | **New** | 390 lines | 22 comprehensive unit and integration tests covering tombstones, suppression, first-sync, conflict lifecycle, and the 10 scenario tests. |
| `docs/BIDIRECTIONAL_SYNC_ARCHITECTURE.md` | Modified | +60 lines | Updated architecture specifications for Phase 2 hardening. |
| `docs/BIDIRECTIONAL_SYNC_IMPLEMENTATION.md` | Modified | +20 lines | Updated implementation summary and decisions. |
| `docs/BIDIRECTIONAL_SYNC_TEST_REPORT.md` | Modified | +70 lines | Corrected arithmetic discrepancy and established clear test categorization. |
| `docs/BIDIRECTIONAL_SYNC_PHASE2_HARDENING.md` | **New** | 280 lines | This comprehensive Phase 2 hardening document. |

---

## 7. Automated Test Execution & Results

### 7.1 Phase 2 Hardening Suite (`test_phase2_hardening.py`)
**Command**: `cd E:\backup-sync\app && python -m unittest test_phase2_hardening -v`  
**Result**: **22/22 PASSED in 1.664s** (Exit Code: 0)

1. `test_reproduce_cloud_deletion_no_reupload_cycle`: Verified cycle 1 tombstone and cycle 2 NO-OP (PASS).
2. `test_network_failure_does_not_trigger_false_deletion`: Verified `RuntimeError` on API failure prevents false deletion (PASS).
3. `test_both_sides_deleted_cleans_up_safely`: Verified `ACTION_BOTH_DELETED` (PASS).
4. `test_delayed_event_suppressed_by_hash`: Verified suppression after context exit (PASS).
5. `test_duplicate_events_both_suppressed`: Verified multi-event OS notification handling (PASS).
6. `test_immediate_user_modification_not_suppressed`: Verified user edits immediately after download are preserved (PASS).
7. `test_failed_download_does_not_suppress_existing_file`: Verified error boundary (PASS).
8. `test_ttl_expiration_purges_suppression`: Verified bounded suppression lifetime (PASS).
9. `test_bounded_cleanup_caps_memory`: Verified 10,000 capacity ceiling with LRU eviction (PASS).
10. `test_first_sync_divergence_preserves_both_versions`: Verified dual-preservation conflict policy (PASS).
11. `test_conflict_copy_is_noop_on_subsequent_cycles`: Verified conflict copies are local-only NO-OP (PASS).
12. `test_conflict_records_survive_agent_restart`: Verified SQLite durability across process restarts (PASS).
13. `test_scenario_01_dashboard_upload_to_desktop_discovery`: End-to-end scenario 1 (PASS).
14. `test_scenario_02_dashboard_update_to_local_inplace_replacement`: End-to-end scenario 2 (PASS).
15. `test_scenario_03_local_upload_to_cloud_discovery`: End-to-end scenario 3 (PASS).
16. `test_scenario_04_local_update_to_cloud_update`: End-to-end scenario 4 (PASS).
17. `test_scenario_05_cloud_deletion_no_automatic_reupload`: End-to-end scenario 5 (PASS).
18. `test_scenario_06_delayed_watcher_event_no_upload_loop`: End-to-end scenario 6 (PASS).
19. `test_scenario_07_first_sync_conflict_preserves_both`: End-to-end scenario 7 (PASS).
20. `test_scenario_08_conflict_copy_no_repeated_conflict`: End-to-end scenario 8 (PASS).
21. `test_scenario_09_network_failure_no_false_deletion`: End-to-end scenario 9 (PASS).
22. `test_scenario_10_agent_restart_state_restored`: End-to-end scenario 10 (PASS).

### 7.2 Full Combined Test Suite
**Command**: `cd E:\backup-sync\app && python -m unittest test_phase2_hardening test_bidirectional_sync test_account_isolation test_individual_sync test_duplicate_filename`  
**Result**: **99/99 PASSED in 27.071s** (Exit Code: 0)

### 7.3 Cryptographic & Disaster Recovery Verification
**Command**: `python C:\...\scratch\audit_crypto_backup.py`  
**Result**: **10/10 PASSED in 0.203s** (Exit Code: 0)

### 7.4 Frontend Production Build
**Command**: `cd E:\backup-sync\frontend && npm run build`  
**Result**: **1887 modules transformed, 0 errors, built in 782ms** (Exit Code: 0)

---

## 8. Remaining Known Limitations

While Phase 2 delivers predictable data integrity and eliminates false overwrites, loops, and re-uploads, the following limitations remain:

1. **Large File Streaming & RAM Usage**: The backend crypto utility (`backend/files/crypto_utils.py`) currently buffers file content in memory during encryption and decryption. Files exceeding 1 GB can cause `MemoryError` on memory-constrained servers. Chunk-based streaming encryption remains recommended for a future backend milestone.
2. **Secondary Backup Storage Location**: Secondary backups (`D:\VaultCloudBackup`) reside on the same physical NVMe SSD as drive `E:`. True disaster recovery against physical drive failure requires an off-site S3/GCS bucket or a physically separate device.
3. **Pagination Limit on `/api/folders/`**: The folders API does not return a total `count` field. The agent paginates using `limit=200` until `len(results) < limit`. While functional for standard folder hierarchies, an explicit backend `count` header would improve formal contract compliance.
4. **Backend Django Tests Network Boundary**: Backend unit tests (`backend/files/tests.py`) require direct network access to MongoDB Atlas (`_mongodb._tcp...`). When running in restricted sandbox environments without live Atlas DNS, backend tests must be run with external network clearance.

