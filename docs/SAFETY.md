# Safety model and manual recovery

Restore Settings changes the configuration of the current user. This document
describes what it guarantees, what it does not, and how to recover by hand if
an automatic rollback cannot finish.

## Scope

- Run it as your normal desktop user; it refuses to start as root.
- It only changes paths registered for an application in
  `data/app_registry.py`, inside your home folder, and only the dconf
  namespaces registered for that application — never the whole dconf database.
- HOME, shared folders (`~/.config`, `~/.local`, `~/.local/share`,
  `~/.local/state`, `~/.cache`, `~/.var/app` and the XDG folders), the dconf
  database file and paths reached through a symbolic-link folder are never
  removed or replaced. A symbolic link that *is* a registered path is moved or
  removed itself; its target is not touched.
- It is a settings tool, not a full-home backup: it does not snapshot running
  applications or live SQLite databases. Close the applications first.
  Detection of running programs uses the exact executable (or `flatpak ps`) and
  cannot see every wrapper script; it never sends SIGKILL and never ends a
  desktop session by itself.

## Reset

`config_paths` defines what a backup contains. `reset_paths` defaults to the
same paths, can be narrower when an application also keeps personal data, and
is empty for backup-only applications (Bottles). Shell history, installed Steam
games, GNOME Boxes disks and the GTK 3 bookmarks are therefore never reset.

**BigLinux defaults** needs a template in `/etc/skel` that maps to a safe
destination; without one the option is not offered and nothing is deleted.
Templates are copied to private staging before any live file changes.

**Program defaults** removes the registered reset paths. For browsers and mail
clients this includes bookmarks, passwords and local mail: keep the
"Create a backup" option enabled. Safety backups are stored in
`~/.local/state/biglinux-config/pre-reset-backups/`.

## Backups

Archive format version 2 (`.tar.gz`) contains a manifest, a BLAKE2b checksum of
every regular file and dconf dump, and the selected roots. Before any live
change, import checks:

- JSON metadata strictly (types, duplicate keys, sizes) and every member name
  (canonical, relative, no `..`, no control characters, no duplicates or
  aliases, no member below a link or file);
- member types: only files, folders and portable relative links;
- every checksum, the gzip trailer and that every declared root is present;
- that each root and dconf namespace belongs to the application as registered
  in *this* version.

Export stores absolute links that point inside HOME as relative links, leaves
out links that point outside HOME (and lists them in the result), skips sockets
and pipes, and never saves Chromium/Electron `Singleton*` runtime markers.

Limits (rejection, not truncation): 100,000 members, 16 GiB in total, 4 GiB per
file, 16 MiB of metadata, 4 MiB per dconf dump, path depth 64. Version 1
archives are still accepted but have no checksums; the import dialog says so.

Checksums detect damage, not authorship. An archive can carry settings that an
application later interprets as code: import only backups you trust and keep
them private.

## Transactions

Files are restored to a private `0700` folder in HOME
(`~/.biglinux-config-restore-*` or `~/.biglinux-config-reset-*`). Originals are
moved aside into the same folder, and `recovery.json` records each step before
it happens. Each rename is atomic, but the whole operation is not atomic
against power loss, SIGKILL or another process writing the same files.

On any error or cancellation the changes are rolled back: dconf namespaces are
reset and reloaded from their previous dump, and originals are moved back.
Cancellation waits for this to finish. Only one backup, import or reset runs at
a time (`~/.local/state/biglinux-config/operations.lock`).

## Manual recovery

If a message says that automatic recovery did not finish:

1. Do not delete the folder named in the message. Stop the affected
   applications.
2. Copy that folder to a private place; it can contain passwords and dconf
   secrets.
3. Read `recovery.json`. Each entry in `files` has the live path, the path of
   the original in `originals/`, and whether the original was moved and the
   new copy installed. `dconf` lists the namespaces with their previous dump.
4. For each entry, compare the live path with the original. Keep a copy of any
   live file you want to preserve, then move the original back.
5. For dconf, restore only the recorded namespaces:
   `dconf reset -f /namespace/` followed by `dconf load /namespace/ < dump`.
   Never run `dconf reset -f /`.

The journal can lag behind the filesystem after a crash; trust what is on disk.
Operation logs are in `~/.local/state/biglinux-config/operations.log`.

## Runtime requirements

Python 3.12, GTK 4.12 and libadwaita 1.6 or newer. The launcher runs
`python3 -I`, so `PYTHONPATH`, the user site directory and the current folder
cannot inject modules.
