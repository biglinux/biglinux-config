#!/usr/bin/env bash

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

windowID="$(xprop -root '\t$0' _NET_ACTIVE_WINDOW | cut -f 2)"

PROG=$(pidof okular)

if [ -n "$PROG" ]; then
	kdialog --attach="$windowID" --title $"Restaurar Configurações" \
--sorry $"Atenção! O programa está aberto!\nEle será fechado para que a restauração tenha efeito."
	RET="$?"
	[ "$RET" == "0" ] && kill -9 $PROG
fi

if [ "$1" = "1" ]; then
	rm -r ~/.local/share/kxmlgui5/okular
	rm -r ~/.local/share/okular
	rm ~/.config/okularpartrc
	rm ~/.config/okularrc
	cp -r /etc/skel/.local/share/kxmlgui5/okular ~/.local/share/kxmlgui5/okular
else
	rm -r ~/.local/share/kxmlgui5/okular
	rm -r ~/.local/share/okular
	rm ~/.config/okularpartrc
	rm ~/.config/okularrc
fi
kdialog --attach="$windowID" --title $"Restaurar Configurações" \
		--msgbox $"As configurações foram restauradas com sucesso!"
exit