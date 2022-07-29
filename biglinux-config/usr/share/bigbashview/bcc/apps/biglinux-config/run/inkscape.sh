#!/usr/bin/env bash

PROG=$(pidof inkscape)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

rm -r ~/.config/inkscape
echo -n "#"

exit
