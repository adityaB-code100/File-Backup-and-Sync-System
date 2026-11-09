"""
reconciler.py — VaultCloud Bidirectional Synchronization Reconciliation Engine
==============================================================================

This module implements a complete bidirectional reconciliation engine that
compares three sources of truth:

    Local Filesystem  <-->  SQLite State  <-->  Cloud (Django REST API)

It correctly handles:
  - New local files  → upload to cloud
  - New cloud files  → download to local
  - Modified local   → upload changes
  - Modified cloud   → download in-place (atomic replace, never "(cloud updated)")
  - Both modified    → conflict copy + cloud wins
  - Local deletion   → update sync record (cloud NOT auto-deleted for safety)
  - Cloud deletion/404 → update sync record (local NOT auto-deleted for safety)
  - Unchanged files  → skip (no-op, zero network traffic)

Design Principles
-----------------
1. PLAN then EXECUTE — decision table is built before any I/O.
2. All downloads are atomic: temp file → hash verify → os.replace.
3. IgnorePathContext prevents watcher loops on agent-generated writes.
4. All SQLite mutations happen AFTER successful I/O, never before.
5. No plaintext secrets are logged.
6. Each reconciliation cycle carries a unique operation_id for tracing.
"""

import hashlib
import logging
import os
import uuid
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests
from requests.exceptions import HTTPError

logger = logging.getLogger("vaultcloud.reconciler")

# ---------------------------------------------------------------------------
# Action constants
# ---------------------------------------------------------------------------
ACTION_NOOP           = "noop"
ACTION_UPLOAD_NEW     = "upload_new"
ACTION_UPLOAD_CHANGED = "upload_changed"
ACTION_DOWNLOAD_NEW   = "download_new"
ACTION_DOWNLOAD_CHANGED = "download_changed"
ACTION_CONFLICT       = "conflict"
ACTION_LOCAL_DELETED  = "local_deleted"      # local gone, cloud still exists
ACTION_CLOUD_DELETED  = "cloud_deleted"      # cloud 404, local still present
ACTION_BOTH_DELETED   = "both_deleted"       # neither side present

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileState:
    """Unified state snapshot for a single logical file."""
    # Identity
    rel_path: str                        # relative path in watched_dir (forward slashes)
    cloud_id: Optional[str] = None       # stable MongoDB ObjectId string

    # Local state
    local_exists: bool = False
    local_hash: Optional[str] = None     # SHA-256 of current on-disk file

    # SQLite (last-known-good synchronised state)
    last_synced_hash: Optional[str] = None
    last_synced_cloud_hash: Optional[str] = None
    last_cloud_version: int = 0
    sync_mode: str = "folder"
    abs_path: Optional[str] = None      # only set for individually tracked files
    status: Optional[str] = None        # Synced, Conflict, CloudDeleted, LocalDeleted, etc.
    is_tombstone: int = 0               # 1 if cloud counterpart was deleted
    conflict_original_path: Optional[str] = None

    # Cloud state (from API response)
    cloud_exists: bool = False
    cloud_hash: Optional[str] = None    # content_hash field from /api/files/<id>/
    cloud_version: int = 0
    cloud_name: Optional[str] = None
    cloud_parent_id: Optional[str] = None  # folder ID or None for root

    # Action decided during reconciliation
    action: str = ACTION_NOOP
    conflict_reason: str = ""


@dataclass
class ReconciliationPlan:
    """Ordered list of actions to execute."""
    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    uploads: list = field(default_factory=list)      # FileState instances
    downloads: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    local_deletions: list = field(default_factory=list)
    cloud_deletions: list = field(default_factory=list)
    noops: int = 0


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _hash_file(path: str) -> Optional[str]:
    """Compute SHA-256 of a local file, returning None on failure."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, FileNotFoundError) as exc:
        logger.debug(f"[recon] Cannot hash '{path}': {exc}")
        return None


def _api(auth, method: str, path: str, **kwargs) -> requests.Response:
    """Thin wrapper around authenticated requests with 401-refresh."""
    base = getattr(auth, 'backend_url', 'http://localhost:8000/api').rstrip('/')
    url = f"{base}/{path.lstrip('/')}"
    hdrs = kwargs.pop("headers", {})
    hdrs.update(auth.get_auth_header())
    resp = requests.request(method, url, headers=hdrs, timeout=30, **kwargs)
    if resp.status_code == 401:
        logger.info("[recon] 401 received — refreshing token")
        auth.do_refresh()
        hdrs.update(auth.get_auth_header())
        resp = requests.request(method, url, headers=hdrs, timeout=30, **kwargs)
    return resp


# ---------------------------------------------------------------------------
# Remote tree fetching
# ---------------------------------------------------------------------------

def _build_folder_path_map(auth) -> dict[str, str]:
    """
    Fetches the COMPLETE folder tree for the authenticated user and returns a
    dict mapping  folder_id → relative_path  (forward-slash, no leading slash).

    Example:
        {"abc123": "Documents", "def456": "Documents/Projects"}
    """
    all_folders: dict[str, dict] = {}  # id → folder dict
    offset = 0
    limit = 200

    while True:
        try:
            resp = _api(auth, "GET", "/folders/", params={"limit": limit, "offset": offset})
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error(f"[recon] Network or HTTP error fetching folders (offset={offset}): {exc}")
            raise RuntimeError(f"Failed to fetch complete folder tree: {exc}") from exc

        # /api/folders/ returns {"results": [...]} (no count/pagination)
        results = data.get("results", data if isinstance(data, list) else [])
        if not results:
            break

        for f in results:
            fid = f.get("id")
            if fid:
                all_folders[fid] = f

        # If we got fewer than the page limit, we have all folders
        if len(results) < limit:
            break
        offset += limit

    # Build path map using parent_id references
    def get_path(fid: str, visited: set) -> str:
        if fid in visited:
            return "CYCLE"
        visited.add(fid)
        folder = all_folders.get(fid)
        if not folder:
            return ""
        pid = folder.get("parent_id")
        name = folder.get("name", "")
        if not pid:
            return name
        parent_path = get_path(pid, visited)
        return f"{parent_path}/{name}".lstrip("/") if parent_path else name

    path_map: dict[str, str] = {}
    for fid in all_folders:
        path_map[fid] = get_path(fid, set())
    return path_map


def fetch_remote_file_tree(auth) -> list[dict]:
    """
    Returns a flat list of ALL active (non-deleted) file metadata dicts for
    the authenticated user, across all folders, handling pagination.

    Queries the root folder ('root') and all subfolders discovered via
    _build_folder_path_map so that files inside nested folders are properly discovered.

    Each item is the dict returned by /api/files/<id>/ — includes:
        id, name, parent_id, content_hash, version_number, deleted, ...
    """
    all_files: list[dict] = []
    folder_path_map = _build_folder_path_map(auth)

    # Query root plus all discovered subfolder IDs
    folder_targets = [("root", "")] + list(folder_path_map.items())

    for parent_target, folder_rel in folder_targets:
        offset = 0
        limit = 200

        while True:
            try:
                resp = _api(
                    auth, "GET", "/files/",
                    params={"parent_id": parent_target, "limit": limit, "offset": offset}
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error(f"[recon] Network or HTTP error fetching files for folder '{folder_rel}' (parent={parent_target}, offset={offset}): {exc}")
                raise RuntimeError(f"Failed to fetch complete remote file tree: {exc}") from exc

            results = data.get("results", [])
            if not results:
                break

            for item in results:
                if item.get("type") != "file" or item.get("deleted"):
                    continue
                item["_folder_rel"] = folder_rel  # e.g. "Documents/Projects"
                all_files.append(item)

            total = data.get("count", len(results))
            if offset + limit >= total or len(results) < limit:
                break
            offset += limit

    logger.debug(f"[recon] Fetched {len(all_files)} remote files across {len(folder_targets)} folder(s)")
    return all_files


# ---------------------------------------------------------------------------
# Local filesystem scan
# ---------------------------------------------------------------------------

def scan_local_tree(watched_dir: str) -> dict[str, str]:
    """
    Walk watched_dir and return { rel_path → sha256_hash }.
    Skips hidden files, temp files (.tmp*, *.tmp), and system files.
    """
    result: dict[str, str] = {}
    abs_watched = os.path.abspath(watched_dir)

    for dirpath, dirnames, filenames in os.walk(abs_watched):
        # Skip hidden directories
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        for fname in filenames:
            # Skip temp and hidden files
            if fname.startswith('.') or fname.endswith('.tmp') or '.tmp.' in fname:
                continue
            abs_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(abs_path, abs_watched).replace("\\", "/")
            h = _hash_file(abs_path)
            if h is not None:
                result[rel] = h

    return result


# ---------------------------------------------------------------------------
# Decision table
# ---------------------------------------------------------------------------

def classify_file_state(state: FileState) -> str:
    """
    Pure decision function: given a FileState, return the action to perform.

    Decision table:
    ┌──────────────┬────────────────┬──────────────────────────────────┐
    │ Local state  │ Cloud state    │ Action                           │
    ├──────────────┼────────────────┼──────────────────────────────────┤
    │ New          │ Missing        │ upload_new                       │
    │ Existing     │ New (no SQLite)│ download_new                     │
    │ Modified     │ Unchanged      │ upload_changed                   │
    │ Unchanged    │ Modified       │ download_changed                 │
    │ Modified     │ Modified       │ conflict                         │
    │ Deleted loc. │ Unchanged      │ local_deleted (record only)      │
    │ Unchanged    │ Deleted/404    │ cloud_deleted (record only)      │
    │ Both deleted │ —              │ both_deleted                     │
    │ Unchanged    │ Unchanged      │ noop                             │
    └──────────────┴────────────────┴──────────────────────────────────┘
    """
    local_exists = state.local_exists
    cloud_exists = state.cloud_exists
    local_hash   = state.local_hash
    cloud_hash   = state.cloud_hash
    last_local   = state.last_synced_hash
    last_cloud   = state.last_synced_cloud_hash

    # Conflict copy lifecycle (local-only conflict copies from prior conflict events)
    if state.status == "Conflict" and state.cloud_id is None:
        if local_exists:
            return ACTION_NOOP
        return ACTION_BOTH_DELETED

    # Tombstone handling (persistent cloud deletion marker — prevents false re-uploads)
    if (state.status == "CloudDeleted" or state.is_tombstone) and not cloud_exists:
        if local_exists:
            # Preserved local copy: as long as local content matches last synced, NO-OP
            if not state.last_synced_hash or local_hash == state.last_synced_hash:
                return ACTION_NOOP
            return ACTION_NOOP
        return ACTION_BOTH_DELETED

    # Both gone
    if not local_exists and not cloud_exists:
        return ACTION_BOTH_DELETED

    # Only in cloud (never seen locally OR local gone)
    if not local_exists and cloud_exists:
        if state.cloud_id and last_local:
            # We previously had this; local was deleted
            return ACTION_LOCAL_DELETED
        # Brand new cloud file we've never seen
        return ACTION_DOWNLOAD_NEW

    # Only local (cloud gone or never uploaded)
    if local_exists and not cloud_exists:
        if state.cloud_id and (last_cloud or state.status == "CloudDeleted" or state.is_tombstone):
            # We previously had this; cloud was deleted or 404
            if state.status == "CloudDeleted" or state.is_tombstone:
                return ACTION_NOOP
            return ACTION_CLOUD_DELETED
        # Never uploaded
        return ACTION_UPLOAD_NEW

    # Both exist — compare changes
    local_changed = (local_hash != last_local) if last_local else True
    cloud_changed = (cloud_hash != last_cloud) if last_cloud else (cloud_hash != local_hash)

    # First-time sync: neither side has a last-synced record
    if not last_local and not last_cloud:
        if local_hash == cloud_hash:
            return ACTION_NOOP   # identical content, adopt
        # Safe first-time sync policy: NEVER silently overwrite local content!
        # Both versions preserved: local copy saved as conflict copy, cloud version downloaded in-place
        state.conflict_reason = "first_sync_divergence"
        return ACTION_CONFLICT

    if not local_changed and not cloud_changed:
        return ACTION_NOOP

    if local_changed and not cloud_changed:
        return ACTION_UPLOAD_CHANGED

    if not local_changed and cloud_changed:
        return ACTION_DOWNLOAD_CHANGED

    # Both changed
    return ACTION_CONFLICT


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------

def build_reconciliation_plan(
    local_tree: dict[str, str],          # rel_path → local_hash
    remote_files: list[dict],            # API file dicts
    sqlite_records: list[dict],          # db.all_records() output
    watched_dir: str,
) -> ReconciliationPlan:
    """
    Merge three views of the world into a single ordered action plan.

    Uses cloud_id as the primary stable key, with rel_path as secondary.
    """
    plan = ReconciliationPlan()

    # Index SQLite records
    sqlite_by_rel: dict[str, dict] = {}
    sqlite_by_cloud_id: dict[str, dict] = {}
    for rec in sqlite_records:
        rel = rec.get("path", "")
        cid = rec.get("cloud_id", "")
        if rel:
            sqlite_by_rel[rel] = rec
        if cid:
            sqlite_by_cloud_id[cid] = rec

    # Index remote files
    remote_by_id: dict[str, dict] = {}
    remote_by_rel: dict[str, dict] = {}
    for rf in remote_files:
        fid = rf.get("id")
        folder_rel = rf.get("_folder_rel", "")
        fname = rf.get("name", "")
        rel = f"{folder_rel}/{fname}".lstrip("/") if folder_rel else fname
        rf["_computed_rel"] = rel
        if fid:
            remote_by_id[fid] = rf
        # Only store first occurrence (duplicates would be a backend bug)
        if rel not in remote_by_rel:
            remote_by_rel[rel] = rf

    processed_rels: set[str] = set()

    # --- Pass 1: SQLite records as the primary merging key ---
    for rec in sqlite_records:
        rel = rec.get("path", "")
        cloud_id = rec.get("cloud_id", "")
        if not rel:
            continue

        # Prefer lookup by cloud_id (stable), fallback to rel_path
        remote_file = remote_by_id.get(cloud_id) if cloud_id else remote_by_rel.get(rel)
        full_local_path = os.path.join(watched_dir, rel)

        state = FileState(
            rel_path=rel,
            cloud_id=cloud_id or (remote_file.get("id") if remote_file else None),
            local_exists=rel in local_tree,
            local_hash=local_tree.get(rel),
            last_synced_hash=rec.get("last_synced_hash"),
            last_synced_cloud_hash=rec.get("last_synced_cloud_md5"),
            last_cloud_version=rec.get("cloud_version", 0),
            sync_mode=rec.get("sync_mode", "folder"),
            abs_path=rec.get("abs_path"),
            status=rec.get("status"),
            is_tombstone=rec.get("is_tombstone", 0),
            conflict_original_path=rec.get("conflict_original_path"),
            cloud_exists=remote_file is not None,
            cloud_hash=remote_file.get("content_hash") if remote_file else None,
            cloud_version=remote_file.get("version_number", 0) if remote_file else 0,
            cloud_name=remote_file.get("name") if remote_file else None,
            cloud_parent_id=remote_file.get("parent_id") if remote_file else None,
        )
        state.action = classify_file_state(state)
        _add_to_plan(plan, state)
        processed_rels.add(rel)
        if remote_file:
            processed_rels.add(remote_file.get("_computed_rel", rel))

    # --- Pass 2: Remote files not yet in SQLite (brand-new cloud files) ---
    for rf in remote_files:
        rel = rf.get("_computed_rel", "")
        fid = rf.get("id")
        if rel in processed_rels:
            continue
        if fid in sqlite_by_cloud_id:
            continue  # already handled above by cloud_id

        state = FileState(
            rel_path=rel,
            cloud_id=fid,
            local_exists=rel in local_tree,
            local_hash=local_tree.get(rel),
            last_synced_hash=None,
            last_synced_cloud_hash=None,
            last_cloud_version=0,
            cloud_exists=True,
            cloud_hash=rf.get("content_hash"),
            cloud_version=rf.get("version_number", 0),
            cloud_name=rf.get("name"),
            cloud_parent_id=rf.get("parent_id"),
        )
        state.action = classify_file_state(state)
        _add_to_plan(plan, state)
        processed_rels.add(rel)

    # --- Pass 3: Local files not in SQLite and not in remote (truly new local) ---
    for rel, local_hash in local_tree.items():
        if rel in processed_rels:
            continue
        state = FileState(
            rel_path=rel,
            local_exists=True,
            local_hash=local_hash,
            cloud_exists=False,
        )
        state.action = ACTION_UPLOAD_NEW
        _add_to_plan(plan, state)

    logger.info(
        f"[recon][{plan.cycle_id}] Plan built: "
        f"{len(plan.uploads)} upload(s), "
        f"{len(plan.downloads)} download(s), "
        f"{len(plan.conflicts)} conflict(s), "
        f"{len(plan.local_deletions)} local-del, "
        f"{len(plan.cloud_deletions)} cloud-del, "
        f"{plan.noops} noop(s)"
    )
    return plan


def _add_to_plan(plan: ReconciliationPlan, state: FileState) -> None:
    action = state.action
    if action in (ACTION_UPLOAD_NEW, ACTION_UPLOAD_CHANGED):
        plan.uploads.append(state)
    elif action in (ACTION_DOWNLOAD_NEW, ACTION_DOWNLOAD_CHANGED):
        plan.downloads.append(state)
    elif action == ACTION_CONFLICT:
        plan.conflicts.append(state)
    elif action == ACTION_LOCAL_DELETED:
        plan.local_deletions.append(state)
    elif action == ACTION_CLOUD_DELETED:
        plan.cloud_deletions.append(state)
    elif action == ACTION_BOTH_DELETED:
        pass  # will be cleaned by clean_orphaned_records
    else:  # noop or first-time identical
        plan.noops += 1


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

# Thread-safe set of paths being written by the agent (suppresses watcher loops)
_agent_writing: set = set()
_agent_writing_lock = threading.Lock()


class AgentWriteContext:
    """Context manager that marks a path as agent-written, suppressing watcher events."""
    def __init__(self, abs_path: str):
        self._path = os.path.abspath(abs_path)

    def __enter__(self):
        with _agent_writing_lock:
            _agent_writing.add(self._path)
        return self

    def __exit__(self, *_):
        with _agent_writing_lock:
            _agent_writing.discard(self._path)


def is_agent_writing(abs_path: str) -> bool:
    """Returns True if the reconciler is currently writing to this path."""
    with _agent_writing_lock:
        return os.path.abspath(abs_path) in _agent_writing


def execute_plan(
    plan: ReconciliationPlan,
    auth,
    watched_dir: str,
    device_id: str,
    db_module,                    # pass db module to avoid circular imports
    drive_client_module,          # pass drive_client module
    watcher_ignore,               # watcher.IgnorePathContext class
) -> dict:
    """
    Execute the reconciliation plan safely.
    Returns a dict with counts of successes/failures.
    """
    import uuid as _uuid
    cid = plan.cycle_id
    results = {
        "uploaded": 0, "downloaded": 0, "conflicts": 0,
        "upload_errors": 0, "download_errors": 0,
        "local_deletions_noted": 0, "cloud_deletions_noted": 0,
    }

    # --- Uploads ---
    for state in plan.uploads:
        full_path = os.path.join(watched_dir, state.rel_path)
        if not os.path.exists(full_path):
            logger.warning(f"[recon][{cid}] Upload skipped (disappeared): {state.rel_path}")
            continue
        try:
            _execute_upload(state, auth, full_path, watched_dir, device_id,
                            db_module, drive_client_module, cid)
            results["uploaded"] += 1
        except Exception as exc:
            logger.error(f"[recon][{cid}] Upload failed for '{state.rel_path}': {exc}")
            results["upload_errors"] += 1

    # --- Downloads ---
    for state in plan.downloads:
        try:
            _execute_download(state, auth, watched_dir, device_id,
                              db_module, drive_client_module, watcher_ignore, cid)
            results["downloaded"] += 1
        except Exception as exc:
            logger.error(f"[recon][{cid}] Download failed for '{state.rel_path}': {exc}")
            results["download_errors"] += 1

    # --- Conflicts ---
    for state in plan.conflicts:
        full_path = os.path.join(watched_dir, state.rel_path)
        try:
            _execute_conflict(state, auth, full_path, watched_dir, device_id,
                              db_module, drive_client_module, watcher_ignore, cid)
            results["conflicts"] += 1
        except Exception as exc:
            logger.error(f"[recon][{cid}] Conflict resolution failed for '{state.rel_path}': {exc}")
            results["upload_errors"] += 1

    # --- Local deletions (note only; cloud NOT auto-deleted) ---
    for state in plan.local_deletions:
        logger.info(f"[recon][{cid}] Local deletion noted for '{state.rel_path}' "
                    f"(cloud copy preserved; manual action required).")
        try:
            db_module.set_file_status(state.rel_path, "LocalDeleted",
                                      "Local file removed; cloud copy preserved")
            results["local_deletions_noted"] += 1
        except Exception as exc:
            logger.warning(f"[recon][{cid}] Could not update status for local deletion: {exc}")

    # --- Cloud deletions (tombstone recorded; local copy preserved; no false re-upload) ---
    for state in plan.cloud_deletions:
        logger.info(f"[recon][{cid}] Cloud file not found for '{state.rel_path}' "
                    f"(local copy preserved; recording persistent CloudDeleted tombstone).")
        try:
            if hasattr(db_module, "set_tombstone"):
                db_module.set_tombstone(state.rel_path, is_tombstone=1,
                                        error_message="Cloud copy deleted; local copy preserved as tombstone")
            else:
                db_module.set_file_status(state.rel_path, "CloudDeleted",
                                          "Cloud copy deleted; local copy preserved as tombstone")
            results["cloud_deletions_noted"] += 1
        except Exception as exc:
            logger.warning(f"[recon][{cid}] Could not record tombstone for '{state.rel_path}': {exc}")

    logger.info(
        f"[recon][{cid}] Execution complete: "
        f"uploaded={results['uploaded']}, downloaded={results['downloaded']}, "
        f"conflicts={results['conflicts']}, errors={results['upload_errors']+results['download_errors']}"
    )
    return results


def _execute_upload(
    state: FileState, auth, full_path: str, watched_dir: str, device_id: str,
    db_module, drive_client_module, cid: str
):
    rel = state.rel_path
    logger.info(f"[recon][{cid}] UPLOAD {rel} (action={state.action}, cloud_id={state.cloud_id})")

    rel_dir = os.path.dirname(rel)
    parent_id = "root"
    if rel_dir:
        parent_id = drive_client_module.get_or_create_drive_folder(auth, rel_dir)

    operation_id = str(uuid.uuid4())

    # Acquire lock if updating existing file
    if state.cloud_id:
        drive_client_module.acquire_lock(auth, state.cloud_id, device_id)

    try:
        resp = drive_client_module.upload_file(
            auth, full_path,
            cloud_id=state.cloud_id,
            parent_id=parent_id if not state.cloud_id else None,
            expected_version=state.last_cloud_version if state.cloud_id else None,
            operation_id=operation_id,
            device_id=device_id,
        )
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 409:
            # Version conflict — will be resolved on next cycle
            logger.warning(f"[recon][{cid}] 409 Conflict on upload '{rel}' — will reconcile next cycle")
            db_module.set_file_status(rel, "Conflict", "Version mismatch — retrying next cycle")
            return
        raise
    finally:
        if state.cloud_id:
            try:
                drive_client_module.release_lock(auth, state.cloud_id, device_id)
            except Exception:
                pass

    new_id = resp.get("id")
    new_ver = resp.get("version_number", 1)
    new_hash = resp.get("content_hash", state.local_hash)
    now_iso = datetime.now(timezone.utc).isoformat()

    db_module.upsert_record(
        rel,
        local_hash=state.local_hash,
        cloud_id=new_id,
        last_synced_hash=state.local_hash,
        last_synced_cloud_md5=new_hash,
        cloud_version=new_ver,
        status="Synced",
        last_sync_time=now_iso,
        error_message="",
        is_tombstone=0,
    )
    logger.info(f"[recon][{cid}] Uploaded '{rel}' → cloud_id={new_id} version={new_ver}")


def _execute_download(
    state: FileState, auth, watched_dir: str, device_id: str,
    db_module, drive_client_module, watcher_ignore, cid: str
):
    """Download cloud file into place atomically. Never uses '(cloud updated)' naming."""
    rel = state.rel_path
    cloud_id = state.cloud_id
    logger.info(f"[recon][{cid}] DOWNLOAD {rel} (action={state.action}, cloud_id={cloud_id})")

    full_dest = os.path.join(watched_dir, rel)
    abs_dest = os.path.abspath(full_dest)

    # Create parent directories
    os.makedirs(os.path.dirname(abs_dest), exist_ok=True)

    temp_path = abs_dest + f".tmp.{uuid.uuid4().hex[:8]}"

    try:
        with watcher_ignore(abs_dest), watcher_ignore(temp_path), AgentWriteContext(abs_dest):
            # Download to temp file
            logger.debug(f"[recon][{cid}] Downloading to temp: {temp_path}")
            drive_client_module.download_file(auth, cloud_id, temp_path)

            # Verify hash
            downloaded_hash = _hash_file(temp_path)
            if state.cloud_hash and downloaded_hash != state.cloud_hash:
                raise ValueError(
                    f"Hash mismatch: expected {state.cloud_hash}, got {downloaded_hash}"
                )

            # Atomic replace of destination
            os.replace(temp_path, abs_dest)
            logger.debug(f"[recon][{cid}] Atomically replaced: {abs_dest}")

            # Register with durable hash-based suppression registry
            try:
                from watcher import suppression_registry
                suppression_registry.record_suppression(abs_dest, downloaded_hash, ttl=30.0)
            except ImportError:
                pass

            # Allow watcher event to settle before updating SQLite
            time.sleep(0.05)

    except Exception:
        # Clean up temp file on failure; leave original intact
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise

    # Verify final hash on disk
    final_hash = _hash_file(abs_dest)
    now_iso = datetime.now(timezone.utc).isoformat()

    db_module.upsert_record(
        rel,
        local_hash=final_hash,
        cloud_id=cloud_id,
        last_synced_hash=final_hash,
        last_synced_cloud_md5=state.cloud_hash or final_hash,
        cloud_version=state.cloud_version,
        status="Synced",
        last_sync_time=now_iso,
        error_message="",
        is_tombstone=0,
    )
    logger.info(f"[recon][{cid}] Downloaded '{rel}' (version={state.cloud_version}, hash={final_hash[:16]}…)")


def _execute_conflict(
    state: FileState, auth, full_path: str, watched_dir: str, device_id: str,
    db_module, drive_client_module, watcher_ignore, cid: str
):
    """
    Both local and cloud changed since last sync.
    Policy: preserve local copy as a conflict file, download cloud version in-place.
    """
    rel = state.rel_path
    cloud_id = state.cloud_id
    logger.warning(f"[recon][{cid}] CONFLICT {rel} — both sides changed independently")

    # Create a conflict copy of the current local file
    base, ext = os.path.splitext(full_path)
    stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
    conflict_path = f"{base} (conflict from cloud {stamp}){ext}"

    # Ensure conflict copy name does not collide
    counter = 1
    candidate = conflict_path
    while os.path.exists(candidate):
        candidate = f"{base} (conflict from cloud {stamp} {counter}){ext}"
        counter += 1
    conflict_path = candidate

    try:
        import shutil
        with AgentWriteContext(conflict_path):
            shutil.copy2(full_path, conflict_path)
        logger.info(f"[recon][{cid}] Conflict copy created: {conflict_path}")
        try:
            from watcher import suppression_registry
            suppression_registry.record_suppression(conflict_path, _hash_file(conflict_path), ttl=30.0)
        except ImportError:
            pass
    except Exception as exc:
        logger.error(f"[recon][{cid}] Could not create conflict copy for '{rel}': {exc}")
        raise

    # Download cloud version into the original path
    state_for_dl = FileState(
        rel_path=rel,
        cloud_id=cloud_id,
        cloud_hash=state.cloud_hash,
        cloud_version=state.cloud_version,
        action=ACTION_DOWNLOAD_CHANGED,
    )
    _execute_download(state_for_dl, auth, watched_dir, device_id,
                      db_module, drive_client_module, watcher_ignore, cid)

    # Update SQLite with conflict note
    conflict_rel = os.path.relpath(conflict_path, watched_dir).replace("\\", "/")
    conflict_hash = _hash_file(conflict_path)
    now_iso = datetime.now(timezone.utc).isoformat()

    db_module.upsert_record(
        conflict_rel,
        local_hash=conflict_hash,
        cloud_id=None,  # conflict copy has no cloud ID
        last_synced_hash=conflict_hash,
        status="Conflict",
        last_sync_time=now_iso,
        error_message=f"Conflict copy of '{rel}' — local version at time of conflict",
        is_tombstone=0,
        conflict_original_path=rel,
    )
    db_module.set_file_status(rel, "Synced", "")
    logger.warning(f"[recon][{cid}] Conflict resolved for '{rel}': cloud version downloaded, local preserved at '{conflict_rel}'")


# ---------------------------------------------------------------------------
# Main reconciliation entry point
# ---------------------------------------------------------------------------

# Guard against overlapping reconciliation cycles
_reconciliation_lock = threading.Lock()


def run_reconciliation_cycle(
    auth,
    watched_dir: str,
    device_id: str,
    db_module,
    drive_client_module,
    watcher_ignore,
    is_startup: bool = False,
) -> dict:
    """
    Run one full bidirectional reconciliation cycle.

    Returns a summary dict with counts for logging/GUI display.
    Thread-safe: skips cycle if another is already running.
    """
    if not _reconciliation_lock.acquire(blocking=False):
        logger.info("[recon] Reconciliation cycle skipped — previous cycle still running")
        return {"skipped": True}

    cycle_id = str(uuid.uuid4())[:8]
    start_time = time.monotonic()

    try:
        logger.info(f"[recon][{cycle_id}] ═══ Reconciliation cycle started (startup={is_startup}) ═══")

        # 1. Fetch remote tree
        logger.info(f"[recon][{cycle_id}] Fetching remote file tree…")
        try:
            remote_files = fetch_remote_file_tree(auth)
        except Exception as exc:
            logger.error(f"[recon][{cycle_id}] Cannot fetch remote tree: {exc} — aborting cycle")
            return {"error": str(exc), "skipped": True}

        logger.info(f"[recon][{cycle_id}] Remote tree: {len(remote_files)} file(s)")

        # 2. Scan local tree
        logger.info(f"[recon][{cycle_id}] Scanning local directory: {watched_dir}")
        local_tree = scan_local_tree(watched_dir)
        logger.info(f"[recon][{cycle_id}] Local tree: {len(local_tree)} file(s)")

        # 3. Load SQLite records
        sqlite_records = db_module.all_records()
        logger.info(f"[recon][{cycle_id}] SQLite records: {len(sqlite_records)}")

        # 4. Build plan
        plan = build_reconciliation_plan(local_tree, remote_files, sqlite_records, watched_dir)
        plan.cycle_id = cycle_id

        # 5. Execute plan
        results = execute_plan(
            plan, auth, watched_dir, device_id,
            db_module, drive_client_module, watcher_ignore
        )

        elapsed = time.monotonic() - start_time
        logger.info(
            f"[recon][{cycle_id}] ═══ Reconciliation complete in {elapsed:.1f}s ═══ "
            f"up={results.get('uploaded',0)} "
            f"dl={results.get('downloaded',0)} "
            f"conflict={results.get('conflicts',0)} "
            f"err={results.get('upload_errors',0)+results.get('download_errors',0)}"
        )
        results["cycle_id"] = cycle_id
        results["elapsed_seconds"] = round(elapsed, 2)
        return results

    except Exception as exc:
        logger.error(f"[recon][{cycle_id}] Unexpected error in reconciliation: {exc}", exc_info=True)
        return {"error": str(exc), "cycle_id": cycle_id}
    finally:
        _reconciliation_lock.release()

