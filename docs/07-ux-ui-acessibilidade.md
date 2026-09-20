# 07 — UX/UI e Acessibilidade

> Documento de desenvolvimento. Não é necessário em runtime.

## Modal do aplicativo — nova hierarquia

Ao clicar num app, o modal agora separa claramente ações **não destrutivas** de
**destrutivas** (Etapa 8 da missão):

```
[ícone] Nome do app
Escolha como restaurar as configurações…

Paths que serão substituídos  (expander: N paths — tamanho)

Backup
[ Exportar… ]   [ Importar… ]

Restaurar
[ Padrão do BigLinux ]   (só se houver skel válido)
[ Padrão do programa ]
```

- **Exportar…** salva a config do app num `.tar.gz` (desabilitado se não há config).
- **Importar…** valida que o backup contém aquele app antes de restaurar; avisa se
  o arquivo for de outro programa ou inválido.
- Botões de Restaurar mantêm confirmação destrutiva.

## Backup antes de restaurar

A confirmação de restauração traz um checkbox **"Criar um backup das configurações
atuais antes de restaurar"** (recomendado, marcado por padrão). Se não houver
config, fica desabilitado.

## Cancelamento e progresso

- Reset agora tem **botão Cancelar** real (event + rollback). Export/Import já
  tinham cancelamento via fechar o diálogo; mantido.
- Progresso de export/import é reportado em **bytes processados / bytes totais**
  pelo backend.

## Erros compreensíveis

- Falta de espaço: mensagem explica quanto é necessário vs. disponível
  (`"Not enough free space: need ~X, have Y."`).
- Backup inválido / app ausente no backup: mensagens específicas em vez de
  traceback.

## Acessibilidade (estado)

- `utils.set_label` define nomes acessíveis via `Gtk.AccessibleProperty.LABEL`
  em botões-chave (export, select-all).
- Toda navegação é por widgets GTK padrão (foco por Tab, Enter/Espaço, Escape
  fecha diálogos — `set_close_response`).
- Recomendações (docs/11): revisar ordem de foco no novo bloco Backup, adicionar
  `set_label` aos botões Exportar/Importar/Cancelar do reset, e testar com Orca.
- Não se depende só de cor: ações destrutivas usam texto + `DESTRUCTIVE`
  appearance; ícones sempre acompanham rótulo textual.

## Internacionalização

- Todas as novas strings passam por `_()`/`ngettext`. A geração de POT/PO/MO/JSON
  é feita pela CI (`big-auto-translator`); não editar `.po` à mão.
