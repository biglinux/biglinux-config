"""Reset application configuration to program- or BigLinux-defaults.

Safety model (see docs/04):

* Every path is validated through :mod:`backend.paths`; nothing outside ``$HOME``
  is ever touched and *structural* directories (``~``, ``~/.config`` …) can never
  be removed or replaced wholesale.
* A reset is **transactional**: the current configuration is moved aside (atomic
  rename) rather than deleted outright, the new state is applied, and any failure
  rolls everything back.  The aside copy is only discarded on success.
* An optional safety backup can be produced *before* the destructive step.
* Running processes are matched precisely (via ``/proc/<pid>/exe``) so unrelated
  programs are never killed.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import signal
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from logging.handlers import RotatingFileHandler

from backend import dconf_manager, paths
from data.app_registry import AppEntry

logger = logging.getLogger("biglinux-config")

STATE_DIR = os.path.expanduser("~/.local/state/biglinux-config")
LOG_FILE = os.path.join(STATE_DIR, "operations.log")
PRE_RESET_DIR = os.path.join(STATE_DIR, "pre-reset-backups")
SKEL_ROOT = "/etc/skel"


class ResetMode(Enum):
    PROGRAM_DEFAULT = auto()   # remove dotfiles (app recreates its own defaults)
    BIGLINUX_DEFAULT = auto()  # remove + copy from /etc/skel/


class ResetStatus(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


@dataclass
class ResetResult:
    success: bool
    message: str
    app_id: str
    mode: ResetMode
    removed_paths: list[str] = field(default_factory=list)
    restored_paths: list[str] = field(default_factory=list)
    status: ResetStatus = ResetStatus.FAILED
    backup_path: str = ""


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def _setup_logger() -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
            handler = RotatingFileHandler(
                LOG_FILE, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    except OSError:
        # Never let logging setup break the app.
        logging.basicConfig(level=logging.INFO)


_setup_logger()


# --------------------------------------------------------------------------- #
# Process detection / termination (precise)
# --------------------------------------------------------------------------- #
def get_running_pids(entry: AppEntry) -> list[int]:
    """Return PIDs of the current user's processes that *are* this app.

    Matches ``/proc/<pid>/exe`` against the registered binary (most precise) and
    falls back to an exact ``comm`` match against ``process_name``.  Never uses a
    loose command-line substring match, so unrelated processes are never hit.
    """
    my_uid = os.getuid()
    binary_real = os.path.realpath(entry.binary) if entry.binary else ""
    comm_target = entry.process_name or os.path.basename(entry.binary or "")
    pids: list[int] = []

    try:
        entries = os.listdir("/proc")
    except OSError:
        return []

    for name in entries:
        if not name.isdigit():
            continue
        pid = int(name)
        base = f"/proc/{name}"
        try:
            if os.stat(base).st_uid != my_uid:
                continue
        except OSError:
            continue
        # Skip zombie / dead processes — they are not "running".
        try:
            with open(f"{base}/stat", encoding="utf-8") as fh:
                state = fh.read().rsplit(")", 1)[1].split()[0]
            if state in ("Z", "X", "x"):
                continue
        except (OSError, IndexError):
            continue
        matched = False
        try:
            exe = os.readlink(f"{base}/exe")
            if binary_real and os.path.realpath(exe) == binary_real:
                matched = True
        except OSError:
            pass
        if not matched and comm_target:
            try:
                with open(f"{base}/comm", encoding="utf-8") as fh:
                    if fh.read().strip() == comm_target:
                        matched = True
            except OSError:
                pass
        if matched:
            pids.append(pid)
    return pids


def kill_app(entry: AppEntry, timeout: float = 5.0) -> bool:
    """Terminate the app gracefully (SIGTERM), then SIGKILL survivors.

    Returns True if no instance remains afterwards.
    """
    pids = get_running_pids(entry)
    if not pids:
        return True
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not get_running_pids(entry):
            return True
        time.sleep(0.2)

    for pid in get_running_pids(entry):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(0.2)
    return not get_running_pids(entry)


# --------------------------------------------------------------------------- #
# Target expansion
# --------------------------------------------------------------------------- #
def _expand_targets(config_paths: list[str]) -> list[str]:
    """Resolve config paths (with glob support) to concrete, existing targets."""
    targets: list[str] = []
    for raw_path in config_paths:
        expanded = os.path.expanduser(raw_path)
        if "*" in expanded or "?" in expanded or "[" in expanded:
            matches = glob.glob(expanded)
        else:
            matches = [expanded]
        for m in matches:
            if os.path.lexists(m):
                targets.append(m)
    return targets


# --------------------------------------------------------------------------- #
# Reset (transactional)
# --------------------------------------------------------------------------- #
def reset_app(
    entry: AppEntry,
    mode: ResetMode,
    backup_first: bool = False,
    cancel_event=None,
) -> ResetResult:
    """Execute a configuration reset for *entry*.

    Must be called from a worker thread (never the UI thread).

    Args:
        entry: the application to reset.
        mode: PROGRAM_DEFAULT or BIGLINUX_DEFAULT.
        backup_first: create a safety ``.tar.gz`` of the current config first.
        cancel_event: optional ``threading.Event`` to abort before applying.
    """
    removed: list[str] = []
    restored: list[str] = []
    backup_path = ""

    def cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    # 0) optional safety backup ------------------------------------------------
    if backup_first and (entry.config_paths or entry.dconf_paths):
        backup_path = _safety_backup(entry)
        if backup_path == "":
            return ResetResult(
                False, "Could not create a safety backup before resetting.",
                entry.app_id, mode, status=ResetStatus.FAILED)

    if cancelled():
        return ResetResult(False, "cancelled", entry.app_id, mode,
                           status=ResetStatus.CANCELLED, backup_path=backup_path)

    # 1) plan skel restore (validate destinations up-front) --------------------
    skel_plan: list[tuple[str, str]] = []  # (skel_source, live_dest)
    if mode == ResetMode.BIGLINUX_DEFAULT:
        for skel_path in entry.skel_paths:
            if not paths.is_within(SKEL_ROOT, skel_path):
                logger.warning("Skel path outside %s ignored: %s", SKEL_ROOT, skel_path)
                continue
            if not os.path.exists(skel_path):
                continue
            rel = os.path.relpath(skel_path, SKEL_ROOT)
            dest = os.path.join(paths.home(), rel)
            safe = paths.safe_destination(dest)
            if safe is None:
                logger.warning("Refusing unsafe/structural skel dest: %s", dest)
                continue
            skel_plan.append((skel_path, safe))

    # 2) collect removable targets --------------------------------------------
    aside_root = os.path.join(paths.home(),
                              f".biglinux-config-reset-{os.getpid()}-{int(time.time())}")
    moved: list[tuple[str, str]] = []   # (original, aside)
    created: list[str] = []             # dests written from skel
    dconf_pre: dict[str, str] = {}      # namespace -> dump captured before reset

    try:
        os.makedirs(aside_root, exist_ok=True)

        for target in _expand_targets(entry.config_paths):
            if cancelled():
                raise _CancelReset()
            real = paths.safe_removable(target)
            if real is None:
                logger.warning("Refusing to remove unsafe/structural path: %s", target)
                continue
            aside = os.path.join(aside_root, os.path.relpath(real, paths.home()))
            os.makedirs(os.path.dirname(aside), exist_ok=True)
            os.rename(real, aside)
            moved.append((real, aside))
            removed.append(real)

        # 3) apply skel copies -------------------------------------------------
        for skel_src, dest in skel_plan:
            if cancelled():
                raise _CancelReset()
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.isdir(skel_src) and not os.path.islink(skel_src):
                shutil.copytree(skel_src, dest, symlinks=True)
            else:
                shutil.copy2(skel_src, dest)
            created.append(dest)
            restored.append(dest)

        # 4) reset dconf namespaces (scoped) -----------------------------------
        if entry.dconf_paths and dconf_manager.is_available():
            for ns in entry.dconf_paths:
                if not dconf_manager.is_valid_namespace(ns):
                    logger.warning("Skipping unsafe dconf namespace: %s", ns)
                    continue
                if cancelled():
                    raise _CancelReset()
                dconf_pre[ns] = dconf_manager.dump(ns)  # for rollback
                if dconf_manager.reset(ns):
                    removed.append(f"dconf:{ns}")

        # success: discard the aside copies
        shutil.rmtree(aside_root, ignore_errors=True)

        status = ResetStatus.SUCCESS
        if mode == ResetMode.BIGLINUX_DEFAULT and not skel_plan:
            # Nothing valid to restore — behaved as program-default.
            logger.info("Reset %s: no valid skel; behaved as program default",
                        entry.app_id)
        logger.info("Reset %s (%s): removed=%d restored=%d backup=%s",
                    entry.app_id, mode.name, len(removed), len(restored),
                    backup_path or "-")
        return ResetResult(True, "", entry.app_id, mode, removed, restored,
                           status, backup_path)

    except _CancelReset:
        _reset_rollback(moved, created)
        _dconf_rollback(dconf_pre)
        shutil.rmtree(aside_root, ignore_errors=True)
        logger.info("Reset %s cancelled and rolled back", entry.app_id)
        return ResetResult(False, "cancelled", entry.app_id, mode, [], [],
                           ResetStatus.CANCELLED, backup_path)
    except Exception as exc:  # noqa: BLE001
        _reset_rollback(moved, created)
        _dconf_rollback(dconf_pre)
        shutil.rmtree(aside_root, ignore_errors=True)
        logger.error("Reset failed for %s: %s (rolled back)", entry.app_id, exc,
                     exc_info=True)
        return ResetResult(False, str(exc), entry.app_id, mode, [], [],
                           ResetStatus.ROLLED_BACK, backup_path)


class _CancelReset(Exception):
    pass


def _dconf_rollback(dconf_pre: dict[str, str]) -> None:
    """Restore dconf namespaces captured before a reset."""
    for ns, text in dconf_pre.items():
        try:
            if text.strip():
                dconf_manager.load(ns, text)
            else:
                dconf_manager.reset(ns)
        except Exception as exc:  # noqa: BLE001
            logger.error("dconf rollback error for %s: %s", ns, exc)


def _reset_rollback(moved: list[tuple[str, str]], created: list[str]) -> None:
    """Undo a partial reset: remove skel copies, move originals back."""
    for dest in reversed(created):
        try:
            if os.path.islink(dest) or os.path.isfile(dest):
                os.unlink(dest)
            elif os.path.isdir(dest):
                shutil.rmtree(dest, ignore_errors=True)
        except OSError as exc:
            logger.error("Rollback (remove skel) error for %s: %s", dest, exc)
    for original, aside in reversed(moved):
        try:
            if os.path.lexists(original):
                continue
            os.makedirs(os.path.dirname(original), exist_ok=True)
            os.rename(aside, original)
        except OSError as exc:
            logger.error("Rollback (restore) error for %s: %s", original, exc)


def _safety_backup(entry: AppEntry) -> str:
    """Create a pre-reset safety backup; return its path or '' on failure."""
    from backend import backup_manager as bm
    try:
        os.makedirs(PRE_RESET_DIR, exist_ok=True)
        name = bm.get_app_backup_name(entry.app_id)
        dest = os.path.join(PRE_RESET_DIR, name)
        result = bm.export_backup([entry], dest)
        if result.success:
            logger.info("Pre-reset backup for %s at %s", entry.app_id, dest)
            return dest
        logger.error("Pre-reset backup failed: %s", result.message)
    except Exception as exc:  # noqa: BLE001
        logger.error("Pre-reset backup crashed: %s", exc, exc_info=True)
    return ""


# --------------------------------------------------------------------------- #
# Queries used by the UI
# --------------------------------------------------------------------------- #
def get_config_size(entry: AppEntry) -> int:
    """Total size in bytes of the existing config paths."""
    total = 0
    for target in _expand_targets(entry.config_paths):
        if os.path.islink(target):
            continue
        if os.path.isdir(target):
            for dirpath, _dirs, files in os.walk(target):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(dirpath, f))
                    except OSError:
                        pass
        elif os.path.isfile(target):
            try:
                total += os.path.getsize(target)
            except OSError:
                pass
    return total


def has_skel(entry: AppEntry) -> bool:
    """True if at least one skel path exists *and* maps to a safe destination.

    This is what gates the "Restore BigLinux default" option in the UI, so it
    must never report True for a skel that we would refuse to apply.
    """
    home = paths.home()
    for p in entry.skel_paths:
        if not paths.is_within(SKEL_ROOT, p) or not os.path.exists(p):
            continue
        rel = os.path.relpath(p, SKEL_ROOT)
        dest = os.path.join(home, rel)
        if paths.safe_destination(dest) is not None:
            return True
    return False


def has_config(entry: AppEntry) -> bool:
    """True if any config path exists on disk, or dconf holds user values."""
    if _expand_targets(entry.config_paths):
        return True
    if entry.dconf_paths and dconf_manager.is_available():
        return dconf_manager.has_content(entry.dconf_paths)
    return False


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
