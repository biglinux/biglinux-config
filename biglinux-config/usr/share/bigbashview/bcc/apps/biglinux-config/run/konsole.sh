#!/usr/bin/env bash

PROG=$(pidof konsole)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.config/konsole.knsrc
    rm -r ~/.config/konsolerc
    rm -r ~/.local/share/konsole
    rm -r ~/.local/share/kxmlgui5/konsole
    cp /etc/skel/.config/konsole.knsrc ~/.config/konsole.knsrc
    cp /etc/skel/.config/konsolerc ~/.config/konsolerc
    cp -r /etc/skel/.local/share/konsole ~/.local/share/konsole
    echo -n "#"
else
    rm -r ~/.config/konsole.knsrc
    rm -r ~/.config/konsolerc
    rm -r ~/.local/share/konsole
    rm -r ~/.local/share/kxmlgui5/konsole
    echo -n "#"
fi

exit
