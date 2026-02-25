# Restore Settings (biglinux-config)

<p align="center">
  <img src="biglinux-config/usr/share/pixmaps/restore-settings.svg" alt="Restore Settings" width="128">
</p>

<p align="center">
  <strong>Restore, backup, and manage application settings on BigLinux</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/GTK-4-green.svg" alt="GTK4">
  <img src="https://img.shields.io/badge/libadwaita-1.x-purple.svg" alt="libadwaita">
  <img src="https://img.shields.io/badge/Python-3.10+-yellow.svg" alt="Python">
  <img src="https://img.shields.io/badge/apps-136-orange.svg" alt="136 apps">
  <img src="https://img.shields.io/badge/languages-29-lightgrey.svg" alt="29 languages">
</p>

---

## Overview

**Restore Settings** is a native GTK4/libadwaita application for [BigLinux](https://www.biglinux.com.br/) that lets you reset, restore, export, and import application configuration files. With 136 preconfigured applications across 15 categories, it covers browsers, multimedia, development tools, terminals, desktop environments, Flatpak apps, and much more.

Built with modern GNOME HIG principles, it integrates seamlessly into any desktop environment running GTK4.

## Features

- **Restore BigLinux Defaults** — Reset any application to BigLinux default settings using `/etc/skel` skeleton files with a single click.
- **Restore Program Defaults** — Remove all custom settings so the application recreates its original default configuration from scratch.
- **Export Settings** — Back up dotfiles for multiple applications into a single compressed `.tar.gz` archive.
- **Import Settings** — Restore previously exported settings from a `.tar.gz` backup with per-application selection.
- **Full Directory Backup** — Optionally copy entire configuration directories instead of individual files.
- **Flatpak Support** — Automatically detect and manage Flatpak application settings alongside native packages.
- **Search** — Quickly find any installed application using the integrated search bar in the header.
- **Organized by Category** — Browse applications grouped into 15 categories: Favorites, Browsers, Communication, Multimedia, Graphics, Office, Development, Terminals, Shell, File Managers, Downloads, System, Gaming, Customization, and Desktop Environment.
- **Welcome Dialog** — Onboarding dialog showing all features on first launch, with a "Show on startup" toggle.
- **Internationalization** — Translated into 29 languages via gettext `.po` files.

## Screenshots

<!-- Add screenshots here -->
<!-- ![Main Window](docs/screenshot-main.png) -->
<!-- ![Restore Dialog](docs/screenshot-restore.png) -->
<!-- ![Export Dialog](docs/screenshot-export.png) -->

## Requirements

| Dependency | Minimum Version |
|---|---|
| Python | 3.10+ |
| GTK | 4.x |
| libadwaita | 1.x |
| PyGObject | 3.42+ |
| Flatpak | (optional, for Flatpak app detection) |

## Installation

### BigLinux / Manjaro / Arch Linux

```bash
# From the official BigLinux repository
sudo pacman -S biglinux-config
```

### From Source

```bash
git clone https://github.com/biglinux/biglinux-config.git
cd biglinux-config
python3 biglinux-config/usr/share/biglinux/biglinux-config/main.py
```

### Building the Package (makepkg)

```bash
cd pkgbuild
makepkg -si
```

## Project Structure

```
biglinux-config/
├── biglinux-config/
│   ├── locale/                      # Translation files (.po, .json, .pot)
│   └── usr/
│       ├── bin/
│       │   ├── big-config           # System launcher script
│       │   └── biglinux-config      # Alternative launcher
│       ├── share/
│       │   ├── applications/
│       │   │   └── big-config.desktop
│       │   ├── biglinux/biglinux-config/
│       │   │   ├── main.py          # Application entry point
│       │   │   ├── backend/
│       │   │   │   ├── app_detector.py       # Detect installed native apps
│       │   │   │   ├── backup_manager.py     # Export/import .tar.gz backups
│       │   │   │   ├── flatpak_detector.py   # Detect installed Flatpak apps
│       │   │   │   └── reset_manager.py      # Reset configs (skel / delete)
│       │   │   ├── data/
│       │   │   │   └── app_registry.py       # 136 app entries + categories
│       │   │   ├── img/                      # Custom SVG icons
│       │   │   ├── ui/
│       │   │   │   ├── application.py        # Main window + Adw.Application
│       │   │   │   ├── app_grid.py           # FlowBox grid of app buttons
│       │   │   │   ├── category_sidebar.py   # Category sidebar navigation
│       │   │   │   ├── restore_dialog.py     # Restore confirmation dialogs
│       │   │   │   ├── backup_dialog.py      # Export/import dialogs
│       │   │   │   ├── about_dialog.py       # About dialog
│       │   │   │   └── welcome_dialog.py     # Welcome/onboarding dialog
│       │   │   └── utils/
│       │   │       └── __init__.py           # i18n helper (_)
│       │   ├── locale/                       # Compiled translations (.mo, .json)
│       │   └── pixmaps/                      # Application icons (.svg, .png)
├── pkgbuild/
│   └── PKGBUILD                              # Arch/BigLinux package build script
├── LICENSE                                   # GPL-3.0
└── README.md
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    main.py                          │
│               BigConfigApp (Adw.Application)        │
├─────────────┬──────────────┬────────────────────────┤
│   UI Layer  │  Backend     │  Data                  │
├─────────────┼──────────────┼────────────────────────┤
│ application │ app_detector │ app_registry            │
│ app_grid    │ flatpak_det. │ (136 AppEntry objects)  │
│ sidebar     │ reset_manager│                         │
│ dialogs     │ backup_mgr   │                         │
└─────────────┴──────────────┴────────────────────────┘
```

- **UI Layer** — GTK4 + libadwaita widgets. Split view with category sidebar and app grid. Dialogs for restore, export/import, about, and welcome.
- **Backend** — Detects installed applications, manages config reset via `/etc/skel` or deletion, and handles `.tar.gz` backup export/import.
- **Data** — Single-source-of-truth registry of 136 applications with their config paths, skel paths, icons, categories, and detection binaries.

## How It Works

### Restoring Settings

1. Select an application from the grid.
2. Choose between:
   - **Restore BigLinux Defaults** — Copies preconfigured files from `/etc/skel` to your home directory.
   - **Restore Program Defaults** — Deletes all custom configuration files so the application recreates its defaults.
3. If the application is currently running, you will be prompted to close it first.
4. A success/error dialog confirms the operation result.

### Exporting Settings

1. Open **Menu → Export settings…**
2. Select which installed applications to include in the backup.
3. Choose a destination file (`.tar.gz`).
4. The archive will contain all selected dotfiles and configuration directories.

### Importing Settings

1. Open **Menu → Import settings…**
2. Select a previously exported `.tar.gz` file.
3. Choose which applications to restore from the backup.
4. Files are extracted to the appropriate locations under `$HOME`.

## Configuration

User preferences are stored at:

```
~/.config/restore-settings/settings.json
```

Currently stores:
- `show-welcome` — Whether to display the welcome dialog on startup (default: `true`).

## Translation

The application uses gettext for internationalization. Translation files are located in `biglinux-config/locale/`.

### Supported Languages

Bulgarian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hebrew, Croatian, Hungarian, Icelandic, Italian, Japanese, Korean, Norwegian, Polish, Portuguese, Portuguese (Brazil), Romanian, Russian, Slovak, Swedish, Turkish, Ukrainian, Chinese.

### Adding a New Translation

1. Copy the template: `cp locale/biglinux-config.pot locale/<lang>.po`
2. Edit the `.po` file with your translations.
3. Compile: `msgfmt locale/<lang>.po -o usr/share/locale/<lang>/LC_MESSAGES/biglinux-config.mo`

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request.

### Adding a New Application

To add support for a new application, add an `AppEntry` to the `APP_REGISTRY` list in `data/app_registry.py`:

```python
AppEntry(
    app_id="my-app",
    name="My Application",
    icon="my-app",
    binary="/usr/bin/my-app",
    category="multimedia",
    config_paths=["~/.config/my-app"],
    skel_paths=["/etc/skel/.config/my-app"],
)
```

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.

## Links

- **Repository**: [github.com/biglinux/biglinux-config](https://github.com/biglinux/biglinux-config)
- **Issues**: [github.com/biglinux/biglinux-config/issues](https://github.com/biglinux/biglinux-config/issues)
- **BigLinux**: [biglinux.com.br](https://www.biglinux.com.br/)
