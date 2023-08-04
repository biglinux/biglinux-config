#!/usr/bin/env bash

if pidof gwenview; then
	exit
fi

rm -r ~/.local/share/kxmlgui5/gwenview >/dev/null 2>&-
rm -r ~/.local/share/gwenview >/dev/null 2>&-
rm ~/.config/gwenviewrc >/dev/null 2>&-

if [ "$1" = "skel" ]; then
	cp -r /etc/skel/.local/share/kxmlgui5/gwenview ~/.local/share/kxmlgui5/gwenview >/dev/null 2>&-
	cp -r /etc/skel/.local/share/gwenview ~/.local/share/gwenview >/dev/null 2>&-
	cp -f /etc/skel/.config/gwenviewrc ~/.config/gwenviewrc >/dev/null 2>&-
fi
echo -n "#"
exit
