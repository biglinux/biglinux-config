#!/usr/bin/env bash

PROG=$(pidof gwenview)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.local/share/kxmlgui5/gwenview
    rm -r ~/.local/share/gwenview
    rm ~/.config/gwenviewrc
    cp -r /etc/skel/.local/share/kxmlgui5/gwenview ~/.local/share/kxmlgui5/gwenview
    cp -r /etc/skel/.local/share/gwenview ~/.local/share/gwenview
    cp -f /etc/skel/.config/gwenviewrc ~/.config/gwenviewrc
    echo -n "#"
else
    rm -r ~/.local/share/kxmlgui5/gwenview
    rm -r ~/.local/share/gwenview
    rm ~/.config/gwenviewrc
    echo -n "#"
fi

exit
