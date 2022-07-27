#!/usr/bin/env bash

PROG=$(pidof clementine)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ]; then
    rm -r ~/.config/Clementine
    cp -r /etc/skel/.config/Clementine ~/.config/Clementine
    echo -n "#"
else
    rm -r ~/.config/Clementine
    echo -n "#"
fi

exit
