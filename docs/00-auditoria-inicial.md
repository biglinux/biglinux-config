# 00 — Auditoria Inicial (baseline)

> Documento de desenvolvimento. **A aplicação não depende deste arquivo em runtime.**

Data: 2026-09-19 · Auditor: engenharia (revisão completa)

## Ambiente da máquina de referência

| Item | Valor |
|---|---|
| Python | 3.14.7 |
| GTK | 4.22.4 |
| libadwaita (Adw) | 1.9.3 |
| PyGObject | 3.56.3 |
| Kernel | 7.2.5-x64v3-xanmod1 |
| Desktop / Sessão | KDE / Wayland |
| Flatpak | 1.18.2 |
| Filesystem do $HOME | btrfs |
| RAM | 46 GiB (37 GiB livres) |
| Disco $HOME | 932 G (325 G livres) |

## Checkout x instalação

- Checkout de desenvolvimento: `/home/ruscher/Documentos/Git/biglinux-config`
  (layout espelha o filesystem: `biglinux-config/usr/share/biglinux/biglinux-config/...`).
- Instalado: `/usr/share/biglinux/biglinux-config/`.
- **Todos os `.py` são byte-idênticos** entre checkout e instalação → posso trabalhar no checkout com segurança; o comportamento reflete o instalado.
- Divergência: a instalação **não** tem `__pycache__` acompanhando os fontes; o checkout tinha `.pyc` versionados anteriormente (removidos por commit `32d1a0a`).

## Inventário do código (linhas)

| Arquivo | Linhas |
|---|---|
| data/app_registry.py | 1337 |
| ui/backup_dialog.py | 958 |
| ui/restore_dialog.py | 727 |
| ui/application.py | 396 |
| backend/backup_manager.py | 382 |
| backend/reset_manager.py | 236 |
| ui/welcome_dialog.py | 228 |
| backend/app_detector.py | 221 |
| ui/app_grid.py | 200 |
| ui/category_sidebar.py | 136 |
| backend/flatpak_detector.py | 75 |
| ui/about_dialog.py | 48 |
| utils/__init__.py | 31 |
| **Total Python** | **~4998** |

## Registro (app_registry)

- 136 entradas, **sem app_id duplicado**, todas com categoria válida.
- 15 categorias.
- 25 entradas com `skel_paths`; 111 sem.
- 1 entrada com `config_paths` vazio: **`gnome-tweaks`** (não faz nada — usa dconf, não coberto).
- 7 entradas `is_de` (desktop environments).
- Nativos detectados nesta máquina: 32. Flatpaks instalados: 23.

## ACHADOS CRÍTICOS (perda de dados) — confirmados por leitura de código

### C1 — `de-kde` "Restaurar padrão do BigLinux" APAGA todo o `~/.config` e `~/.local`
`de-kde.skel_paths = ['/etc/skel/.config', '/etc/skel/.local']`.
Em `reset_manager.reset_app(BIGLINUX_DEFAULT)`:
`rel = relpath('/etc/skel/.config','/etc/skel') = '.config'` → `dest = ~/.config` →
`shutil.rmtree(dest)` e depois `copytree(skel, dest)`.
**Resultado: destrói a configuração de TODOS os aplicativos do usuário** (Firefox, VSCode, etc.)
e substitui por `/etc/skel/.config`. É o pior cenário possível para esta ferramenta.

### C2 — Restauração de skel pode escapar do HOME
`dest` é derivado de `relpath(skel_path, '/etc/skel')`. Se um `skel_path` não estiver
sob `/etc/skel`, o `relpath` produz `../...` e `dest = ~/../...` escreve **fora do HOME**.
Hoje todos os skel estão sob `/etc/skel`, mas não há validação central — regressão fácil.

### C3 — Importação NÃO é transacional (sem rollback)
`import_backup` remove o alvo existente (`rmtree`/`unlink`) e então extrai o novo conteúdo,
membro a membro. Se ocorrer erro, cancelamento ou desligamento no meio, o usuário fica com
**metade da config antiga e metade da nova**, sem forma de voltar. Cancelar (linha 286)
retorna após já ter sobrescrito arquivos.

### C4 — Exportação não é atômica
`export_backup` grava direto em `archive_path`. Se `archive_path` for um backup válido
existente e a operação falhar, o backup antigo é destruído (o `except` faz `os.unlink`).
Sem `.part` + `rename` atômico, sem `fsync`.

### C5 — Round-trip perde symlinks / dirs vazios / modos de diretório
No import só `member.isfile()` e `member.isdir()` são tratados; **symlinks, hardlinks e FIFOs
são silenciosamente ignorados** (nem restaurados, nem avisados). Modos e mtime de diretórios
não são restaurados. Perda de fidelidade no round-trip.

## ACHADOS DE PERFORMANCE / CORREÇÃO — a provar com testes

### P1 — `full_directory=True` e `False` produzem praticamente o MESMO resultado
Em `full_directory=False`, `tar.add(expanded, arcname=rel_path)` usa `recursive=True`
(default do tarfile) → adiciona a árvore inteira mesmo assim. A diferença de intenção
documentada não existe. Além disso, no modo False há um `os.walk` **adicional** só para
somar tamanho → **I/O duplicado**.

### P2 — Manifesto no fim do `.tar.gz` → leitura dupla
`read_backup_manifest` faz `tar.getmember(MANIFEST)`; como o manifesto é o último membro,
o tarfile precisa varrer todo o arquivo descomprimido para montar a lista até achá-lo.
A importação lê o gz uma vez para achar o manifesto e **de novo** para extrair.
→ Escrever manifesto **primeiro**.

### P3 — Importação O(arquivos × paths)
Para cada membro do TAR faz loop em `path_to_app` e em `allowed_paths` (`any(...startswith)`).
→ substituir por índice/estrutura de prefixos.

### P4 — `kill_app` usa `pgrep -f <nome>`
`-f` casa a linha de comando inteira; `process_name`/basename genérico ("code", "vlc")
pode matar processos não relacionados. `subprocess.run(["sleep","1"])` gera processo à toa.

### P5 — Flatpak inclui cache
`flatpak_detector` registra `~/.var/app/<id>` inteiro como config, incluindo `cache/`.
Cache não deve ir por padrão; `config/`, `data/` e `cache/` não são diferenciados.

## Outros

- `gnome-tweaks` com `config_paths=[]` deveria ser removido ou tratado (dconf).
- Privacidade: `firefox ~/.mozilla`, `bash ~/.bash_history`, `zsh ~/.zsh_history`,
  navegadores → contêm segredos/cookies/histórico; export não avisa.
- Sem checksums / verificação de integridade do backup.
- Sem verificação de espaço em disco antes de exportar/importar.
- `except Exception` amplo em backup/reset engole detalhes (mensagem crua repassada à UI).

## LibreOffice como caso de referência (disponível nesta máquina)
- `~/.config/libreoffice/4` existe (modo `drwx------`).
- `/etc/skel/.config/libreoffice/4` existe → os dois fluxos de restauração são testáveis.
