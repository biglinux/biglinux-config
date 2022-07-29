#!/usr/bin/env bash

PROG=$(pidof mystiq)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.config/mystiq
    cp -r /etc/skel/.config/mystiq ~/.config/mystiq
    echo -n "#"
else
    rm -r ~/.config/mystiq
    echo -n "#"
fi

exit
