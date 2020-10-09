#!/usr/bin/env bash

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

windowID="$(xprop -root '\t$0' _NET_ACTIVE_WINDOW | cut -f 2)"

PROG=$(pidof kate)

if [ -n "$PROG" ]; then
	kdialog --attach="$windowID" --title $"Restaurar Configurações" \
--sorry $"Atenção! O programa está aberto!\nEle será fechado para que a restauração tenha efeito."
	RET="$?"
	[ "$RET" == "0" ] && kill -9 $PROG
fi

if [ "$1" = "1" ]; then
	rm -r ~/.local/share/kate
	rm -r ~/.local/share/kxmlgui5/kate
	rm -r ~/.local/share/kxmlgui5/katepart
	rm -r ~/.local/share/ktexteditor_snippets
	rm ~/.config/katevirc
	rm ~/.config/katemetainfos
	rm ~/.config/kateschemarc
	rm ~/.config/katesyntaxhighlightingrc
	rm ~/.config/katerc
	cp -r /etc/skel/.local/share/kate ~/.local/share/kate
	cp -r /etc/skel/.local/share/kxmlgui5/kate ~/.local/share/kxmlgui5/kate
else
	rm -r ~/.local/share/kate
	rm -r ~/.local/share/kxmlgui5/kate
	rm -r ~/.local/share/kxmlgui5/katepart
	rm -r ~/.local/share/ktexteditor_snippets
	rm ~/.config/katevirc
	rm ~/.config/katemetainfos
	rm ~/.config/kateschemarc
	rm ~/.config/katesyntaxhighlightingrc
	rm ~/.config/katerc
fi
kdialog --attach="$windowID" --title $"Restaurar Configurações" \
		--msgbox $"As configurações foram restauradas com sucesso!"
exit