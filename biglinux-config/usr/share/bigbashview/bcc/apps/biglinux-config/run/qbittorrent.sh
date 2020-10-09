#!/usr/bin/env bash

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

windowID="$(xprop -root '\t$0' _NET_ACTIVE_WINDOW | cut -f 2)"

PROG=$(pidof qbittorrent)

if [ -n "$PROG" ]; then
	kdialog --attach="$windowID" --title $"Restaurar Configurações" \
--sorry $"Atenção! O programa está aberto!\nEle será fechado para que a restauração tenha efeito."
	RET="$?"
	[ "$RET" == "0" ] && kill -9 $PROG
fi

if [ "$1" = "1" ]; then
	rm -r ~/.config/qBittorrent
	rm -r ~/.local/share/data/qBittorrent
	cp -r /etc/skel/.config/qBittorrent ~/.config/qBittorrent
	cp -r /etc/skel/.local/share/data/qBittorrent ~/.local/share/data/qBittorrent
else
	rm -r ~/.config/qBittorrent
	rm -r ~/.local/share/data/qBittorrent
fi
kdialog --attach="$windowID" --title $"Restaurar Configurações" \
		--msgbox $"As configurações foram restauradas com sucesso!"
exit