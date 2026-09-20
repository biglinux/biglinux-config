# 07 — UX/UI e Acessibilidade

> Documento de desenvolvimento. Não é necessário em runtime.

## Modal do aplicativo — redesenho Adwaita moderno

O modal antigo empilhava rótulos soltos ("Backup"/"Restore"), *cards* grandes com
um botão "Restore" repetido em cada linha e a lista de paths expandida — o que
gerava rolagem vertical e hierarquia confusa. O redesenho usa o idioma Adwaita
padrão e compacto:

```
        ( ícone 72 )
         Nome do app
        N itens · 18,6 MB

╭─ Backup ────────────────────────────╮
│ 💾  Exportar configurações…       › │  Adw.ActionRow (ativável)
│ 📂  Importar configurações…       › │
╰─────────────────────────────────────╯
╭─ Restaurar padrões ─────────────────╮
│ ◆  Padrão do BigLinux             › │  (só se skel válido)
│ ↺  Padrão do programa             › │  (ícone em vermelho — destrutivo)
╰─────────────────────────────────────╯
╭─────────────────────────────────────╮
│ ▸ Arquivos afetados   N itens · … │   Adw.ExpanderRow (recolhido)
╰─────────────────────────────────────╯
```

Princípios aplicados:
- **`Adw.PreferencesGroup`** com título para cada seção (Backup / Restaurar) — sem
  rótulos soltos nem CSS custom (as classes `.restore-*` foram removidas).
- **`Adw.ActionRow` ativável** com ícone + título + subtítulo + chevron
  (`go-next-symbolic`): cada ação vira uma linha limpa e autoexplicativa. O
  subtítulo esclarece o efeito de cada modo (o que o antigo *card* não fazia).
- **`Adw.Clamp`** (máx. 360 px) centraliza o conteúdo e dá largura confortável.
- Lista de paths recolhida por padrão num **`Adw.ExpanderRow`** — deixou de ser a
  causa da rolagem.
- `Adw.ScrolledWindow` com `propagate_natural_height` + `max_content_height`: a
  janela ajusta-se ao conteúdo (sem espaço morto) e só rola em telas pequenas.
- Estado vazio com **`Adw.StatusPage`**.
- Ação destrutiva (Padrão do programa) sinalizada por ícone com classe `error`
  (vermelho) **e** texto — nunca só por cor.

Comportamento preservado: Exportar (desabilitado se não há config), Importar
(valida que o backup contém o app), e Restaurar (confirmação destrutiva com opção
de backup prévio).

## Backup antes de restaurar

A confirmação de restauração traz um checkbox **"Criar um backup das configurações
atuais antes de restaurar"** (recomendado, marcado por padrão). Se não houver
config, fica desabilitado.

## Cancelamento e progresso

- Reset agora tem **botão Cancelar** real (event + rollback).
- Export e Import compartilham **um único componente de progresso**
  (`_build_progress_dialog`) com o mesmo idioma Adwaita: `Adw.Dialog` com header
  plano + botão **Cancelar**, spinner, barra determinada e legenda do item atual.
- A barra mostra **percentual + tamanhos reais** — ex.: `46% · 12,0 MB / 25,8 MB`
  (progresso por bytes). Antes o export exibia contadores de bytes crus como
  `5242881/104857600`; corrigido.
- Fechar o diálogo também cancela (o `cancel_event` é honrado pelo backend, que
  então reverte/limpa).

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

## Tela principal (grid)

- **Busca incremental**: ao entrar no modo de busca os cards são populados **uma
  vez**; cada tecla seguinte apenas re-filtra (`filter_by_text`) em vez de
  reconstruir todos os cards. Antes cada tecla refazia o grid inteiro.
- **Selo Nativo/Flatpak**: apps Flatpak ganham um emblema (`folder-flatpak`) no
  canto inferior direito do ícone.
- **Selo "Padrão BigLinux disponível"**: apps com skel válido (`has_skel`) ganham
  um emblema da marca (accent) no canto superior direito — some automaticamente
  quando não há skel (ex.: Chrome, mpv, Steam).
- **Tooltip rico**: nome + origem (Nativo/Flatpak) + "Padrão BigLinux disponível".
- **Hover amigável**: a barra de status mostra `Nome · Nativo/Flatpak · Padrão
  BigLinux disponível` em vez dos caminhos crus de configuração.
- Selos também expõem nome acessível (`set_label`).

## Favoritos editáveis

- Menu de contexto por **botão direito**, **long-press** (toque) e **teclado**
  (**Menu** ou **Shift+F10**) sobre o card em foco: um `Gtk.Popover` com
  **"Adicionar aos favoritos"** (estrela vazada) ou **"Remover dos favoritos"**
  (estrela cheia), conforme o estado atual. Cobre 100% de operação por teclado.
- Persistência em `~/.config/restore-settings/settings.json` via
  `backend/user_prefs.py` (chaves `favorites-added` / `favorites-removed`),
  com read-modify-write que preserva `show-welcome`.
- A lista de Favoritos = **(auto-detectados ∪ adicionados) − removidos**. Assim o
  usuário pode tanto fixar novos apps quanto ocultar favoritos automáticos.
- Ao esvaziar os favoritos, a categoria sai da sidebar; ao adicionar o primeiro,
  ela reaparece. O grid de Favoritos atualiza na hora.

## Internacionalização

- Todas as novas strings passam por `_()`/`ngettext`. A geração de POT/PO/MO/JSON
  é feita pela CI (`big-auto-translator`); não editar `.po` à mão.
