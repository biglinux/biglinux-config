"""Private staging, serialized operations and explicit recovery after failures.

Each rename is atomic, but a group of filesystem and dconf changes is not a
crash-atomic transaction. Recovery records are deliberately retained on failure.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import stat
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from backend import paths

_gate = threading.RLock()
_local = threading.local()


class OperationBusy(RuntimeError):
    pass


def fsync_directory(directory: str) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(destination: str | Path, data: dict) -> None:
    """Private temp file, fsync, atomic replacement, then directory fsync."""
    destination = os.fspath(destination)
    parent = os.path.dirname(destination) or "."
    os.makedirs(parent, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, destination)
        fsync_directory(parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


@contextmanager
def operation_lock():
    """Non-blocking process/thread lock; nested safety exports are reentrant."""
    if not _gate.acquire(blocking=False):
        raise OperationBusy("Another settings operation is already running.")
    fd = None
    try:
        depth = getattr(_local, "depth", 0)
        if not depth:
            state = os.path.join(paths.xdg_home("XDG_STATE_HOME", ".local/state"), "biglinux-config")
            os.makedirs(state, mode=0o700, exist_ok=True)
            fd = os.open(os.path.join(state, "operations.lock"),
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise OperationBusy("Unsafe operation lock file.")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise OperationBusy("Another settings operation is already running.") from exc
        _local.depth = depth + 1
        try:
            yield
        finally:
            _local.depth = depth
    finally:
        if fd is not None:
            os.close(fd)
        _gate.release()


def remove_entry(path: str) -> None:
    if os.path.islink(path) or not os.path.isdir(path):
        if os.path.lexists(path):
            os.unlink(path)
    else:
        shutil.rmtree(path)


class FileTransaction:
    """Rollback journal written BEFORE moving each original configuration."""

    def __init__(self, prefix: str):
        self.directory = tempfile.mkdtemp(prefix=prefix, dir=paths.home())
        self.aside = os.path.join(self.directory, "originals")
        self.staging = os.path.join(self.directory, "staging")
        os.mkdir(self.aside, 0o700)
        os.mkdir(self.staging, 0o700)
        self.records: list[dict] = []
        self.dconf: list[tuple[str, str]] = []
        self.write_journal()

    def write_journal(self) -> None:
        atomic_json(os.path.join(self.directory, "recovery.json"), {
            "version": 1, "home": paths.home(), "files": self.records, "dconf": self.dconf,
        })

    def replace(self, live: str, staged: str | None) -> None:
        if paths.safe_destination(live) != live:
            raise RuntimeError(f"Unsafe live destination: {live}")
        relative = os.path.relpath(live, paths.home())
        aside = os.path.join(self.aside, relative)
        had_live = os.path.lexists(live)
        record = {"live": live, "aside": aside, "had_live": had_live,
                  "moved": False, "installed": False}
        self.records.append(record)
        self.write_journal()
        os.makedirs(os.path.dirname(aside), mode=0o700, exist_ok=True)
        if had_live:
            os.rename(live, aside)
            record["moved"] = True
            fsync_directory(os.path.dirname(live))
            fsync_directory(os.path.dirname(aside))
            self.write_journal()
        if staged is not None:
            os.makedirs(os.path.dirname(live), mode=0o700, exist_ok=True)
            if paths.safe_destination(live) != live:
                raise RuntimeError(f"Live destination changed: {live}")
            os.rename(staged, live)
            record["installed"] = True
            fsync_directory(os.path.dirname(live))
            self.write_journal()

    def rollback_files(self) -> list[str]:
        errors = []
        for record in reversed(self.records):
            live, aside = record["live"], record["aside"]
            try:
                if paths.safe_destination(live) != live:
                    raise RuntimeError(f"Live destination changed: {live}")
                if record["installed"]:
                    remove_entry(live)
                if record["moved"]:
                    if os.path.lexists(live):
                        raise RuntimeError(f"Refusing to overwrite a recreated destination: {live}")
                    os.rename(aside, live)
                    fsync_directory(os.path.dirname(live))
            except (OSError, RuntimeError) as exc:
                errors.append(f"{live}: {exc}")
        return errors

    def cleanup(self) -> None:
        shutil.rmtree(self.directory)
        fsync_directory(paths.home())
