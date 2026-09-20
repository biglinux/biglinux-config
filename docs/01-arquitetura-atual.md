# 01 — Arquitetura atual

> Documento de desenvolvimento. A aplicação **não** depende deste arquivo em runtime.

## Camadas

```
main.py  ──►  ui/application.py (Adw.Application + janela)
                 │
   ┌─────────────┼──────────────────────────────┐
   │             │                               │
 ui/            backend/                         data/
 app_grid       app_detector    (detecção nativa) app_registry (135 AppEntry)
 category_side  flatpak_detector(detecção flatpak)
 backup_dialog  backup_manager  (export/import) ◄── paths (NOVO: validação central)
 restore_dialog reset_manager   (reset/skel)    ◄── paths
 welcome/about  paths           (NOVO)
 utils (_ i18n)
```

## Fluxo

1. `BigConfigApp.do_activate` cria a janela e dispara `_load_apps_async`
   (thread) → `get_installed_apps()` + `get_installed_flatpaks()` → volta à main
   thread via `GLib.idle_add`.
2. A sidebar lista categorias; o grid mostra os apps instalados da categoria.
3. Clicar num app abre o **modal de restauração** (`restore_dialog`) com:
   - Exportar / Importar (config individual) — **NOVO**
   - Restaurar padrão do BigLinux (só se `has_skel`)
   - Restaurar padrão do programa
4. Menu → Exportar/Importar configurações (multi-app) → `backup_dialog`.

## Threading (modelo confirmado)

- Todo trabalho de I/O roda em `threading.Thread(daemon=True)`.
- O retorno à UI é sempre via `GLib.idle_add`; nenhum widget GTK é tocado fora
  da main thread (auditado nos 8 arquivos de UI).
- Export/Import usam `threading.Event` como `cancel_event`; **o reset agora
  também** (antes não era cancelável).

## Backend — responsabilidades

| Módulo | Papel |
|---|---|
| `paths.py` (novo) | validação central de caminhos (HOME, symlink, traversal, dirs estruturais) |
| `backup_manager.py` | export atômico + import transacional + verificação de integridade |
| `reset_manager.py` | reset transacional program/BigLinux, backup prévio, matching preciso de processos |
| `app_detector.py` | apps nativos instalados, nome localizado via `.desktop`, favoritos por MIME |
| `flatpak_detector.py` | apps Flatpak com `~/.var/app/<id>/{config,data}` (cache excluído) |

## Formato de backup (v2)

- `biglinux-backup-manifest.json` — **primeiro** membro (metadados + apps + roots).
- Membros de arquivos (dirs, files, symlinks), modos preservados.
- `biglinux-backup-checksums.json` — **último** membro (BLAKE2b por arquivo).
- Compatível com leitura de backups **v1** (manifesto no fim, chaves `apps/paths`).

## Empacotamento

- Launcher: `usr/bin/biglinux-config` → `python3 /usr/share/biglinux/biglinux-config/main.py`.
- `.desktop`: `usr/share/applications/big-config.desktop` (Icon=restore-settings).
- PKGBUILD: depends python, python-gobject, gtk4, libadwaita, procps-ng;
  optdepends flatpak. (procps-ng não é mais estritamente necessário — o
  `pgrep`/`kill` via subprocess foi substituído por `/proc` + `os.kill`.)
