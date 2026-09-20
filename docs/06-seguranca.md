# 06 — Segurança

> Documento de desenvolvimento. Não é necessário em runtime.

## Modelo de ameaça

Um backup importado é **entrada não confiável**. Nunca se confia no manifesto nem
nos nomes dos membros do TAR.

## Proteções contra TAR malicioso (implementadas + testadas)

| Ameaça | Defesa | Teste |
|---|---|---|
| Path traversal (`../`) | `paths.safe_extract_target` rejeita `..` e resolve realpath sob staging | `test_backup::test_reject_path_traversal` |
| Path absoluto (`/etc/...`) | membros com `/` inicial rejeitados | `test_reject_absolute_path` |
| Symlink que escapa do HOME | `_symlink_is_safe` resolve o alvo no destino final; rejeita fora do HOME | `test_reject_symlink_escape` |
| Device nodes / FIFO / socket | tipos não suportados são ignorados (export e import) | classificação em `_classify`/extract |
| Hardlink traversal | só `isfile/isdir/issym` são materializados; hardlinks não são seguidos | leitura de código |
| Manifesto/versão inválidos | `read_backup_manifest` valida formato e versão suportada (1,2) antes de tocar o HOME | `import_backup` early-return |
| gzip/tar truncado ou corrompido | exceções de `tarfile` capturadas; `verify_backup` detecta | `test_verify_detects_truncation` |
| Hash incorreto (adulteração) | BLAKE2b por arquivo conferido na extração e em `verify_backup` | `test_verify_detects_checksum_tamper` |

Extração ocorre **primeiro em staging** dentro do HOME; nada é escrito no destino
final antes da validação completa. Falha ⇒ nada aplicado (ou rollback total).

## Caminhos (reset e export)

- `paths.resolve_under_home` garante que só se opera dentro do `$HOME` real.
- **Diretórios estruturais** (`~`, `~/.config`, `~/.local`, `~/.local/share`,
  `~/.local/state`, `~/.cache`, `~/.var`, `~/.var/app`) nunca podem ser removidos
  ou substituídos como unidade (bloqueia a classe de bug C1/C2).
- Skel só é aceito de dentro de `/etc/skel` (`SKEL_ROOT`).

## Processos

- Sem `pgrep -f` (casamento amplo). Matching por `/proc/<pid>/exe` + `comm`,
  restrito ao uid do usuário; zombies ignorados. Elimina o risco de matar
  processos alheios.

## Privacidade

- Dados sensíveis por natureza (Firefox `~/.mozilla`, `~/.bash_history`,
  `~/.zsh_history`, perfis de navegadores) podem entrar no backup. Recomendação
  (docs/11): exibir aviso "este backup pode conter informações privadas; guarde-o
  em local seguro" no diálogo de export. Cache é excluído por padrão, o que já
  reduz vazamento incidental.
- **Logs nunca registram** conteúdo de arquivo, senha, token, cookie ou segredo —
  apenas caminhos, contagens, tamanhos e resultado.

## Shell / comandos

- Sem `shell=True`, sem `eval`, sem `rm -rf` via shell, sem `sudo`, sem `chmod 777`.
- `_logout_session` usa listas de argumentos fixas por DE (sem interpolação).
