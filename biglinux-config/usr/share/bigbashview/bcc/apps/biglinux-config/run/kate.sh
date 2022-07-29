#!/usr/bin/env bash

PROG=$(pidof kate)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.local/share/kate
    rm -r ~/.local/share/kxmlgui5/kate
    rm -r ~/.local/share/kxmlgui5/katepart
    rm -r ~/.local/share/ktexteditor_snippets
    rm ~/.config/katevirc
    rm ~/.config/katemetainfos
    rm ~/.config/kateschemarc
    rm ~/.config/katesyntaxhighlightingrc
    rm ~/.config/katerc
    cp -f /etc/skel/.config/katevirc ~/.config/katevirc
    cp -f /etc/skel/.config/katemetainfos ~/.config/katemetainfos
    cp -f /etc/skel/.config/kateschemarc ~/.config/kateschemarc
    cp -f /etc/skel/.config/katesyntaxhighlightingrc ~/.config/katesyntaxhighlightingrc
    cp -f /etc/skel/.config/katerc ~/.config/katerc
    cp -r /etc/skel/.local/share/kate ~/.local/share/kate
    cp -r /etc/skel/.local/share/kxmlgui5/kate ~/.local/share/kxmlgui5/kate
    cp -r /etc/skel/.local/share/kxmlgui5/katepart ~/.local/share/kxmlgui5/katepart
    cp -r /etc/skel/.local/share/ktexteditor_snippets ~/.local/share/ktexteditor_snippets
    echo -n "#"
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
    echo -n "#"
fi

exit
