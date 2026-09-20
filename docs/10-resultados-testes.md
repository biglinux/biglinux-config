# 10 — Resultados dos testes

> Documento de desenvolvimento. Não é necessário em runtime.

## Suite automatizada

```
python3 -m pytest tests/ -q
34 passed, 5 xfailed in ~0.56s
```

- **34 passam** (comportamento correto).
- **5 xfailed (strict)** = as reproduções dos bugs originais, que agora **não**
  reproduzem (bugs corrigidos). Se um bug regredir, o xfail vira "xpass" e a CI
  falha — funcionam como sentinelas de regressão.
- 39 itens de teste coletados no total.

## Smoke test da aplicação real

`scratchpad/smoke.py` sobe `BigConfigApp`, ativa a janela, executa o carregamento
assíncrono de apps e sai (auto-quit em 2,5 s):

```
APP EXIT CODE: 0
```

Sem traceback. Único aviso é ambiental (`gtk-application-prefer-dark-theme`,
originado do GtkSettings do sistema, não do app).

## Round-trip real (LibreOffice-style)

`scratchpad/bench.py`:
```
ROUND-TRIP LibreOffice-style: OK (A restored after mutation to B)
```
Criou config A (registrymodifications.xcu + autotext), exportou, mutou para B,
importou A, confirmou que A voltou byte a byte e que os diretórios reapareceram.

## Benchmarks

Ver docs/05. Destaque: leitura de manifesto 127 ms → 0,21 ms (~600×).

## Compilação / import

`python3 -m py_compile` em todos os `.py`: OK.
Import headless de `backend/*` e `ui/*`: OK.

## Cobertura por categoria da missão

Ver a matriz em docs/08 — backup, import, reset e registry cobertos, incluindo
casos maliciosos, cancelamento e rollback.
