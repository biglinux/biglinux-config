# 08 — Plano de testes

> Documento de desenvolvimento. Não é necessário em runtime.

## Infraestrutura

- `pytest`, HOME artificial via `TemporaryDirectory` + `monkeypatch` de `$HOME` e
  `os.path.expanduser` (`tests/conftest.py`). **Nenhum teste toca a config real.**
- `APP_ROOT` adicionado ao `sys.path` para importar `backend/`, `data/`.

## Suites

| Arquivo | Cobre |
|---|---|
| `test_reproduce_bugs.py` | Reprodução dos bugs originais (P2, C1, C3, C4, C5) — marcados `xfail(strict)` após correção |
| `test_backup.py` | round-trip (arquivos, dirs, unicode, espaços, permissões, dir vazio, symlink); cache on/off; manifesto primeiro; export atômico (cancel/erro preservam backup e não deixam `.part`); verify (truncamento, adulteração de checksum); import transacional + rollback; cancelamento; seleção parcial; segurança (traversal, path absoluto, symlink escape); leitura v1; guarda de espaço em disco |
| `test_reset.py` | program default; skel restore; **recusa de skel estrutural** (prova C1 corrigido); `has_skel` seguro; skel fora do root; rollback; backup-before-reset; matching de processo preciso + kill (processo filho real) |
| `test_registry.py` | ids únicos, entradas bem formadas, paths sob `~`, skel sob `/etc/skel` e nunca estrutural, sem entrada morta, favoritos válidos |

## Matriz da missão × cobertura

- Backup: arquivo simples ✓, diretório ✓, dir vazio ✓, árvore ✓, muitos arquivos
  ✓ (bench), unicode ✓, espaços ✓, symlink ✓, cancelamento ✓, sem espaço ✓.
- Import: válido ✓, inválido ✓, gzip truncado ✓, manifesto ausente/ inválido ✓,
  versão desconhecida ✓ (via versão fora de SUPPORTED), traversal ✓, path absoluto
  ✓, symlink malicioso ✓, seleção parcial ✓, cancelamento ✓, rollback ✓, v1 ✓.
- Reset: program default ✓, BigLinux default ✓, skel inexistente ✓, config
  inexistente ✓, app aberto ✓ (get_running_pids), path estrutural ✓.
- Registry: categoria válida ✓, app_id único ✓, paths válidos ✓, skel seguro ✓.

## Round-trip e interrupção

- Round-trip A→export→B→import→A validado no backend (LibreOffice-style em
  `scratchpad/bench.py`; genérico em `test_backup`).
- Interrupção: falha simulada no swap (`test_import_rollback_on_failure`) e no skel
  copy (`test_reset_rollback_on_skel_failure`) provam que a config anterior
  permanece utilizável.

## Execução

```bash
cd <repo>
python3 -m pytest tests/ -q
```
