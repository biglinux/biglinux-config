"""Scoped resets with private staging and explicit recovery after failures.

Filesystem renames are individually atomic; the combined operation with dconf
is NOT crash-atomic. Failed rollback preserves originals and a recovery journal.
All mutating functions must run outside the GTK main thread.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from logging.handlers import RotatingFileHandler

from backend import dconf_manager, paths
from backend.transactions import FileTransaction, operation_lock
from data.app_registry import AppEntry, get_reset_paths

logger = logging.getLogger("biglinux-config")
STATE_DIR = os.path.join(paths.xdg_home("XDG_STATE_HOME", ".local/state"), "biglinux-config")
LOG_FILE = os.path.join(STATE_DIR, "operations.log")
PRE_RESET_DIR = os.path.join(STATE_DIR, "pre-reset-backups")
SKEL_ROOT = "/etc/skel"


class _PrivateRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        return os.fdopen(fd, self.mode, encoding=self.encoding, errors=self.errors)


class ResetMode(Enum):
    PROGRAM_DEFAULT = auto()
    BIGLINUX_DEFAULT = auto()


class ResetStatus(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"  # Kept for API compatibility; new operations fail closed.
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"
    RECOVERY_REQUIRED = "recovery_required"


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
    recovery_path: str = ""


def setup_logger() -> None:
    """Initialize explicitly at application startup, never during import."""
    try:
        state = os.path.join(paths.xdg_home("XDG_STATE_HOME", ".local/state"), "biglinux-config")
        os.makedirs(state, mode=0o700, exist_ok=True)
        if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
            filename = os.path.join(state, "operations.log")
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            handler = _PrivateRotatingFileHandler(filename, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    except OSError:
        logging.basicConfig(level=logging.INFO)


def _native_match(pid: int, executable: str) -> bool:
    """No comm/basename fallback: unrelated programs may share those names."""
    if pid == os.getpid():
        return False
    try:
        base = f"/proc/{pid}"
        if os.stat(base).st_uid != os.getuid():
            return False
        with open(f"{base}/stat", encoding="utf-8") as source:
            state = source.read().rsplit(")", 1)[1].split()[0]
        return state not in ("Z", "X", "x") and os.path.realpath(f"{base}/exe") == executable
    except (OSError, IndexError):
        return False


def get_running_pids(entry: AppEntry) -> list[int]:
    """Identify a native executable exactly, or use Flatpak's application IDs.

    Script wrappers/launchers may have a different final executable: absence of
    a match is not proof that the app is stopped. The confirmation explains this.
    """
    if entry.app_id.startswith("flatpak-"):
        app_id = entry.app_id.removeprefix("flatpak-")
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]+", app_id):
            raise RuntimeError("Invalid Flatpak application ID.")
        result = subprocess.run(["flatpak", "ps", "--columns=application,pid"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError("Could not check running Flatpak applications.")
        pids = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] == app_id and fields[1].isdigit():
                pid = int(fields[1])
                try:
                    if pid != os.getpid() and os.stat(f"/proc/{pid}").st_uid == os.getuid():
                        pids.append(pid)
                except FileNotFoundError:
                    pass
        return pids
    binary = entry.binary
    if not binary:
        return []
    resolved = binary if os.path.isabs(binary) else shutil.which(binary)
    if not resolved:
        return []
    executable = os.path.realpath(resolved)
    return [int(name) for name in os.listdir("/proc")
            if name.isdigit() and _native_match(int(name), executable)]


def kill_app(entry: AppEntry, timeout: float = 5.0) -> bool:
    """Request graceful exit; never escalate to SIGKILL or kill a desktop session.

    A pidfd pins process identity. Revalidate after opening it, then signal that
    identity, not a possibly reused integer PID. Without pidfd, ask the user to
    close the app manually instead of weakening the guarantee.
    """
    if entry.is_de:
        return False
    try:
        pids = get_running_pids(entry)
        if not pids:
            return True
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            return False
        for pid in pids:
            fd = None
            try:
                fd = os.pidfd_open(pid)
                if pid in get_running_pids(entry):
                    signal.pidfd_send_signal(fd, signal.SIGTERM)
            except ProcessLookupError:
                pass
            finally:
                if fd is not None:
                    os.close(fd)
        deadline = time.monotonic() + max(0, timeout)
        while time.monotonic() < deadline:
            if not get_running_pids(entry):
                return True
            time.sleep(0.1)
        return not get_running_pids(entry)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        logger.exception("Could not stop %s safely", entry.app_id)
        return False


_expand_targets = paths.expand_targets


class _CancelReset(Exception):
    pass


def _skel_plan(entry: AppEntry) -> list[tuple[str, str]]:
    plan = []
    for source in entry.skel_paths:
        if not paths.is_within(SKEL_ROOT, source) or not os.path.lexists(source):
            continue
        destination = paths.safe_destination(os.path.join(paths.home(), os.path.relpath(source, SKEL_ROOT)))
        if destination is not None:
            plan.append((source, destination))
    # A parent template already contains its children; never swap a subtree twice.
    result = []
    for source, destination in sorted(set(plan), key=lambda item: (len(item[1]), item[1])):
        if not any(destination == parent or destination.startswith(parent + os.sep) for _, parent in result):
            result.append((source, destination))
    return result


def _stage_template(source: str, staged: str, destination: str, check_cancel) -> None:
    """Copy only inside private staging; partial copies never touch live data."""
    def copy_file(src, dst):
        check_cancel()
        if not stat.S_ISREG(os.lstat(src).st_mode):
            raise RuntimeError(f"Unsupported template file: {src}")
        return shutil.copy2(src, dst, follow_symlinks=False)

    def check_links(directory, names):
        check_cancel()
        for name in names:
            candidate = os.path.join(directory, name)
            if os.path.islink(candidate):
                relative = os.path.relpath(candidate, source)
                member = os.path.relpath(os.path.join(destination, relative), paths.home())
                if not paths.safe_link(os.readlink(candidate), member):
                    raise RuntimeError(f"Unsafe template link: {candidate}")
        return []

    os.makedirs(os.path.dirname(staged), mode=0o700, exist_ok=True)
    if os.path.islink(source):
        link = os.readlink(source)
        if not paths.safe_link(link, os.path.relpath(destination, paths.home())):
            raise RuntimeError(f"Unsafe template link: {source}")
        os.symlink(link, staged)
    elif os.path.isdir(source):
        shutil.copytree(source, staged, symlinks=True, copy_function=copy_file, ignore=check_links)
    else:
        copy_file(source, staged)
    check_cancel()


def reset_app(entry: AppEntry, mode: ResetMode, backup_first: bool = False, cancel_event=None) -> ResetResult:
    try:
        with operation_lock():
            return _reset_app(entry, mode, backup_first, cancel_event)
    except Exception as exc:
        return ResetResult(False, str(exc), entry.app_id, mode, status=ResetStatus.FAILED)


def _reset_app(entry, mode, backup_first, cancel_event):
    from backend.backup_manager import _rollback_dconf

    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise _CancelReset("cancelled")

    transaction = None
    backup_path = ""
    removed, restored = [], []
    try:
        check_cancel()
        if mode not in (ResetMode.PROGRAM_DEFAULT, ResetMode.BIGLINUX_DEFAULT):
            raise ValueError("Unknown reset mode.")
        plan = _skel_plan(entry) if mode is ResetMode.BIGLINUX_DEFAULT else []
        if mode is ResetMode.BIGLINUX_DEFAULT and not plan:
            raise RuntimeError("No safe BigLinux template is available. Nothing was reset.")
        targets = paths.expand_targets(get_reset_paths(entry)) if mode is ResetMode.PROGRAM_DEFAULT else [dst for _, dst in plan]
        if any(paths.safe_removable(target) != target for target in targets):
            raise RuntimeError("An unsafe configuration path was refused. Nothing was reset.")
        namespaces = []
        for ns in sorted(set(entry.dconf_paths), key=len):
            if not dconf_manager.is_valid_namespace(ns):
                raise RuntimeError(f"Unsafe dconf namespace: {ns}")
            if not any(ns.startswith(parent) for parent in namespaces):
                namespaces.append(ns)
        # Snapshot BEFORE touching files; unavailable dconf is not an empty dump.
        previous = {ns: dconf_manager.dump_strict(ns) for ns in namespaces}
        check_cancel()
        if backup_first and (entry.config_paths or entry.dconf_paths):
            backup_path = _safety_backup(entry, cancel_event)
            check_cancel()
            if not backup_path:
                raise RuntimeError("Could not create a safety backup before resetting.")
        transaction = FileTransaction(".biglinux-config-reset-")
        for source, destination in plan:
            staged = os.path.join(transaction.staging, os.path.relpath(destination, paths.home()))
            _stage_template(source, staged, destination, check_cancel)
        for destination in targets:
            check_cancel()
            staged = (os.path.join(transaction.staging, os.path.relpath(destination, paths.home()))
                      if mode is ResetMode.BIGLINUX_DEFAULT else None)
            transaction.replace(destination, staged)
            removed.append(destination)
            if staged is not None:
                restored.append(destination)
        for ns in namespaces:
            check_cancel()
            transaction.dconf.append((ns, previous[ns]))
            transaction.write_journal()
            if not dconf_manager.reset(ns):
                raise RuntimeError(f"Could not reset dconf namespace {ns}")
            removed.append(f"dconf:{ns}")
        check_cancel()
        warning = ""
        try:
            transaction.cleanup()
        except OSError as exc:
            warning = f"Reset completed, but temporary files remain at {transaction.directory}: {exc}"
            logger.warning(warning)
        logger.info("Reset %s (%s): removed=%d restored=%d", entry.app_id, mode.name, len(removed), len(restored))
        return ResetResult(True, warning, entry.app_id, mode, removed, restored, ResetStatus.SUCCESS, backup_path)
    except Exception as exc:
        errors = []
        changed = transaction is not None and bool(transaction.records or transaction.dconf)
        if transaction is not None:
            errors.extend(_rollback_dconf(transaction.dconf))
            errors.extend(transaction.rollback_files())
            if not errors:
                try:
                    transaction.cleanup()
                except OSError as cleanup_error:
                    errors.append(str(cleanup_error))
        if errors:
            message = f"{exc}. Automatic recovery incomplete. Keep {transaction.directory}. " + "; ".join(errors)
            logger.error(message)
            return ResetResult(False, message, entry.app_id, mode, status=ResetStatus.RECOVERY_REQUIRED,
                               backup_path=backup_path, recovery_path=transaction.directory)
        status = (ResetStatus.CANCELLED if isinstance(exc, _CancelReset) else
                  ResetStatus.ROLLED_BACK if changed else ResetStatus.FAILED)
        logger.warning("Reset did not complete for %s: %s", entry.app_id, exc)
        return ResetResult(False, str(exc), entry.app_id, mode, status=status, backup_path=backup_path)


def _safety_backup(entry: AppEntry, cancel_event=None) -> str:
    from backend import backup_manager as bm
    try:
        os.makedirs(PRE_RESET_DIR, mode=0o700, exist_ok=True)
        dest = os.path.join(PRE_RESET_DIR, bm.get_app_backup_name(entry.app_id))
        result = bm.export_backup([entry], dest, cancel_event=cancel_event)
        if result.success:
            return dest
        logger.error("Pre-reset backup failed: %s", result.message)
    except Exception:
        logger.exception("Pre-reset backup failed")
    return ""


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


def has_config(entry: AppEntry, *, for_reset: bool = False) -> bool:
    """True if any config path exists on disk, or dconf holds user values."""
    if _expand_targets(get_reset_paths(entry) if for_reset else entry.config_paths):
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
