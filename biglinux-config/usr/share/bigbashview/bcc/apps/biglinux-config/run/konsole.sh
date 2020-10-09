#!/usr/bin/env bash

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

windowID="$(xprop -root '\t$0' _NET_ACTIVE_WINDOW | cut -f 2)"

PROG=$(pidof konsole)

if [ -n "$PROG" ]; then
	kdialog --attach="$windowID" --title $"Restaurar Configurações" \
--sorry $"Atenção! O programa está aberto!\nEle será fechado para que a restauração tenha efeito."
	RET="$?"
	[ "$RET" == "0" ] && kill -9 $PROG
fi

if [ "$1" = "1" ]; then
	rm -r ~/.config/konsole.knsrc
	rm -r ~/.config/konsolerc
	rm -r ~/.local/share/konsole
	rm -r ~/.local/share/kxmlgui5/konsole
	cp /etc/skel/.config/konsole.knsrc ~/.config/konsole.knsrc
	cp /etc/skel/.config/konsolerc ~/.config/konsolerc
	cp -r /etc/skel/.local/share/konsole ~/.local/share/konsole
else
	rm -r ~/.config/konsole.knsrc
	rm -r ~/.config/konsolerc
	rm -r ~/.local/share/konsole
	rm -r ~/.local/share/kxmlgui5/konsole
fi
kdialog --attach="$windowID" --title $"Restaurar Configurações" \
		--msgbox $"As configurações foram restauradas com sucesso!"
exit