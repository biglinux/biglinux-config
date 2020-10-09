#!/usr/bin/env bash

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

windowID="$(xprop -root '\t$0' _NET_ACTIVE_WINDOW | cut -f 2)"

PROG=$(pidof dolphin)

if [ -n "$PROG" ]; then
	kdialog --attach="$windowID" --title $"Restaurar Configurações" \
--sorry $"Atenção! O programa está aberto!\nEle será fechado para que a restauração tenha efeito."
	RET="$?"
	[ "$RET" == "0" ] && kill -9 $PROG
fi

if [ "$1" = "1" ]; then
	rm -r ~/.local/share/kxmlgui5/dolphin
	rm -r ~/.local/share/dolphin
	rm ~/.config/session/dolphin_dolphin_dolphin
	rm ~/.config/dolphinrc
	cp -r /etc/skel/.local/share/kxmlgui5/dolphin ~/.local/share/kxmlgui5/dolphin
else
	rm -r ~/.local/share/kxmlgui5/dolphin
	rm -r ~/.local/share/dolphin
	rm ~/.config/session/dolphin_dolphin_dolphin
	rm ~/.config/dolphinrc
fi
kdialog --attach="$windowID" --title $"Restaurar Configurações" \
		--msgbox $"As configurações foram restauradas com sucesso!"
exit
