#!/usr/bin/env bash

PROG=$(pidof brave)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

rm -r ~/.config/BraveSoftware
echo -n "#"

exit
