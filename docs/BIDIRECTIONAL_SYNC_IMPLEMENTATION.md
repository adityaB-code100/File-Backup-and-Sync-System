# VaultCloud — Bidirectional Sync Implementation Summary

**Date**: November 2026  
**Author**: Senior Python / Distributed Systems Engineer  
**Scope**: Desktop agent bidirectional sync — BUG-01 (remote discovery) and BUG-02 (in-place update)

---

## 1. Files Modified

| File | Change Type | Summary |
|---|---|---|
| `app/sync_engine.py` | **Modified** | Replaced old `poll_remote_changes` (single-pass, SQLite-only) with delegation to new `reconciler.run_reconciliation_cycle`. Removed `get_cloud_updated_path` logic from polling path. All other functions (`handle_local_change`, `reconcile_conflict`, `sync_individual_file`, etc.) unchanged. |
| `app/watcher.py` | **Modified** | `DebouncedHandler.on_created` and `on_modified` now also check `reconciler.is_agent_writing()` in addition to the existing `IgnorePathContext`. Prevents watcher loops from agent-generated downloads. |
| `app/db.py` | **Modified** | `init_db()` migration adds three new columns: `cloud_folder_id`, `cloud_path`, `last_seen_remote_at`. All migrations are non-destructive (`ALTER TABLE ... ADD COLUMN` with existence checks). |
| `app/main.py` | **Modified** | `startup_reconciliation` now calls `run_reconciliation_cycle` for a full bidirectional initial sync instead of a local-only walk. Added imports for `drive_client`, `reconciler`, and `IgnorePathContext`. |

## 2. Files Created

| File | Purpose |
|---|---|
| `app/reconciler.py` | **New module** — the full bidirectional reconciliation engine. Contains: `fetch_remote_file_tree`, `scan_local_tree`, `classify_file_state`, `build_reconciliation_plan`, `execute_plan`, `_execute_upload`, `_execute_download`, `_execute_conflict`, `run_reconciliation_cycle`, `AgentWriteContext`, `is_agent_writing`. |
| `app/test_bidirectional_sync.py` | **New test file** — 45 automated tests across 10 test suites covering the decision table, plan builder, atomic download, remote discovery, conflict handling, loop prevention, reliability, and SQLite migration. |
| `docs/BIDIRECTIONAL_SYNC_ARCHITECTURE.md` | Architecture documentation |
| `docs/BIDIRECTIONAL_SYNC_TEST_REPORT.md` | Test execution report |
| `docs/BIDIRECTIONAL_SYNC_IMPLEMENTATION.md` | This file |

## 3. Files NOT Modified

All other files remain exactly as they were. Specifically:

- `app/drive_client.py` — no changes (existing `download_file`, `upload_file`, `acquire_lock`, `release_lock`, `find_drive_file` are reused)
- `app/auth.py` — no changes
- `app/gui.py` — no changes
- `app/db.py` schema v1 columns — preserved exactly
- All backend files (`backend/**`) — no changes required
- All frontend files (`frontend/**`) — no changes required
- All existing tests — no test assertions were weakened or removed

## 4. Database Schema Changes

### SQLite `app/sync_state.db`

Three columns added non-destructively:

```sql
ALTER TABLE file ADD COLUMN cloud_folder_id TEXT;
ALTER TABLE file ADD COLUMN cloud_path TEXT;
ALTER TABLE file ADD COLUMN last_seen_remote_at TEXT;
```

Each is guarded by:
```python
if 'column_name' not in existing_cols:
    conn.execute("ALTER TABLE file ADD COLUMN ...")
```

**Migration is idempotent**: running `init_db()` twice does not error or drop existing data.

**Backward compatibility**: existing rows get `NULL` for new columns, which is handled safely throughout the codebase.

## 5. API Changes

**None.** All reconciler operations use existing, documented API endpoints:

- `GET /api/folders/` — full folder tree fetch
- `GET /api/files/?limit=200&offset=N` — paginated file listing
- `GET /api/files/<id>/content/` — streaming decrypted download
- `POST /api/files/` — new file upload
- `PUT /api/files/<id>/content/` — file content update
- `POST /api/files/<id>/lock/` — distributed lock acquisition
- `DELETE /api/files/<id>/unlock/` — lock release

No new backend endpoints were added. No existing endpoints were changed.

## 6. Important Implementation Decisions

### Decision 1: `poll_remote_changes` delegates to reconciler, not replaced
The function signature `poll_remote_changes(auth, watched_dir)` is preserved for backward compatibility with `main.py` and GUI code. Its body now calls `run_reconciliation_cycle`. This avoids touching GUI integration code.

### Decision 2: Atomic downloads use `os.replace` (not `shutil.move`)
`os.replace` is an OS-level atomic operation on POSIX and Windows. Temp and destination must be on the same filesystem (guaranteed because we place the temp file in the same directory as the destination).

### Decision 3: `AgentWriteContext` is a second, independent guard alongside `IgnorePathContext`
`IgnorePathContext` is a context variable in `watcher.py`. `AgentWriteContext` lives in `reconciler.py`. Using two independent guards ensures that even if one module is refactored, the loop prevention remains robust. The import of `reconciler` from `watcher` is deferred (`from reconciler import is_agent_writing` inside the method) to avoid a circular import at module load time.

### Decision 4: Cloud is authoritative on first encounter with differing content
When a file exists on both sides but neither has a SQLite record (first-time sync), and the hashes differ, the cloud version is downloaded. Rationale: the cloud is the canonical store; local copies may be stale or partial.

### Decision 5: Deletions are never automatically propagated
Neither local deletion → cloud purge nor cloud deletion → local purge is performed automatically. Both are recorded in SQLite as status changes only. This avoids irreversible data loss from transient network errors.

### Decision 6: One reconciliation cycle at a time
`_reconciliation_lock = threading.Lock()` with `blocking=False` ensures that if a cycle is already running when the 30-second timer fires, the new cycle is silently skipped. This prevents memory accumulation and double-action on the same files.

### Decision 7: `get_cloud_updated_path` is kept in sync_engine.py but no longer called from polling
The function and its `(cloud updated)` naming logic remain in `sync_engine.py` as dead code for now. It is NOT called by the reconciler. It could be removed in a future cleanup commit.

## 7. Backward Compatibility

| Concern | Status |
|---|---|
| Existing SQLite data (`sync_state.db`) | **Fully preserved** — schema migration is additive only |
| Existing cloud files and MongoDB documents | **Untouched** — no backend changes |
| Existing JWT authentication flow | **Unchanged** |
| Existing individual file tracking (GUI) | **Unchanged** — `sync_individual_file` and `upload_new_individual_file` remain identical |
| Existing watcher event handling | **Unchanged** — only new suppression check added in `on_modified`/`on_created` |
| Existing test assertions | **All 32 previous tests still pass** — no assertions weakened |

## 8. How to Run the Desktop Agent

### Standard startup (bidirectional sync active):
```bash
# From E:\backup-sync\app\
python -m app.main ./synced_folder

# Or with explicit credentials:
python -m app.main ./synced_folder --email user@example.com --password <secret>
```

### CLI mode (headless, no GUI):
```bash
python main.py ./synced_folder
```

### GUI mode:
```bash
python gui.py
```

### Run all desktop tests:
```bash
cd E:\backup-sync\app

# New bidirectional sync tests (45 tests)
python -m unittest test_bidirectional_sync -v

# Existing account isolation + individual sync + duplicate handling (32 tests)
python -m unittest test_account_isolation test_individual_sync test_duplicate_filename -v

# All desktop tests at once (77 tests)
python -m unittest test_bidirectional_sync test_account_isolation test_individual_sync test_duplicate_filename -v
```

### Environment variables:
```bash
# Backend URL (defaults to http://localhost:8000/api)
set VAULTCLOUD_BACKEND_URL=http://your-backend.example.com/api
```

## 9. Known Remaining Limitations

| Limitation | Severity | Notes |
|---|---|---|
| In-memory file hash buffering for large files | HIGH | The backend crypto layer still buffers the entire file in RAM. Upload/download of files > 1 GB may OOM. This is a backend issue (crypto_utils.py), not a sync engine issue. |
| Secondary backup on same physical disk | HIGH | Infrastructure issue — not addressable in software. |
| Automatic deletion propagation absent | MEDIUM | By design. Manual cloud delete via web dashboard or future explicit sync action required. |
| `get_cloud_updated_path` dead code remains | LOW | The function exists in sync_engine.py but is no longer called from the polling path. Safe to remove in a future cleanup. |
| Watcher suppression import is deferred | INFORMATIONAL | `from reconciler import is_agent_writing` is called inside each event handler to avoid circular import. Performance impact is negligible (Python module cache hit after first import). |
| Git branch creation blocked | INFORMATIONAL | Windows file permission on `.git/refs/heads/` prevents creating `.lock` files in the sandbox. All changes were committed to `main`. |
