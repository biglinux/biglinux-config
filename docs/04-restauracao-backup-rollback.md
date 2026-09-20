# 04 — Restauração, backup prévio e rollback

> Documento de desenvolvimento. Não é necessário em runtime.

## Problema crítico corrigido (C1)

`de-kde.skel_paths` era `['/etc/skel/.config', '/etc/skel/.local']`. O
`reset_manager` computava `dest = ~/relpath(skel,/etc/skel)` → `~/.config` e
`~/.local`, fazia `shutil.rmtree(dest)` e copiava o skel por cima → **apagava a
configuração de TODOS os aplicativos do usuário**. Provado em
`test_reproduce_bugs::test_c1_biglinux_default_wipes_whole_config`.

## Defesas implementadas

1. **`backend/paths.py`** centraliza validação:
   - `resolve_under_home`, `is_within`, `safe_removable`, `safe_destination`,
     `safe_extract_target`.
   - Conjunto de **diretórios estruturais** (`~`, `~/.config`, `~/.local`,
     `~/.local/share`, `~/.local/state`, `~/.cache`, `~/.var`, `~/.var/app`) que
     **nunca** podem ser removidos ou substituídos como unidade.
2. **Registro corrigido**: `de-kde` agora lista arquivos KDE específicos do skel.
3. **`has_skel` seguro**: só reporta `True` quando o skel existe **e** mapeia para
   destino não estrutural — a opção "Padrão do BigLinux" nunca aparece se não
   houver o que restaurar de verdade (regra da Etapa 10).

## Reset transacional (`reset_app`)

Fluxo:
1. (Opcional) **Backup de segurança** antes de destruir (`backup_first=True`),
   salvo em `~/.local/state/biglinux-config/pre-reset-backups/`.
2. Planeja o skel restore validando cada destino (recusa estrutural/escapando).
3. Move cada `config_path` para um *aside* (`~/.biglinux-config-reset-<pid>-<ts>`)
   via `rename` (não deleta ainda).
4. Copia o skel para o destino (modo BigLinux).
5. Sucesso → descarta o *aside*. Falha/cancelamento → **rollback**: remove skel
   copiado e restaura os originais do *aside*.

Estados: `SUCCESS`, `PARTIAL`, `FAILED`, `CANCELLED`, `ROLLED_BACK`.
Provado em `tests/test_reset.py` (rollback, recusa estrutural, backup prévio).

## Processos (matar com precisão)

`get_running_pids` varre `/proc/<pid>/exe` (realpath == binário) e faz *fallback*
para `comm` exato; considera só processos do usuário atual e **ignora zombies**.
Substitui o antigo `pgrep -f <nome>` (casava linha de comando inteira e podia
matar processos não relacionados). `kill_app`: SIGTERM → espera → SIGKILL nos
sobreviventes, com `os.kill` (sem `subprocess sleep`).

## UI de restauração

- Confirmação agora traz **"Criar um backup das configurações atuais antes de
  restaurar"** (marcado por padrão; desabilitado se não há config).
- Diálogo de progresso do reset tem **botão Cancelar** funcional (antes o reset
  não era cancelável).
- Diálogo de sucesso mostra o caminho do backup de segurança criado.
- Cancelamento não mostra erro (o estado é revertido silenciosamente).

## Padrão do programa vs BigLinux

- **Programa**: remove os `config_paths` (movidos para *aside* e descartados no
  sucesso) → o app recria seu padrão original.
- **BigLinux**: idem + copia os arquivos de `/etc/skel` correspondentes.
- Se o modo BigLinux não tem skel válido, comporta-se como "programa" e registra
  isso no log (nunca informa "sucesso" tendo restaurado nada indevidamente).
