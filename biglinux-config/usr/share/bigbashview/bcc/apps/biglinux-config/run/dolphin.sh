#!/usr/bin/env bash

PROG=$(pidof dolphin)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ]; then
    rm -r ~/.local/share/kxmlgui5/dolphin
    rm -r ~/.local/share/dolphin
    rm ~/.config/session/dolphin_dolphin_dolphin
    rm ~/.config/dolphinrc
    cp -f /etc/skel/.config/dolphinrc ~/.config/dolphinrc
    cp -r /etc/skel/.local/share/kxmlgui5/dolphin ~/.local/share/kxmlgui5/dolphin
    echo -n "#"
else
    rm -r ~/.local/share/kxmlgui5/dolphin
    rm -r ~/.local/share/dolphin
    rm ~/.config/session/dolphin_dolphin_dolphin
    rm ~/.config/dolphinrc
    echo -n "#"
fi

exit
