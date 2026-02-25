# BigLinux Config — Plano de Reconstrução Completa

## Visão Geral

Aplicativo GTK4 + libadwaita em Python para restauração de configurações de programas no BigLinux.
Substitui o antigo BigBashView com uma interface moderna, acessível e preparada para competição internacional.

O programa detecta aplicativos instalados no sistema, lista seus dotfiles/configurações,
e oferece duas opções de restauração:
1. **Restaurar padrão do BigLinux** — copia configs de `/etc/skel/`
2. **Restaurar padrão do programa** — remove dotfiles (o app recria com padrões internos)

---

## Arquitetura

```
biglinux-config/
├── usr/
│   ├── bin/
│   │   └── biglinux-config              # Entry point (bash wrapper)
│   └── share/
│       ├── applications/
│       │   └── biglinux-config.desktop
│       ├── biglinux/biglinux-config/     # App Python
│       │   ├── main.py                   # Entry point Python
│       │   ├── ui/
│       │   │   ├── __init__.py
│       │   │   ├── application.py        # Adw.Application principal
│       │   │   ├── category_sidebar.py   # Sidebar de categorias
│       │   │   ├── app_grid.py           # Grid de apps (FlowBox)
│       │   │   ├── restore_dialog.py     # Diálogo de restauração
│       │   │   └── about_dialog.py       # Diálogo Sobre
│       │   ├── data/
│       │   │   ├── __init__.py
│       │   │   └── app_registry.py       # Registro completo de apps e dotfiles
│       │   ├── backend/
│       │   │   ├── __init__.py
│       │   │   ├── reset_manager.py      # Lógica de reset (backup + rm + skel copy)
│       │   │   ├── app_detector.py       # Detecção de apps nativos instalados
│       │   │   └── flatpak_detector.py   # Detecção automática de Flatpaks
│       │   └── utils/
│       │       ├── __init__.py
│       │       └── i18n.py               # Internacionalização
│       ├── locale/                       # Traduções compiladas
│       └── icons/hicolor/scalable/apps/
│           └── biglinux-config.svg
├── locale/                               # Fontes .po/.pot
└── pkgbuild/
    └── PKGBUILD
```

### Separação de responsabilidades

| Camada     | Responsabilidade                                              |
|------------|---------------------------------------------------------------|
| `ui/`      | Widgets GTK4, layout, sinais, acessibilidade                  |
| `data/`    | Registro estático de apps, categorias, caminhos de dotfiles   |
| `backend/` | Operações de filesystem: backup, remoção, cópia de skel       |
| `utils/`   | i18n, helpers genéricos                                       |

---

## Widget Hierarchy

```
Adw.Application
└── Adw.ApplicationWindow
    └── Adw.ToolbarView
        ├── Adw.HeaderBar
        │   ├── Gtk.Button (app icon)
        │   └── Gtk.SearchEntry
        └── Adw.NavigationSplitView
            ├─ SIDEBAR: Adw.NavigationPage
            │  └─ Adw.ToolbarView
            │     ├─ Adw.HeaderBar (título "Categorias")
            │     └─ Gtk.ScrolledWindow
            │        └─ Gtk.ListBox (CategorySidebar)
            │           └─ Adw.ActionRow × N categorias
            │
            └─ CONTENT: Adw.NavigationPage
               └─ Adw.ToolbarView
                  ├─ Adw.HeaderBar
                  │  └─ Gtk.SearchEntry
                  └─ Gtk.ScrolledWindow
                     └─ Adw.Clamp (max-width: 1200px)
                        └─ Gtk.FlowBox (AppGrid)
                           └─ AppCard (Gtk.Button) × N apps
                              ├── Gtk.Image (ícone do app)
                              └── Gtk.Label (nome do app)

Adw.Dialog (RestoreDialog) — modal para cada app
├── Adw.StatusPage (ícone + nome do app)
├── Adw.PreferencesGroup
│   ├─ Adw.ActionRow "Restaurar padrão do BigLinux"
│   │   └─ Gtk.Button (ação)
│   └─ Adw.ActionRow "Restaurar padrão do programa"
│       └─ Gtk.Button (ação)
└── Gtk.Box (botões Cancelar)

Adw.AlertDialog (confirmação destrutiva)
├── Heading: "Restaurar configurações?"
├── Body: aviso sobre perda de customizações
└── Responses: Cancelar / Restaurar (destructive-action)

Adw.Dialog (resultado)
├── Adw.StatusPage (sucesso/erro)
└── Gtk.Button "OK"
```

---

## Etapas de Implementação

### Fase 1 — Infraestrutura base

- [ ] **1.1** Criar estrutura de diretórios
- [ ] **1.2** Criar `main.py` (entry point)
- [ ] **1.3** Criar `utils/i18n.py` (gettext setup)
- [ ] **1.4** Criar `ui/application.py` (Adw.Application + Window)
- [ ] **1.5** Criar script wrapper `usr/bin/biglinux-config`
- [ ] **1.6** Criar `.desktop` file

### Fase 2 — Registro de aplicativos

- [ ] **2.1** Criar `data/app_registry.py` com lista completa de ~120+ apps
- [ ] **2.2** Cada entrada: `app_id`, `name`, `icon`, `binary`, `category`, `config_paths`, `skel_paths`, `process_name`
- [ ] **2.3** Categorias: Navegadores, Comunicação, Multimídia, Gráficos, Escritório, Desenvolvimento, Terminais, Gerenciadores de Arquivo, Sistema, Jogos, Personalização

### Fase 3 — Backend de reset

- [ ] **3.1** Criar `backend/app_detector.py` — detecta quais apps estão instalados (nativos + Flatpak)
- [ ] **3.2** Criar `backend/flatpak_detector.py` — detecção automática de Flatpaks instalados via `flatpak list`
- [ ] **3.3** Criar `backend/reset_manager.py` — lógica de reset com:
  - Verificação se o app está em execução (pidof/pgrep)
  - Backup opcional antes de remover
  - Remoção de dotfiles
  - Cópia de arquivos do skel
  - Retorno de status (sucesso/erro/app_running)
  - Execução assíncrona para não bloquear a UI

### Fase 4 — UI: Sidebar e Grid

- [ ] **4.1** Criar `ui/category_sidebar.py` — ListBox com categorias e ícones
- [ ] **4.2** Criar `ui/app_grid.py` — FlowBox com cards de apps
- [ ] **4.3** Integrar sidebar ↔ grid (filtro por categoria)
- [ ] **4.4** Implementar busca por texto

### Fase 5 — UI: Diálogos

- [ ] **5.1** Criar `ui/restore_dialog.py` — diálogo com as duas opções de restauração
- [ ] **5.2** Implementar Adw.AlertDialog para confirmação destrutiva
- [ ] **5.3** Feedback inline (StatusPage) para sucesso/erro
- [ ] **5.4** Tratamento de app em execução (aviso + opção de fechar)

### Fase 6 — Acessibilidade e UX

- [ ] **6.1** accessible-name em TODOS os widgets interativos
- [ ] **6.2** Navegação completa por teclado (Tab, Enter, Escape, setas)
- [ ] **6.3** Labels descritivos em ActionRows (subtitle com info de dotfiles)
- [ ] **6.4** Contraste e escala (testar 200% font scaling)
- [ ] **6.5** Atalhos de teclado (Ctrl+F para busca, Escape para fechar diálogo)

### Fase 7 — Desktop Environment Reset

- [ ] **7.1** Detecção de DE ativo (KDE/XFCE/GNOME/Cinnamon/DDE)
- [ ] **7.2** Card especial no topo para reset completo do DE
- [ ] **7.3** Aviso sobre necessidade de logout
- [ ] **7.4** Botão "Sair da sessão" no diálogo de sucesso

### Fase 8 — Polimento

- [ ] **8.1** CSS customizado (consistente com Adwaita HIG)
- [ ] **8.2** Responsividade (AdwBreakpoint para telas estreitas)
- [ ] **8.3** Animações e transições suaves
- [ ] **8.4** Persistência de estado (tamanho da janela)
- [ ] **8.5** Diálogo "Sobre" (AdwAboutDialog)

### Fase 9 — Empacotamento

- [ ] **9.1** Atualizar PKGBUILD
- [ ] **9.2** Gerar/atualizar .pot e traduções
- [ ] **9.3** Testes manuais em KDE, GNOME, XFCE

---

## Registro Completo de Aplicativos

### Navegadores Web
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| Firefox | `/usr/lib/firefox/firefox` | `~/.mozilla` | `/etc/skel/.mozilla` |
| Brave | `/usr/lib/brave-browser/brave` | `~/.config/BraveSoftware` | — |
| Google Chrome | `/opt/google/chrome/google-chrome` | `~/.config/google-chrome` | — |
| Chromium | `/usr/lib/chromium/chromium` | `~/.config/chromium` | `/etc/skel/.config/chromium` |
| Vivaldi | `/usr/bin/vivaldi` | `~/.config/vivaldi` | — |
| Microsoft Edge | `/usr/bin/microsoft-edge-stable` | `~/.config/microsoft-edge` | — |
| Opera | `/usr/bin/opera` | `~/.config/opera` | — |
| Pale Moon | `/usr/lib/palemoon/palemoon` | `~/.moonchild productions` | — |
| Tor Browser | `/usr/bin/torbrowser-launcher` | `~/.local/share/torbrowser` | — |
| Midori | `/usr/bin/midori` | `~/.config/midori` | — |
| Epiphany (GNOME Web) | `/usr/bin/epiphany` | `~/.local/share/epiphany`, `~/.config/epiphany` | — |
| Floorp | `/usr/lib/floorp/floorp` | `~/.floorp` | — |
| Zen Browser | `/usr/bin/zen-browser` | `~/.zen` | — |
| Librewolf | `/usr/bin/librewolf` | `~/.librewolf` | — |

### Comunicação e Email
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| Thunderbird | `/usr/bin/thunderbird` | `~/.thunderbird` | — |
| Telegram Desktop | `/usr/bin/telegram-desktop` | `~/.local/share/TelegramDesktop` | — |
| Discord | `/usr/bin/discord` | `~/.config/discord` | — |
| Signal | `/usr/bin/signal-desktop` | `~/.config/Signal` | — |
| Element | `/usr/bin/element-desktop` | `~/.config/Element` | — |
| Slack | `/usr/bin/slack` | `~/.config/Slack` | — |
| HexChat | `/usr/bin/hexchat` | `~/.config/hexchat` | — |
| Evolution | `/usr/bin/evolution` | `~/.config/evolution`, `~/.local/share/evolution` | — |
| Geary | `/usr/bin/geary` | `~/.local/share/geary` | — |

### Multimídia — Vídeo
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| VLC | `/usr/bin/vlc` | `~/.config/vlc` | `/etc/skel/.config/vlc` |
| SMPlayer | `/usr/bin/smplayer` | `~/.config/smplayer` | `/etc/skel/.config/smplayer` |
| mpv | `/usr/bin/mpv` | `~/.config/mpv` | `/etc/skel/.config/mpv` |
| Celluloid | `/usr/bin/celluloid` | `~/.config/celluloid` | — |
| Totem (GNOME Videos) | `/usr/bin/totem` | `~/.config/totem`, `~/.local/share/totem` | — |
| Parole | `/usr/bin/parole` | `~/.config/parole` | — |
| Haruna | `/usr/bin/haruna` | `~/.config/haruna` | — |
| Kodi | `/usr/bin/kodi` | `~/.kodi` | — |
| OBS Studio | `/usr/bin/obs` | `~/.config/obs-studio` | — |
| Kdenlive | `/usr/bin/kdenlive` | `~/.config/kdenlive`, `~/.local/share/kdenlive` | — |
| Shotcut | `/usr/bin/shotcut` | `~/.config/Meltytech` | — |
| HandBrake | `/usr/bin/ghb` | `~/.config/ghb` | — |
| MystiQ | `/usr/bin/mystiq` | `~/.config/mystiq` | `/etc/skel/.config/mystiq` |
| vokoscreenNG | `/usr/bin/vokoscreenNG` | `~/.config/vokoscreenNG` | — |

### Multimídia — Áudio
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| Clementine | `/usr/bin/clementine` | `~/.config/Clementine` | `/etc/skel/.config/Clementine` |
| Rhythmbox | `/usr/bin/rhythmbox` | `~/.local/share/rhythmbox`, `~/.config/rhythmbox` | — |
| Strawberry | `/usr/bin/strawberry` | `~/.config/strawberry` | — |
| Audacious | `/usr/bin/audacious` | `~/.config/audacious` | — |
| Lollypop | `/usr/bin/lollypop` | `~/.local/share/lollypop` | — |
| Elisa | `/usr/bin/elisa` | `~/.config/elisa` | — |
| Audacity | `/usr/bin/audacity` | `~/.config/audacity`, `~/.audacity-data` | — |
| LMMS | `/usr/bin/lmms` | `~/.config/lmms`, `~/.lmms` | — |

### Gráficos e Imagens
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| GIMP | `/usr/bin/gimp` | `~/.config/GIMP` | `/etc/skel/.config/GIMP` |
| Inkscape | `/usr/bin/inkscape` | `~/.config/inkscape` | — |
| Krita | `/usr/bin/krita` | `~/.config/krita*`, `~/.local/share/krita` | — |
| Gwenview | `/usr/bin/gwenview` | `~/.local/share/gwenview`, `~/.config/gwenviewrc` | `/etc/skel/.config/gwenviewrc` |
| Ristretto | `/usr/bin/ristretto` | `~/.config/ristretto` | — |
| Eye of GNOME (eog) | `/usr/bin/eog` | `~/.config/eog` | — |
| Loupe (GNOME Image Viewer) | `/usr/bin/loupe` | `~/.config/loupe` | — |
| Shotwell | `/usr/bin/shotwell` | `~/.local/share/shotwell` | — |
| digikam | `/usr/bin/digikam` | `~/.config/digikam*`, `~/.local/share/digikam` | — |
| Blender | `/usr/bin/blender` | `~/.config/blender` | — |
| darktable | `/usr/bin/darktable` | `~/.config/darktable` | — |
| Ksnip | `/usr/bin/ksnip` | `~/.config/ksnip` | `/etc/skel/.config/ksnip` |
| Flameshot | `/usr/bin/flameshot` | `~/.config/flameshot` | — |
| Spectacle | `/usr/bin/spectacle` | `~/.config/spectaclerc` | — |

### Escritório e Produtividade
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| LibreOffice | `/usr/bin/libreoffice` | `~/.config/libreoffice` | `/etc/skel/.config/libreoffice` |
| Okular | `/usr/bin/okular` | `~/.local/share/okular`, `~/.config/okularrc`, `~/.config/okularpartrc` | `/etc/skel/.config/okularrc` |
| Evince | `/usr/bin/evince` | `~/.config/evince` | — |
| Calibre | `/usr/bin/calibre` | `~/.config/calibre` | — |
| Xournalpp | `/usr/bin/xournalpp` | `~/.config/xournalpp` | — |
| Zathura | `/usr/bin/zathura` | `~/.config/zathura` | — |
| FreeOffice | `/usr/bin/freeoffice` | `~/.SoftMaker` | — |
| OnlyOffice | `/usr/bin/onlyoffice-desktopeditors` | `~/.config/onlyoffice` | — |
| Obsidian | `/usr/bin/obsidian` | `~/.config/obsidian` | — |
| Logseq | `/usr/bin/logseq` | `~/.config/Logseq`, `~/.logseq` | — |

### Terminais
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| Konsole | `/usr/bin/konsole` | `~/.config/konsolerc`, `~/.local/share/konsole` | `/etc/skel/.config/konsolerc`, `/etc/skel/.local/share/konsole` |
| GNOME Terminal | `/usr/bin/gnome-terminal` | dconf: `/org/gnome/terminal/` | — |
| XFCE4 Terminal | `/usr/bin/xfce4-terminal` | `~/.config/xfce4/terminal` | `/etc/skel/.config/xfce4/terminal` |
| Alacritty | `/usr/bin/alacritty` | `~/.config/alacritty` | — |
| Kitty | `/usr/bin/kitty` | `~/.config/kitty` | — |
| WezTerm | `/usr/bin/wezterm` | `~/.config/wezterm` | — |
| Tilix | `/usr/bin/tilix` | dconf: `/com/gexperts/Tilix/` | — |
| Yakuake | `/usr/bin/yakuake` | `~/.config/yakuakerc` | — |
| Terminator | `/usr/bin/terminator` | `~/.config/terminator` | — |
| foot | `/usr/bin/foot` | `~/.config/foot` | — |
| Guake | `/usr/bin/guake` | dconf: `/apps/guake/` | — |

### Shell
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| Bash | `/usr/bin/bash` | `~/.bashrc`, `~/.bash_profile`, `~/.bash_history`, `~/.bash_logout` | `/etc/skel/.bashrc`, `/etc/skel/.bash_profile` |
| Zsh | `/usr/bin/zsh` | `~/.zshrc`, `~/.zsh_history`, `~/.zshenv`, `~/.zprofile` | `/etc/skel/.zshrc` |
| Fish | `/usr/bin/fish` | `~/.config/fish` | — |
| Starship | `/usr/bin/starship` | `~/.config/starship.toml` | — |

### Gerenciadores de Arquivo
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| Dolphin | `/usr/bin/dolphin` | `~/.local/share/dolphin`, `~/.local/share/kxmlgui5/dolphin`, `~/.config/dolphinrc` | `/etc/skel/.config/dolphinrc` |
| Nautilus (Files) | `/usr/bin/nautilus` | `~/.config/nautilus`, `~/.local/share/nautilus` | — |
| Nemo | `/usr/bin/nemo` | `~/.config/nemo`, `~/.local/share/nemo` | — |
| Thunar | `/usr/bin/thunar` | `~/.config/Thunar`, `~/.config/thunar` | — |
| PCManFM | `/usr/bin/pcmanfm` | `~/.config/pcmanfm` | — |
| Caja | `/usr/bin/caja` | `~/.config/caja` | — |
| Double Commander | `/usr/bin/doublecmd` | `~/.config/doublecmd` | — |
| Krusader | `/usr/bin/krusader` | `~/.config/krusaderrc`, `~/.local/share/krusader` | — |

### Desenvolvimento
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| Kate | `/usr/bin/kate` | `~/.local/share/kate`, `~/.local/share/kxmlgui5/kate*`, `~/.config/katerc`, `~/.config/kateschemarc` | `/etc/skel/.config/katerc` |
| VS Code | `/usr/bin/code` | `~/.config/Code`, `~/.vscode` | — |
| VS Code Insiders | `/usr/bin/code-insiders` | `~/.config/Code - Insiders`, `~/.vscode-insiders` | — |
| Sublime Text | `/usr/bin/subl` | `~/.config/sublime-text` | — |
| Gedit | `/usr/bin/gedit` | `~/.config/gedit`, `~/.local/share/gedit` | — |
| GNOME Text Editor | `/usr/bin/gnome-text-editor` | `~/.config/gnome-text-editor` | — |
| Mousepad | `/usr/bin/mousepad` | `~/.config/Mousepad` | — |
| Neovim | `/usr/bin/nvim` | `~/.config/nvim`, `~/.local/share/nvim`, `~/.local/state/nvim` | — |
| Vim | `/usr/bin/vim` | `~/.vimrc`, `~/.vim` | — |
| Emacs | `/usr/bin/emacs` | `~/.emacs`, `~/.emacs.d` | — |
| Geany | `/usr/bin/geany` | `~/.config/geany` | — |

### Torrent / Downloads
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| qBittorrent | `/usr/bin/qbittorrent` | `~/.config/qBittorrent`, `~/.local/share/qBittorrent` | `/etc/skel/.config/qBittorrent` |
| Transmission | `/usr/bin/transmission-gtk` | `~/.config/transmission` | — |
| Deluge | `/usr/bin/deluge` | `~/.config/deluge` | — |
| KTorrent | `/usr/bin/ktorrent` | `~/.config/ktorrentrc`, `~/.local/share/ktorrent` | — |

### Sistema e Utilitários
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| KDE System Settings | `/usr/bin/systemsettings` | `~/.config/systemsettingsrc` | — |
| GNOME Settings | `/usr/bin/gnome-control-center` | dconf: `/org/gnome/` | — |
| Timeshift | `/usr/bin/timeshift` | `/etc/timeshift` (root) | — |
| BleachBit | `/usr/bin/bleachbit` | `~/.config/bleachbit` | — |
| Stacer | `/usr/bin/stacer` | `~/.config/stacer` | — |
| baobab (Disk Usage) | `/usr/bin/baobab` | `~/.config/baobab` | — |
| GParted | `/usr/bin/gparted` | — (root app) | — |
| Virtual Box | `/usr/bin/VirtualBox` | `~/.config/VirtualBox` | — |
| GNOME Boxes | `/usr/bin/gnome-boxes` | `~/.config/gnome-boxes`, `~/.local/share/gnome-boxes` | — |
| Virt-Manager | `/usr/bin/virt-manager` | `~/.config/virt-manager` | — |
| KeePassXC | `/usr/bin/keepassxc` | `~/.config/keepassxc` | — |
| Bitwarden | `/usr/bin/bitwarden` | `~/.config/Bitwarden` | — |
| Syncthing | `/usr/bin/syncthing` | `~/.config/syncthing` | — |
| Rclone | `/usr/bin/rclone` | `~/.config/rclone` | — |
| Lutris | `/usr/bin/lutris` | `~/.config/lutris`, `~/.local/share/lutris` | — |
| Steam | `/usr/bin/steam` | `~/.steam`, `~/.local/share/Steam` | — |
| Heroic Games Launcher | `/usr/bin/heroic` | `~/.config/heroic` | — |
| Bottles | `/usr/bin/bottles` | `~/.local/share/bottles` | — |

### Personalização
| App | Binário | Config Paths | Skel |
|-----|---------|-------------|------|
| GNOME Tweaks | `/usr/bin/gnome-tweaks` | dconf: `/org/gnome/desktop/` | — |
| LXAppearance | `/usr/bin/lxappearance` | `~/.config/gtk-3.0`, `~/.gtkrc-2.0` | — |
| Kvantum | `/usr/bin/kvantummanager` | `~/.config/Kvantum` | — |
| dconf Editor | `/usr/bin/dconf-editor` | — (modifica dconf) | — |
| Conky | `/usr/bin/conky` | `~/.config/conky`, `~/.conkyrc` | — |
| Plank | `/usr/bin/plank` | `~/.config/plank` | — |
| Latte Dock | `/usr/bin/latte-dock` | `~/.config/lattedockrc`, `~/.config/latte` | — |

### Aplicativos Flatpak

O programa deve detectar automaticamente aplicativos instalados via Flatpak e oferecer restauração.

**Como funciona:**
- Configs ficam em `~/.var/app/<app-id>/` (config, data, cache isolados)
- Listar apps instalados: `flatpak list --app --columns=application,name`
- Cada app tem subdiretórios: `config/`, `data/`, `cache/`
- Restaurar = remover `~/.var/app/<app-id>/config/` e `~/.var/app/<app-id>/data/`
- Não existe "skel" para Flatpak — apenas reset para padrão do programa

| App (Flatpak ID) | Nome | Config Path |
|-------------------|------|-------------|
| `org.mozilla.firefox` | Firefox | `~/.var/app/org.mozilla.firefox/` |
| `com.brave.Browser` | Brave | `~/.var/app/com.brave.Browser/` |
| `com.google.Chrome` | Google Chrome | `~/.var/app/com.google.Chrome/` |
| `org.chromium.Chromium` | Chromium | `~/.var/app/org.chromium.Chromium/` |
| `com.discordapp.Discord` | Discord | `~/.var/app/com.discordapp.Discord/` |
| `org.telegram.desktop` | Telegram | `~/.var/app/org.telegram.desktop/` |
| `org.signal.Signal` | Signal | `~/.var/app/org.signal.Signal/` |
| `com.slack.Slack` | Slack | `~/.var/app/com.slack.Slack/` |
| `org.videolan.VLC` | VLC | `~/.var/app/org.videolan.VLC/` |
| `io.mpv.Mpv` | mpv | `~/.var/app/io.mpv.Mpv/` |
| `com.obsproject.Studio` | OBS Studio | `~/.var/app/com.obsproject.Studio/` |
| `org.kde.kdenlive` | Kdenlive | `~/.var/app/org.kde.kdenlive/` |
| `org.gimp.GIMP` | GIMP | `~/.var/app/org.gimp.GIMP/` |
| `org.inkscape.Inkscape` | Inkscape | `~/.var/app/org.inkscape.Inkscape/` |
| `org.kde.krita` | Krita | `~/.var/app/org.kde.krita/` |
| `org.blender.Blender` | Blender | `~/.var/app/org.blender.Blender/` |
| `org.libreoffice.LibreOffice` | LibreOffice | `~/.var/app/org.libreoffice.LibreOffice/` |
| `org.onlyoffice.desktopeditors` | OnlyOffice | `~/.var/app/org.onlyoffice.desktopeditors/` |
| `com.visualstudio.code` | VS Code | `~/.var/app/com.visualstudio.code/` |
| `org.mozilla.Thunderbird` | Thunderbird | `~/.var/app/org.mozilla.Thunderbird/` |
| `com.spotify.Client` | Spotify | `~/.var/app/com.spotify.Client/` |
| `com.valvesoftware.Steam` | Steam | `~/.var/app/com.valvesoftware.Steam/` |
| `net.lutris.Lutris` | Lutris | `~/.var/app/net.lutris.Lutris/` |
| `com.heroicgameslauncher.hgl` | Heroic | `~/.var/app/com.heroicgameslauncher.hgl/` |
| `com.usebottles.bottles` | Bottles | `~/.var/app/com.usebottles.bottles/` |
| `org.qbittorrent.qBittorrent` | qBittorrent | `~/.var/app/org.qbittorrent.qBittorrent/` |
| `de.haeckerfelix.Fragments` | Fragments | `~/.var/app/de.haeckerfelix.Fragments/` |
| `org.keepassxc.KeePassXC` | KeePassXC | `~/.var/app/org.keepassxc.KeePassXC/` |
| `com.bitwarden.desktop` | Bitwarden | `~/.var/app/com.bitwarden.desktop/` |
| `md.obsidian.Obsidian` | Obsidian | `~/.var/app/md.obsidian.Obsidian/` |
| (detecção automática) | Qualquer Flatpak instalado | `~/.var/app/<app-id>/` |

**Detecção automática de Flatpaks:**
```python
import subprocess

def get_installed_flatpaks() -> list[dict]:
    """Detecta todos os Flatpaks instalados pelo usuário."""
    result = subprocess.run(
        ["flatpak", "list", "--app", "--user", "--system",
         "--columns=application,name,origin"],
        capture_output=True, text=True
    )
    apps = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            app_id, name = parts[0], parts[1]
            config_path = os.path.expanduser(f"~/.var/app/{app_id}")
            if os.path.isdir(config_path):
                apps.append({
                    "app_id": app_id,
                    "name": f"{name} (Flatpak)",
                    "config_paths": [config_path],
                    "is_flatpak": True,
                })
    return apps
```

**Regras para Flatpak no UI:**
- Apps nativos e Flatpak do mesmo programa aparecem como entradas separadas
- Badge "(Flatpak)" no nome para diferenciar
- Flatpak só tem opção "Restaurar padrão do programa" (não tem skel)
- Ícone resolve via Flatpak export: `/var/lib/flatpak/exports/share/icons/` ou `~/.local/share/flatpak/exports/share/icons/`

### Desktop Environments (Reset completo)
| DE | Detecção | Config Paths | Skel |
|----|----------|-------------|------|
| KDE Plasma | `$XDG_CURRENT_DESKTOP=KDE` | `~/.config/plasma*`, `~/.config/kwin*`, `~/.config/kde*`, `~/.local/share/plasma*`, `~/.local/share/kwin`, etc. | `/etc/skel/.config/` (completo) |
| XFCE | `$XDG_CURRENT_DESKTOP=XFCE` | `~/.config/xfce4/`, `~/.config/Thunar/` | `/etc/skel/.config/xfce4/` |
| GNOME | `$XDG_CURRENT_DESKTOP=GNOME` | dconf dump + `~/.config/gnome*` | `/etc/skel/.config/dconf/` |
| Cinnamon | `$XDG_CURRENT_DESKTOP=X-Cinnamon` | `~/.config/cinnamon/`, `~/.cinnamon/` | — |
| Deepin (DDE) | `$XDG_CURRENT_DESKTOP=Deepin` | `~/.config/deepin/` | — |
| MATE | `$XDG_CURRENT_DESKTOP=MATE` | dconf: `/org/mate/` | — |
| Budgie | `$XDG_CURRENT_DESKTOP=Budgie` | dconf: `/com/solus-project/budgie-panel/` | — |

---

## Categorias no UI

| ID              | Label (pt-BR)              | Ícone                            |
|-----------------|----------------------------|----------------------------------|
| `favorites`     | Principais                 | `view-app-grid-symbolic`         |
| `browsers`      | Navegadores                | `web-browser-symbolic`           |
| `communication` | Comunicação                | `mail-send-symbolic`             |
| `multimedia`    | Multimídia                 | `applications-multimedia-symbolic` |
| `graphics`      | Gráficos                   | `applications-graphics-symbolic` |
| `office`        | Escritório                 | `x-office-document-symbolic`     |
| `development`   | Desenvolvimento            | `utilities-terminal-symbolic`    |
| `terminals`     | Terminais                  | `terminal-symbolic`              |
| `filemanagers`  | Gerenciador de Arquivos    | `system-file-manager-symbolic`   |
| `downloads`     | Downloads                  | `folder-download-symbolic`       |
| `system`        | Sistema                    | `emblem-system-symbolic`         |
| `gaming`        | Jogos                      | `applications-games-symbolic`    |
| `customization` | Personalização             | `preferences-desktop-theme-symbolic` |
| `shell`         | Shell                      | `text-x-script-symbolic`        |
| `desktop_env`   | Ambiente de Trabalho       | `user-desktop-symbolic`          |

---

## Requisitos de Acessibilidade (Orca)

1. Cada `Gtk.Button` do grid: `set_tooltip_text()` + accessible-name com nome do app
2. Cada `Adw.ActionRow`: label + subtitle sempre presentes
3. `Gtk.SearchEntry`: accessible-name "Pesquisar aplicativo"
4. `Adw.AlertDialog`: lido automaticamente pelo Orca (heading + body)
5. Navegação por Tab entre: sidebar → search → grid → diálogos
6. Grid: setas ←→↑↓ para navegar entre cards
7. Enter para ativar card, Escape para fechar diálogo
8. Status de cada operação anunciado via accessible-description dinâmico

---

## Requisitos de UX

1. **Primeira execução**: sem wizard — o app já mostra a categoria "Principais" com apps mais comuns
2. **Feedback**: após restauração, inline StatusPage com resultado (não toast)
3. **Confirmação**: AlertDialog destrutivo antes de qualquer reset
4. **App em execução**: aviso com opção de fechar automaticamente
5. **Busca**: filtragem instantânea no FlowBox, sem delay
6. **Max 5-7 elementos visíveis por interação**: cada card é uma unidade; diálogos têm max 3 ações
7. **Linguagem**: "Limpar configurações do Firefox" em vez de "rm -rf ~/.mozilla"
8. **A categoria sidebar esconde categorias sem apps**: UX limpa
9. **Responsividade**: em janelas estreitas, sidebar colapsa (NavigationSplitView automático)

---

## Fluxo do Usuário

```
1. Abre o app → vê grid com apps da categoria "Principais"
2. Navega por categorias na sidebar OU pesquisa
3. Clica num app → abre diálogo com:
   a. Info: quais configs serão afetadas
   b. Botão "Restaurar padrão do BigLinux" (copia de /etc/skel)
   c. Botão "Restaurar padrão do programa" (apaga dotfiles)
4. Clica numa opção → AlertDialog: "Tem certeza? Customizações serão perdidas"
5. Confirma → backend executa:
   a. Verifica se app está rodando
   b. Se sim: pergunta se quer fechar
   c. Remove configs / copia skel
6. StatusPage mostra resultado (sucesso/erro)
7. Para DE reset: mostra aviso de logout necessário
```

---

## CSS Personalizado

Seguir o padrão do bigcontrolcenter — CSS inline via `Gtk.CssProvider`:
- `.app-card` — cards no grid com hover/active
- `.active-category` — categoria selecionada na sidebar
- `.status-bar` — barra de status inferior
- `.restore-dialog` — estilização do diálogo
- Background transparente para integrar com tema do sistema

---

## Tecnologias

- **Linguagem**: Python 3.14+ (sistema atual: 3.14.3)
- **UI**: GTK 4.20+ (sistema atual: 4.20.3)
- **Adwaita**: libadwaita 1.8+ (sistema atual: 1.8.4) — suporta Adw.Dialog, Adw.AlertDialog, Adw.Breakpoint, Adw.NavigationSplitView
- **Bindings**: PyGObject 3.54+ (sistema atual: 3.54.5)
- **Flatpak**: 1.16+ (sistema atual: 1.16.3)
- **i18n**: gettext 1.0+
- **GObject Introspection**: 1.86+
- **Python Cairo**: 1.29+
- **Filesystem**: pathlib + shutil
- **Processos**: subprocess (lista, sem shell=True)
- **Async**: threading.Thread + GLib.idle_add para operações de IO
- **Build**: PKGBUILD (Arch/Manjaro/BigLinux)

### Features modernas disponíveis (libadwaita 1.8)
- `Adw.Dialog` (substitui Gtk.Dialog deprecated)
- `Adw.AlertDialog` (confirmações destrutivas)
- `Adw.NavigationSplitView` (layout responsivo two-pane)
- `Adw.Breakpoint` (responsividade por tamanho)
- `Adw.StatusPage` (páginas de estado/vazio)
- `Adw.PreferencesGroup` / `Adw.ActionRow` (listas de configuração)
- `Adw.AboutDialog` (diálogo sobre moderno)
- `Adw.Clamp` (largura máxima de conteúdo)
- `Adw.Spinner` (indicador de progresso)
- `Adw.SwitchRow` (toggle row)
- `Adw.Banner` (avisos não-intrusivos no topo)

---

## Notas de Segurança

- Nunca usar `shell=True` em subprocess
- Validar que paths estão dentro de `$HOME` antes de remover
- Não seguir symlinks ao remover (usar `os.path.islink` para verificar)
- Log de operações em `~/.local/state/biglinux-config/operations.log`
- Portais XDG onde possível
- Suporte X11 e Wayland
