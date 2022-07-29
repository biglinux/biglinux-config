#!/usr/bin/env bash

PROG=$(pidof gimp-2.10)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.config/GIMP
    cp -r /etc/skel/.config/GIMP ~/.config/GIMP
    echo -n "#"
else
    rm -r ~/.config/GIMP
    echo -n "#"
fi

exit
