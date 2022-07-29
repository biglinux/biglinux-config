#!/usr/bin/env bash

PROG=$(pidof okular)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.local/share/kxmlgui5/okular
    rm -r ~/.local/share/okular
    rm ~/.config/okularpartrc
    rm ~/.config/okularrc
    cp -r /etc/skel/.local/share/kxmlgui5/okular ~/.local/share/kxmlgui5/okular
    cp -f /etc/skel/.config/okularpartrc ~/.config/okularpartrc
    cp -f /etc/skel/.config/okularrc ~/.config/okularrc
    echo -n "#"
else
    rm -r ~/.local/share/kxmlgui5/okular
    rm -r ~/.local/share/okular
    rm ~/.config/okularpartrc
    rm ~/.config/okularrc
    echo -n "#"
fi

exit
