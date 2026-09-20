# 09 — Plano de implementação (executado)

> Documento de desenvolvimento. Não é necessário em runtime.

Ordem seguida (fases da missão):

1. **Descoberta** — mapa de arquitetura, ambiente, registro, `/etc/skel`,
   apps instalados (docs/00, docs/01).
2. **Reproduzir** — `tests/test_reproduce_bugs.py` provando P1/P2/C1/C3/C4/C5.
3. **Segurança/integridade** — `backend/paths.py` (validação central); correção
   do registro `de-kde`; `has_skel` seguro.
4. **Export/Import** — reescrita de `backend/backup_manager.py`
   (atômico, manifesto-primeiro, checksums, transacional com rollback, v2 + leitura v1).
5. **Restauração** — reescrita de `backend/reset_manager.py` (transacional,
   backup prévio, matching de processo preciso, cancel, estados).
6. **Registry** — remoção de `gnome-tweaks`; flatpak config/data sem cache.
7. **UX/UI** — backup-before-reset + cancel no reset; export/import individuais no
   modal; rótulo do switch de cache; mensagens de erro claras.
8. **Performance** — benchmarks reais (docs/05).
9. **Testes** — `test_backup.py`, `test_reset.py`, `test_registry.py`.
10. **Empacotamento** — revisão do PKGBUILD, launcher, `.desktop`, smoke test.
11. **Documentação** — docs/00–11.

## Arquivos alterados/criados

Criados:
- `backend/paths.py`
- `tests/conftest.py`, `tests/test_reproduce_bugs.py`, `tests/test_backup.py`,
  `tests/test_reset.py`, `tests/test_registry.py`
- `docs/00`–`docs/11`

Reescritos:
- `backend/backup_manager.py`, `backend/reset_manager.py`

Alterados:
- `backend/flatpak_detector.py` (config/data, exclui cache)
- `data/app_registry.py` (de-kde skel seguro; remoção de gnome-tweaks)
- `ui/restore_dialog.py` (backup-before-reset, cancel, seção Backup export/import,
  nota do backup no sucesso)
- `ui/backup_dialog.py` (single export/import; rótulo do switch de cache;
  imports)

## Compatibilidade preservada

- Assinaturas públicas mantidas (parâmetros novos são opcionais).
- `BackupResult`/`RestoreFromBackupResult` mantêm campos usados pela UI; novos
  campos têm default.
- Backups v1 continuam importáveis.
