# 11 — Relatório final

> Documento de desenvolvimento. **A aplicação não depende deste arquivo em runtime.**

## Resumo

Auditoria completa e reengenharia do núcleo de segurança de dados do BigLinux
Config (Restore Settings). A prioridade absoluta — **não perder dados do usuário e
tornar Exportar/Importar/Restaurar confiáveis** — foi atendida com:

- Correção de um bug **catastrófico** que apagava todo o `~/.config` e `~/.local`.
- Reescrita de `backup_manager` (export atômico, import transacional com rollback,
  integridade por checksum, proteção contra TAR malicioso).
- Reescrita de `reset_manager` (reset transacional, backup prévio, término preciso
  de processos, cancelamento).
- Melhoria de UX (backup-before-reset, export/import por app no modal, cancelar).
- 36 testes automatizados + 5 sentinelas de regressão (xfail) + benchmarks reais.
- Documentação de desenvolvimento em `docs/`.

Nenhuma configuração real do usuário foi tocada durante o trabalho (testes em HOME
temporário).

## Bugs encontrados

### Crítico
- **C1** — `de-kde` "Padrão do BigLinux" apagava `~/.config` e `~/.local` inteiros
  (skel apontava para diretórios estruturais + `rmtree` do destino). Perda total.
- **C2** — Restauração de skel podia escapar do HOME (dest derivado sem validação).
- **C3** — Importação não transacional: `rmtree` do alvo antes de extrair; falha ou
  cancelamento deixava o HOME destruído sem rollback.
- **C4** — Exportação não atômica: falha destruía um backup válido preexistente.

### Alto
- **C5** — Round-trip perdia symlinks (silenciosamente ignorados na extração).
- **P4** — `kill_app` usava `pgrep -f`: podia matar processos não relacionados.
- Sem validação de integridade (checksum) nem detecção de corrupção.
- Sem verificação de espaço em disco.

### Médio
- **P1** — `full_directory` era no-op; modo "não-full" fazia I/O duplicado.
- **P2** — Manifesto no fim do TAR: leitura O(arquivo inteiro), dobrada na import.
- **P3** — Import O(arquivos × paths).
- Flatpak incluía cache como se fosse configuração.
- Sem "backup antes de restaurar"; reset não cancelável.

### Baixo
- `gnome-tweaks` sem `config_paths` (entrada morta).
- Aviso de privacidade ausente no export.
- `except Exception` amplo repassando mensagem crua.

## Bugs corrigidos (arquivo + descrição)

| Arquivo | Correção |
|---|---|
| `backend/paths.py` (novo) | Validação central: HOME, symlink, traversal, dirs estruturais |
| `data/app_registry.py` | `de-kde` skel → arquivos KDE específicos (C1); remoção de `gnome-tweaks` |
| `backend/reset_manager.py` | Reset transacional + rollback (C2/C3-classe); skel seguro; `has_skel` seguro; kill preciso via `/proc` (P4); backup prévio; cancel; estados |
| `backend/backup_manager.py` | Export atômico `.part`+fsync+rename (C4); manifesto primeiro (P2); import transacional + rollback (C3); symlinks (C5); checksums BLAKE2b; proteção TAR malicioso; guarda de disco; matching O(n) (P3); `full_directory`=incluir cache (P1); v2 + leitura v1; resiliência a arquivo sumido |
| `backend/flatpak_detector.py` | `config/`+`data/`, exclui `cache/` |
| `ui/restore_dialog.py` | Backup-before-reset; cancel; seção Backup (export/import por app); nota de backup no sucesso |
| `ui/backup_dialog.py` | Export/import individuais; rótulo do switch de cache |

## Exportação — arquitetura final e benchmarks

Atômica (`.part` → fsync → `os.replace`), manifesto primeiro, checksums BLAKE2b
calculados na mesma leitura, cache excluído por padrão. 100 MB/1000 arquivos:
export 2,25 s, verify 0,47 s. Ver docs/05.

## Importação — arquitetura final e proteção de dados

Transacional: valida → verifica espaço → extrai para staging no mesmo filesystem →
verifica checksums e sanitiza cada membro → swap atômico por root → rollback total
em qualquer falha. Estados SUCCESS/CANCELLED/ROLLED_BACK/FAILED. Lê v1 e v2.
Leitura de manifesto ~600× mais rápida (127 ms → 0,21 ms em 117 MB).

## Restauração — Program Default e BigLinux Default

Reset transacional com move-aside + rollback; backup de segurança opcional antes
de destruir; término de processo preciso; "Padrão do BigLinux" só aparece quando
há skel válido e seguro (`has_skel`).

## Aplicativos

135 entradas auditadas (era 136; `gnome-tweaks` removido). `de-kde` corrigido.
Flatpak com config/data e sem cache. Candidatos futuros mapeados em docs/03.

## Dotfiles

Tabela completa em docs/03. `de-kde` skel reescrito para arquivos KDE específicos;
Firefox/mpv corretamente deixam de oferecer "Padrão do BigLinux" (skel ausente).

## Segurança

Proteções testadas contra path traversal, path absoluto, symlink escape, device
nodes, corrupção, checksum adulterado, manifesto/versão inválidos. Backup tratado
como entrada não confiável; extração sempre em staging antes de aplicar. Detalhes
em docs/06.

## Performance

Antes/depois reais em docs/05 (manifesto ~600×; I/O de tamanho eliminado; import
O(n); cache excluído). Sem regressão.

## UX/UI

Modal com hierarquia Backup (não destrutivo) × Restaurar (destrutivo);
backup-before-reset recomendado; cancelamento de reset; mensagens de erro claras
(espaço em disco, backup inválido, app ausente no backup).

## Testes

36 passam + 5 xfailed (sentinelas). Smoke test da app real: exit 0 sem traceback.
Round-trip LibreOffice-style validado. Ver docs/08 e docs/10.

## Pendências (honestas)

1. ~~Aviso de privacidade no export~~ — **CONCLUÍDO**. Campo `sensitive` no
   `AppEntry` + helper `is_sensitive` (browsers/communication + 7 apps explícitos);
   `Adw.Banner` no diálogo de export, ícone de aviso por linha e confirmação na
   exportação individual de app sensível. Ver docs/06.
2. ~~Suporte a dconf/GSettings~~ — **CONCLUÍDO**. `backend/dconf_manager.py`
   (dump/load/reset por namespace, nunca a base inteira); campo `dconf_paths` no
   `AppEntry`; integrado a export (membros `.biglinux-dconf/…` com checksum),
   import (fase transacional com rollback) e reset (com rollback). gnome-tweaks
   reintroduzido e de-gnome com namespaces `/org/gnome/{shell,desktop,mutter}/`.
   8 testes usando namespace de rascunho isolado. Ver docs/03.
3. **Criptografia de backup** — não implementada (evita dependência pesada/formato
   incompatível). Documentado como decisão consciente.
4. **Acessibilidade** — botões de ação do modal são `Adw.ActionRow` (nome
   acessível pelo título); botão ícone "abrir no gerenciador" recebeu `set_label`;
   menu de favoritos acessível por teclado (Menu / Shift+F10). Pendente ainda:
   teste com leitor de tela (Orca).
5. ~~PKGBUILD `procps-ng`~~ — **CONCLUÍDO**. Removido de `depends` (kill via
   `/proc`+`os.kill`); adicionado `dconf` em `optdepends`.
6. **Testes de UI automatizados** — a UI foi validada por compile + import + smoke
   test + revisão; não há testes GTK dirigidos por evento.
7. **Benchmark de 1 GB** — não executado (evitar uso excessivo de disco); a
   arquitetura é linear e os cenários até 100 MB comprovam o comportamento.

## Confiança final

O objetivo — poder exportar antes de reinstalar e recuperar com segurança, e
restaurar padrões podendo voltar atrás — está atendido no núcleo: operações
atômicas, transacionais, com rollback, integridade verificada e proteção contra
entradas maliciosas, tudo coberto por testes.
