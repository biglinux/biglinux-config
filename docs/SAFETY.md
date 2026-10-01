# Safety, compatibility and release checks

Review date: 2026-10-01. This is a reviewed patch set, not a declaration that all
registered applications or native GTK combinations have been certified.

## Scope and trust

The app changes the current user's registered configuration paths. Run it as the
normal desktop user, never with sudo. Close target applications and save work
before export, reset or import. Exact executable/Flatpak checks cannot identify
every script, wrapper, launcher or detached subprocess, and cannot prevent a
program from restarting. There is no filesystem snapshot or live SQLite snapshot.

Import **only trusted backups**. Checksums detect content corruption; they do not
prove who created the archive, encrypt secrets or stop a malicious author from
choosing another allowed HOME destination in the manifest. An archive can contain
configuration that another application later interprets as code. The importer is
not a sandbox against an actively malicious process with the same UID. Keep
Python and the operating system's security updates installed.

Archive v2 requires complete checksums for regular-file and dconf payloads.
Legacy v1 is accepted with an explicit no-checksum warning. Paths, types, duplicate
members, JSON metadata, resource limits and gzip completion are checked before
live files are changed. Explicit tarfile.data_filter is one layer, not the entire
policy. Symlink metadata is not separately cryptographically hashed. Neither
format authenticates manifests, ownership or application identity.

Default limits: 100,000 members, 16 GiB total member payload, 4 GiB per file,
16 MiB metadata/header budget, 4 MiB per dconf dump, path depth 64. These limits
are deliberate rejection criteria, not truncation. Large VM/game backups can
exceed them; this is not a general-purpose full-home backup tool. Memory and
parsing are bounded by policy, but no universal CPU/RAM guarantee is claimed.

Only portable relative symlinks are exported/imported. Absolute links and live
paths with symlink parents are rejected, including otherwise legitimate setups.
A leaf symlink is moved/removed itself, not its target. Symlinked XDG trees and
some Steam installations therefore need manual handling. Filesystem mount
boundaries may cause EXDEV: the app aborts/rolls back rather than using unsafe
cross-device replacement. No ACL/xattr, sparse allocation, hardlink identity,
or application-version migration fidelity is promised. Hardlinked source contents
are saved as independent regular files. Restored permission bits are sanitized.

## Reset versus backup

`config_paths` describes the backup scope. `reset_paths=None` uses that same scope;
`reset_paths=[]` explicitly means no filesystem reset; an explicit list narrows
reset. New registry entries must choose this deliberately and test with real data.
The review narrows Steam reset to its configuration directory, preserves GNOME
Boxes VM data, leaves Bottles backup-only, and resets only Flatpak configuration
rather than all Flatpak data. This is not an exhaustive semantic certification of
all 136 static registrations or every app/version's data layout.

BigLinux defaults require an existing validated skeleton template; absence is
an error, not permission to silently fall back to deleting everything. Program
defaults remove registered reset paths and can still remove application history
or secrets stored there. Review the displayed paths and take a separate backup.
Only scoped dconf namespaces are manipulated; the raw dconf database is not
copied. Exact replacement uses namespace reset followed by load, with previous
contents captured for rollback. dconf is not schema-level GSettings validation.

## Transaction and manual recovery

New files are fully staged in private 0700 directories below HOME, originals are
moved aside, and a private recovery.json journal records the affected roots.
Each rename is atomic; a group of filesystem/dconf operations is **not** atomic
against power loss, SIGKILL, filesystem failure or another process's writes.
There is no automatic crash-recovery resolver in this patch set.

After `RECOVERY_REQUIRED`, do not delete the reported
`.biglinux-config-restore-*` / `.biglinux-config-reset-*` directory or pre-reset
archive. Stop writes to the affected applications. Copy the recovery directory
to private storage before attempting repairs; it can contain passwords and dconf
secrets. Inspect `recovery.json`, `originals/`, `staging/` and the actual live paths.
A journal flag can lag the real filesystem after a crash; do not treat it as the
sole source of truth. Preserve conflicting live files separately before manually
restoring each affected root. Do not run a blanket deletion/move loop against
HOME. dconf recovery must target only the recorded namespaces, never `/`.

Cancellation is cooperative: the dialog waits for staging/rollback to finish and
reports incomplete recovery even when cancel was requested. There is no SIGKILL
escalation when a target application refuses to close. Successful operations can
also report cleanup/durability warnings; do not discard those warnings.

## Runtime and packaging

API minimums: Python 3.12, GTK 4.12, libadwaita 1.6, PyGObject with Gtk/Adw
introspection. Python 3.13+ avoids TarInfo caching via stream=True; 3.12 retains
a count-bounded compatibility path. These minimums are not a recommendation to
hold outdated security releases. Use distribution-supported current packages.
libadwaita can require a newer GTK transitively than the app's own API floor.

The installed launcher uses `/usr/bin/python3 -I` and only inserts the installed
application tree, avoiding arbitrary PYTHONPATH/cwd/user-site imports. This still
trusts the installed application files. The original upstream URLs/authors are
retained; the repository URLs in metadata and PKGBUILD differ and require
maintainer confirmation before a release. No upstream release tag is invented.

The VCS PKGBUILD fetches its configured upstream. To package this **local patched
checkout**, run `python3 tools/prepare-local-package.py`, then `cd build/local-package`
and `makepkg` as a normal user. The generated recipe uses a deterministic local
source archive and an actual SHA-256 checksum; it does not refetch upstream.
Build compiles gettext catalogs, package excludes bytecode/caches, and check runs
the isolated unit suite. `gettext`, `python-pytest` and normal makepkg tools must
be installed separately. No package is automatically installed by these scripts.

The review updates 17 new safety/UI strings in pt_BR and rebuilds pt_BR/en
catalogs. Existing translations, plural rules and linguistic quality across all
other languages still need translator review. The canonical build uses GNU
msgfmt; local review also parsed/checked the 29 PO files with Babel and tested
the rebuilt MO files with Python's GNUTranslations loader.

## Repeatable checks and native release gate

From the checkout, run `bash tools/check.sh`. This isolates HOME/XDG, disables the
real dconf tests and compiles Python syntax. Run `bash tools/check-dconf.sh` for
real dconf/D-Bus integration: isolation must happen **before** the private session
bus starts, because an already running dconf service inherits its old environment.
Never opt into those tests inside your real desktop bus/profile.

Native GTK validation was not available in the review executor (no gi/GTK4/Adw
bindings). `tests/test_jobs.py` tests scheduling/lifetime with a fake GLib queue;
it is not a native widget test. Before release, in a disposable desktop account:

1. Start on Wayland with supported GTK/Adw; check CSS warnings, 600sp collapse,
   keyboard focus, text scale, dark/light themes, file dialogs and screen reader.
2. Export/import a closed small app, compare contents, dconf and permissions;
   test legacy v1, zero selected items, malformed/truncated archives and missing
   dependencies. Test explicit overwrite consent with unusual filenames.
3. Cancel during scanning, writing, staging and rollback. Close the main window,
   press Ctrl+Q, and confirm that mutation/rollback finishes and errors remain
   visible. Repeat when storage is full/read-only or cleanup is denied.
4. Test native/Flatpak process detection, refusal to close, inactive desktop
   settings, Steam, Boxes and Bottles with copies of representative profiles.
5. Build/install the generated local makepkg recipe; validate 29 GNU gettext
   catalogs, app launch, desktop integration, launcher symlink and uninstallation.
6. Measure RSS, CPU, I/O and responsiveness on HDD/2 GiB hardware. No measured
   performance percentage or stable-release certification is included here.

## Primary references consulted

- Python tarfile filters, limitations and streaming: https://docs.python.org/3/library/tarfile.html
- Python temporary files: https://docs.python.org/3/library/tempfile.html
- PyGObject main-thread and worker guidance: https://pygobject.gnome.org/guide/threading.html
- Gio lifetime: https://docs.gtk.org/gio/method.Application.hold.html
- Adw dialog close protection: https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/method.Dialog.set_can_close.html
- GTK CSS API: https://docs.gtk.org/gtk4/method.CssProvider.load_from_string.html
- Adw Spinner API: https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/class.Spinner.html
- Gtk label wrapping: https://docs.gtk.org/gtk4/method.Label.set_wrap_mode.html
- Gio Unix desktop entries: https://docs.gtk.org/gio-unix/class.DesktopAppInfo.html
- XDG base directories: https://specifications.freedesktop.org/basedir/latest/
- dconf operations: https://man.archlinux.org/man/dconf.1.en
- pidfd signaling: https://docs.python.org/3/library/signal.html
- Flatpak process identity: https://docs.flatpak.org/en/latest/flatpak-command-reference.html
- GNOME Boxes data scope: https://help.gnome.org/gnome-boxes/backup.html
- Arch package functions/dependencies: https://man.archlinux.org/man/PKGBUILD.5.en

Generated documentation can display development/alpha library versions. API
availability annotations were used; those headings are not evidence that an
alpha is the latest stable release or should be installed.
