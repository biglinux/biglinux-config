#!/usr/bin/env bash

PROG=$(pidof soffice.bin)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.config/libreoffice
    rm -r ~/.config/LanguageTool
    cp -r /etc/skel/.config/libreoffice ~/.config/libreoffice
    echo -n "#"
else
    rm -r ~/.config/libreoffice
    rm -r ~/.config/LanguageTool
    echo -n "#"
fi

exit
