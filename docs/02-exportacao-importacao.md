# 02 — Exportação e Importação

> Documento de desenvolvimento. Não é necessário em runtime.

## Problemas encontrados na versão original (provados por teste)

| ID | Problema | Prova |
|---|---|---|
| P1 | `full_directory=True/False` produziam o **mesmo** arquivo (tar.add já é recursivo) e o modo False fazia um `os.walk` extra só p/ tamanho (I/O dobrado) | `test_reproduce_bugs::test_p1…` |
| P2 | Manifesto no **fim** do `.tar.gz` → leitura do manifesto varria o arquivo inteiro; import lia o gz duas vezes | `test_p2…` |
| P3 | Import O(arquivos × paths) | leitura de código |
| C3 | Import **não transacional**: `rmtree` do diretório alvo antes de extrair; falha/cancelamento deixava HOME destruído sem rollback | `test_c3…` |
| C4 | Export **não atômico**: gravava direto no arquivo final; falha destruía backup válido preexistente | `test_c4…` |
| C5 | Symlinks/dirs-vazios perdidos no round-trip | `test_c5…` |

## Arquitetura final

### Exportação (atômica)
1. Pré-walk único: coleta inventário (path/type/size/mode/mtime/link) e `total_size`
   (só `lstat`, sem ler conteúdo). Sem I/O duplicado.
2. Grava em `arquivo.tar.gz.part`.
3. Manifesto **primeiro**.
4. Arquivos adicionados via streaming; BLAKE2b calculado **durante a mesma leitura**
   (wrapper `_HashingReader`) — sem segunda leitura.
5. Checksums no fim.
6. `flush` + `os.fsync` + `os.replace` atômico para o nome final.
7. Cancelamento/erro: remove só o `.part`; **backup anterior intacto**.

`full_directory` agora tem efeito real: `False` (padrão) exclui diretórios de
cache (`Cache`, `CachedData`, `Code Cache`, `GPUCache`, …); `True` inclui tudo.

### Importação (transacional)
1. Lê manifesto (O(1), primeiro membro). Valida formato/versão (1 ou 2).
2. Resolve os *roots* dos apps selecionados (matching por prefixo, sem O(n×m)).
3. Verifica espaço em disco (`shutil.disk_usage`, ~1.15× `total_size`).
4. Extrai para *staging* oculto no **mesmo filesystem** que o HOME
   (`~/.biglinux-config-restore-<pid>-<ts>`), sanitizando cada membro
   (`paths.safe_extract_target` + rejeição de symlink que escapa) e conferindo
   checksum ao escrever.
5. **Swap atômico** por root: `rename(live → aside)` (gravado antes), `rename(staged → live)`.
6. Qualquer falha → **rollback** completo (restaura os `aside`), staging removido.
7. Sucesso → descarta `aside` e staging. Estados: SUCCESS / CANCELLED / ROLLED_BACK / FAILED.

## Compatibilidade
- Lê backups **v1** (`read_backup_manifest` normaliza `apps/paths` → `applications/roots`)
  e importa com o mesmo caminho transacional. Validado em `test_backup::test_reads_v1_archive`.

## Exportação/Importação individual (modal)
- `get_app_backup_name(app_id)` → `biglinux-config-<app>-<ts>.tar.gz`.
- No modal do app: botões Exportar/Importar operam sobre um único `AppEntry`.
