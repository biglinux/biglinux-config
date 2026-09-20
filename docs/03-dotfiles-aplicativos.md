# 03 — Dotfiles e aplicativos

> Documento de desenvolvimento. Não é necessário em runtime.

## Registro

- 136 → **135** entradas (removido `gnome-tweaks`: só usa dconf, nada em dotfiles).
- Sem app_id duplicado; todas as categorias válidas (validado em `tests/test_registry.py`).
- `config_paths` sempre sob `~`; `skel_paths` sempre sob `/etc/skel` e **nunca**
  estruturais (`~/.config`, `~/.local`…), garantido por teste.

## Auditoria de `/etc/skel` (máquina de referência)

`/etc/skel` contém principalmente arquivos KDE/Plasma, LibreOffice, GIMP, VLC,
qBittorrent, htop, bash/zsh, etc. Ruídos presentes: `.bashrc.bak`, `.bashrc.pacnew`.

### Tabela — apps instalados nesta máquina

| App | Instalado | Config existe | Skel registrado | Skel utilizável (`has_skel`) |
|---|---|---|---|---|
| audacity | ✓ | sim | - | não |
| bash | ✓ | sim | sim | sim |
| brave | ✓ | sim | - | não |
| btop | ✓ | sim | - | não |
| de-kde | ✓ | sim | sim | **sim (corrigido)** |
| dolphin | ✓ | sim | sim | sim |
| firefox | ✓ | sim | sim | **não** (skel `/etc/skel/.mozilla` ausente) |
| gimp | ✓ | sim | sim | sim |
| google-chrome | ✓ | sim | - | não |
| gwenview | ✓ | sim | sim | sim |
| htop | ✓ | sim | sim | sim |
| kate | ✓ | sim | sim | sim |
| konsole | ✓ | sim | sim | sim |
| kvantum | ✓ | sim | - | não |
| libreoffice | ✓ | sim | sim | sim |
| lutris | ✓ | sim | - | não |
| mpv | ✓ | sim | sim | não (skel ausente) |
| mystiq | ✓ | sim | sim | sim |
| obs-studio | ✓ | sim | - | não |
| okular | ✓ | sim | sim | sim |
| qbittorrent | ✓ | sim | sim | sim |
| spectacle | ✓ | sim | sim | sim |
| steam | ✓ | sim | - | não |
| vim | ✓ | não | - | não |
| virt-manager | ✓ | não | - | não |
| vlc | ✓ | sim | sim | sim |
| vscode / -insiders | ✓ | sim | - | não |
| zen-browser | ✓ | sim | - | não |
| zsh | ✓ | sim | sim | sim |

Observação importante: `has_skel` agora só retorna `sim` quando o skel **existe**
e mapeia para um destino seguro. Por isso Firefox/mpv (skel registrado mas ausente
em `/etc/skel`) corretamente **não** exibem "Restaurar padrão do BigLinux".

## Aplicativos Flatpak instalados (23) — agora com config/data separados de cache

Krita, Inkscape, Discord, Telegram, OBS, VLC, Bottles, Heroic, RetroDECK,
ProtonUp-Qt, RustDesk, Stremio, Zed, Arduino IDE, Mission Center, OpenRGB,
qpwgraph, TigerVNC, Alpaca, geforcenow, Sober, IRPF2026, Chrome.
O detector passou a registrar `~/.var/app/<id>/{config,data}` e **excluir** `cache/`.

## Candidatos a suporte adicional (não adicionados sem validação confiável)

Detectáveis por dotfile e presentes na máquina/skel — poderiam ser adicionados
com config/skel confiáveis: `strawberry`, `clementine`, `smplayer` (skel existe),
`corectrl`, `jamesdsp`, `fcitx5`. Não foram adicionados agora para manter o escopo
seguro; recomendação registrada em docs/11.

## dconf / GSettings (implementado)

Suporte via `backend/dconf_manager.py`, sempre **por namespace específico**
(`is_valid_namespace` recusa `/` e raízes de um só segmento — nunca dump/reset da
base inteira). Campo `dconf_paths` no `AppEntry`.

- **Export**: `dconf dump <ns>` de cada namespace vira um membro
  `.biglinux-dconf/<app_id>/<i>.ini` no `.tar.gz`, com checksum e registro no
  manifesto (`dconf`).
- **Import**: fase transacional após o swap de arquivos — captura o estado atual,
  faz `dconf load`, e em falha reverte (arquivos **e** dconf).
- **Reset**: `dconf reset -f <ns>` (program/BigLinux default), com rollback do
  dump capturado.
- Entradas: `gnome-tweaks` (namespaces do GNOME desktop/mutter) reintroduzido;
  `de-gnome` com `/org/gnome/{shell,desktop,mutter}/`.
- `has_config` passa a considerar conteúdo dconf, então esses apps aparecem como
  restauráveis mesmo sem dotfiles.
