#!/usr/bin/env bash

PROG=$(pidof google-chrome)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

rm -r ~/.config/google-chrome
echo -n "#"

exit
