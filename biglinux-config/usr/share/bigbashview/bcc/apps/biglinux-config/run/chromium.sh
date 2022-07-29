#!/usr/bin/env bash

PROG=$(pidof chromium)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ]; then
    rm -r ~/.config/chromium
    rm -r ~/.config/chromium-optimize
    cp -r /etc/skel/.config/chromium ~/.config/chromium
    echo -n "#"
else
    rm -r ~/.config/chromium
    rm -r ~/.config/chromium-optimize
    echo -n "#"
fi

exit
