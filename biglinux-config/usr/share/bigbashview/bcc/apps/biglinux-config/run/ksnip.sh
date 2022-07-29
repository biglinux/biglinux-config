#!/usr/bin/env bash

PROG=$(pidof ksnip)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.config/ksnip
    cp -r /etc/skel/.config/ksnip ~/.config/ksnip
    echo -n "#"
else
    rm -r ~/.config/ksnip
    echo -n "#"
fi

exit
