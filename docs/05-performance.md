# 05 — Performance (medições reais)

> Documento de desenvolvimento. Não é necessário em runtime.
> Máquina: Python 3.14.7, btrfs, 46 GiB RAM. Números reais (não inventados).

## Leitura do manifesto — impacto do P2 (manifesto primeiro vs último)

Arquivo de teste: `.tar.gz` com 1000 arquivos, ~117 MB.

| Layout | Tempo de `read_backup_manifest` |
|---|---|
| Manifesto no **fim** (comportamento antigo / v1) | **127,14 ms** |
| Manifesto no **início** (novo, v2) | **0,21 ms** |

→ **~600× mais rápido**. Como a importação lia o manifesto ao menos duas vezes
(abrir diálogo + importar), o ganho percebido é multiplicado. Em arquivos maiores
a diferença cresce proporcionalmente ao tamanho comprimido.

## Export / verify / import (fim a fim, backend)

| Cenário | Export | Tamanho | Verify | Import |
|---|---|---|---|---|
| 100 arquivos / ~10 MB | 0,212 s | 9,79 MB | 0,048 s | 0,056 s |
| 1000 arquivos / ~100 MB | 2,253 s | 97,91 MB | 0,469 s | 0,561 s |
| 3000 arquivos (conteúdo repetido) | 0,757 s | 1,34 MB | 0,569 s | 0,788 s |

Observações:
- Export inclui hashing BLAKE2b **na mesma leitura** (sem 2ª passagem).
- Import é transacional (staging + verificação de checksum + swap atômico) e ainda
  assim fica na casa de sub-segundo para 100 MB.

## Ganhos estruturais (além dos números)

- **I/O de tamanho eliminado**: o modo "não-full" antigo fazia um `os.walk`
  adicional só para somar tamanho, além do `tar.add` recursivo. Agora há um único
  pré-walk (`lstat`) + uma leitura por arquivo.
- **Import O(n) em vez de O(arquivos × paths)**: matching por prefixo de *root*.
- **Cache excluído por padrão**: backups menores e mais rápidos (navegadores e
  Electron apps guardam centenas de MB em `Cache`/`GPUCache`).

## UI / thread

- Detecção de apps roda em thread; `app_detector` cacheia o mapa de `.desktop`
  (`_build_desktop_map`) e nomes localizados (`_name_cache`) por sessão.
- Nenhuma operação de disco roda na main loop; retorno sempre via `GLib.idle_add`.

## Método

Scripts: `scratchpad/bench.py` (round-trip + fim a fim) e
`scratchpad/manifest_bench.py` (leitura de manifesto). Reexecutáveis a qualquer
momento; `min` de 3 medições para a leitura de manifesto.
